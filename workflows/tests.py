from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from files.models import ProcessedFile
from workflows.models import Execution, Workflow, WorkflowOperation

from files.tests.helpers import make_csv_bytes, make_xlsx_bytes, sample_df

User = get_user_model()


class WorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="pass")
        self.client.force_login(self.user)

    def _upload_and_apply_ops(self):
        self.client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("clients.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        self.client.post(reverse("files:apply"), {"op": "remove_empty_rows"})
        self.client.post(
            reverse("files:apply"),
            {"op": "filter", "column": "Salary", "operator": "gt", "value": "85000"},
        )

    def test_create_workflow_from_session(self):
        self._upload_and_apply_ops()
        response = self.client.post(
            reverse("workflows:create"),
            {"name": "Очистка клиентской базы", "description": "для клиентов"},
        )
        self.assertEqual(response.status_code, 302)
        workflow = Workflow.objects.get(user=self.user, name="Очистка клиентской базы")
        self.assertEqual(workflow.operations.count(), 2)
        ops = list(workflow.operations.all())
        self.assertEqual(ops[0].operation_type, "remove_empty_rows")
        self.assertEqual(ops[1].operation_type, "filter")

    def test_create_workflow_requires_session(self):
        response = self.client.get(reverse("workflows:create"))
        self.assertRedirects(response, reverse("files:upload"))

    def test_workflow_index(self):
        wf = Workflow.objects.create(user=self.user, name="W1")
        WorkflowOperation.objects.create(workflow=wf, operation_type="remove_empty_rows", order=0)
        response = self.client.get(reverse("workflows:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "W1")

    def test_run_workflow_success(self):
        self._upload_and_apply_ops()
        self.client.post(reverse("workflows:create"), {"name": "Cleaner"})
        workflow = Workflow.objects.get(user=self.user, name="Cleaner")

        response = self.client.post(
            reverse("workflows:run", args=[workflow.pk]),
            {"file": SimpleUploadedFile("april.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        self.assertRedirects(response, reverse("workflows:detail", args=[workflow.pk]))

        execution = Execution.objects.get(workflow=workflow)
        self.assertEqual(execution.status, Execution.Status.SUCCESS)
        self.assertEqual(execution.rows_before, 5)
        self.assertIsNotNone(execution.output_file)
        # remove_empty_rows удаляет 1 пустую строку, затем filter >85000 оставляет 3
        self.assertEqual(execution.rows_after, 3)

    def test_run_workflow_missing_column_fails_gracefully(self):
        import pandas as pd

        wf = Workflow.objects.create(user=self.user, name="NeedsSalary")
        WorkflowOperation.objects.create(
            workflow=wf,
            operation_type="filter",
            order=0,
            configuration={"column": "Salary", "operator": "gt", "value": "100"},
        )
        df = pd.DataFrame({"Name": ["x"]})
        response = self.client.post(
            reverse("workflows:run", args=[wf.pk]),
            {"file": SimpleUploadedFile("no_salary.csv", make_csv_bytes(df), content_type="text/csv")},
        )
        self.assertRedirects(response, reverse("workflows:detail", args=[wf.pk]))
        execution = Execution.objects.get(workflow=wf)
        self.assertEqual(execution.status, Execution.Status.FAILED)
        self.assertIn("Salary", execution.error)

    def test_run_workflow_wrong_extension(self):
        wf = Workflow.objects.create(user=self.user, name="Cleaner")
        response = self.client.post(
            reverse("workflows:run", args=[wf.pk]),
            {"file": SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")},
        )
        self.assertRedirects(response, reverse("workflows:run", args=[wf.pk]))
        self.assertEqual(Execution.objects.filter(workflow=wf).count(), 0)

    def test_delete_workflow(self):
        wf = Workflow.objects.create(user=self.user, name="ToDelete")
        response = self.client.post(reverse("workflows:delete", args=[wf.pk]))
        self.assertRedirects(response, reverse("workflows:index"))
        self.assertFalse(Workflow.objects.filter(pk=wf.pk).exists())

    def test_export_op_not_saved_in_workflow(self):
        # Экспорт не должен попадать в сохранённый workflow
        self._upload_and_apply_ops()
        self.client.get(reverse("files:download"), {"fmt": "csv"})
        self.client.post(reverse("workflows:create"), {"name": "NoExport"})
        workflow = Workflow.objects.get(user=self.user, name="NoExport")
        self.assertEqual(workflow.operations.count(), 2)
        for op in workflow.operations.all():
            self.assertNotEqual(op.operation_type, "export")

    def test_run_workflow_xlsx_input(self):
        self._upload_and_apply_ops()
        self.client.post(reverse("workflows:create"), {"name": "CleanerXlsx"})
        workflow = Workflow.objects.get(user=self.user, name="CleanerXlsx")
        response = self.client.post(
            reverse("workflows:run", args=[workflow.pk]),
            {"file": SimpleUploadedFile("april.xlsx", make_xlsx_bytes(sample_df()))},
        )
        self.assertRedirects(response, reverse("workflows:detail", args=[workflow.pk]))
        execution = Execution.objects.get(workflow=workflow)
        self.assertEqual(execution.status, Execution.Status.SUCCESS)
        self.assertEqual(execution.output_file.file_type, "xlsx")
        self.assertEqual(execution.output_file.original_name, "april_cleaned.xlsx")