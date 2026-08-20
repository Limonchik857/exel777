from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from zoneinfo import ZoneInfo

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

    def test_undo_then_new_op_workflow_contains_only_live_ops(self):
        """op1 → op2 → undo → op3. Workflow должен содержать только op1 и op3."""
        self.client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("clients.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        # op1
        self.client.post(reverse("files:apply"), {"op": "remove_empty_rows"})
        # op2
        self.client.post(
            reverse("files:apply"),
            {"op": "filter", "column": "Salary", "operator": "gt", "value": "90000"},
        )
        # undo → op2 отменена
        self.client.post(reverse("files:undo"))
        # op3
        self.client.post(
            reverse("files:apply"),
            {"op": "sort", "column": "Salary", "order": "desc"},
        )
        response = self.client.post(reverse("workflows:create"), {"name": "LiveOps"})
        self.assertEqual(response.status_code, 302)
        workflow = Workflow.objects.get(user=self.user, name="LiveOps")
        ops = list(workflow.operations.all())
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0].operation_type, "remove_empty_rows")
        self.assertEqual(ops[1].operation_type, "sort")

    def test_run_workflow_rows_before_after(self):
        """100 строк → удалить 20 → 80. rows_before=100, rows_after=80."""
        import pandas as pd

        df = pd.DataFrame({"A": list(range(100)), "B": ["x"] * 100})
        big = pd.concat([df, pd.DataFrame({"A": [None] * 20, "B": [""] * 20})], ignore_index=True)
        wf = Workflow.objects.create(user=self.user, name="Rows100")
        WorkflowOperation.objects.create(
            workflow=wf,
            operation_type="remove_empty_rows",
            order=0,
        )
        response = self.client.post(
            reverse("workflows:run", args=[wf.pk]),
            {"file": SimpleUploadedFile("big.csv", make_csv_bytes(big), content_type="text/csv")},
        )
        self.assertRedirects(response, reverse("workflows:detail", args=[wf.pk]))
        execution = Execution.objects.get(workflow=wf)
        self.assertEqual(execution.status, Execution.Status.SUCCESS)
        self.assertEqual(execution.rows_before, 120)
        self.assertEqual(execution.rows_after, 100)
        processed = execution.output_file
        self.assertEqual(processed.rows_before, 120)
        self.assertEqual(processed.rows_after, 100)


class PipelineScheduleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", email="b@example.com", password="pass")
        self.client.force_login(self.user)

    def _wf(self, **kwargs):
        defaults = {"name": "Scheduled"}
        defaults.update(kwargs)
        return Workflow.objects.create(user=self.user, **defaults)

    def test_compute_next_run_daily(self):
        from datetime import time

        from django.utils import timezone
        from workflows.services import compute_next_run

        wf = self._wf(
            schedule_active=True,
            schedule_type=Workflow.ScheduleType.DAILY,
            schedule_time=time(10, 30),
            timezone="Europe/Moscow",
        )
        now = timezone.now()
        nxt = compute_next_run(wf, now)
        self.assertIsNotNone(nxt)
        local = nxt.astimezone(ZoneInfo("Europe/Moscow"))
        self.assertEqual(local.hour, 10)
        self.assertEqual(local.minute, 30)
        self.assertGreater(nxt, now)

    def test_compute_next_run_disabled_returns_none(self):
        from workflows.services import compute_next_run

        wf = self._wf()
        self.assertIsNone(compute_next_run(wf))

    def test_compute_next_run_weekly_monday(self):
        from datetime import time, timedelta

        from django.utils import timezone
        from workflows.services import compute_next_run

        wf = self._wf(
            schedule_active=True,
            schedule_type=Workflow.ScheduleType.WEEKLY,
            schedule_time=time(9, 0),
            schedule_days=[0],
            timezone="Europe/Moscow",
        )
        now = timezone.now()
        nxt = compute_next_run(wf, now)
        local = nxt.astimezone(ZoneInfo("Europe/Moscow"))
        self.assertEqual(local.weekday(), 0)
        self.assertEqual(local.hour, 9)
        self.assertGreater(nxt, now - timedelta(days=2))

    def test_schedule_view_saves_and_computes(self):
        wf = self._wf()
        response = self.client.post(
            reverse("workflows:schedule", args=[wf.pk]),
            {
                "schedule_type": "daily",
                "schedule_time": "08:00",
                "schedule_days": "",
                "timezone": "Europe/Moscow",
                "schedule_active": "on",
            },
        )
        self.assertRedirects(response, reverse("workflows:detail", args=[wf.pk]))
        wf.refresh_from_db()
        self.assertTrue(wf.schedule_active)
        self.assertEqual(wf.schedule_type, "daily")
        self.assertIsNotNone(wf.next_run)

    def test_schedule_view_disable(self):
        wf = self._wf(schedule_active=True, schedule_type="daily", schedule_time="08:00")
        self.client.post(
            reverse("workflows:schedule", args=[wf.pk]),
            {
                "schedule_type": "daily",
                "schedule_time": "08:00",
                "schedule_days": "",
                "timezone": "Europe/Moscow",
                "schedule_active": "",
            },
        )
        wf.refresh_from_db()
        self.assertFalse(wf.schedule_active)
        self.assertEqual(wf.schedule_type, "manual")
        self.assertIsNone(wf.next_run)

    def test_schedule_form_requires_time_when_active(self):
        wf = self._wf()
        response = self.client.post(
            reverse("workflows:schedule", args=[wf.pk]),
            {"schedule_type": "daily", "schedule_time": "", "schedule_active": "on"},
        )
        self.assertRedirects(response, reverse("workflows:detail", args=[wf.pk]))
        wf.refresh_from_db()
        self.assertFalse(wf.schedule_active)

    def test_stage_error_recorded(self):
        import pandas as pd

        wf = Workflow.objects.create(user=self.user, name="TwoStep")
        WorkflowOperation.objects.create(
            workflow=wf, operation_type="normalize_text", order=0,
            configuration={"column": "Name", "modes": ["trim"]},
        )
        WorkflowOperation.objects.create(
            workflow=wf, operation_type="filter", order=1,
            configuration={"column": "Salary", "operator": "gt", "value": "100"},
        )
        df = pd.DataFrame({"Name": [" Ivan "], "City": ["M"]})
        response = self.client.post(
            reverse("workflows:run", args=[wf.pk]),
            {"file": SimpleUploadedFile("no_salary.csv", make_csv_bytes(df), content_type="text/csv")},
        )
        self.assertRedirects(response, reverse("workflows:detail", args=[wf.pk]))
        execution = Execution.objects.get(workflow=wf)
        self.assertEqual(execution.status, Execution.Status.FAILED)
        self.assertEqual(len(execution.stage_errors), 1)
        err = execution.stage_errors[0]
        self.assertEqual(err["order"], 1)
        self.assertEqual(err["op"], "filter")
        self.assertIn("Salary", err["error"])

    def test_execution_duration(self):
        from datetime import timedelta

        from django.utils import timezone

        wf = Workflow.objects.create(user=self.user, name="Dur")
        run = Execution.objects.create(user=self.user, workflow=wf, status=Execution.Status.SUCCESS)
        run.created_at = timezone.now() - timedelta(seconds=5)
        run.completed_at = timezone.now()
        run.save()
        run.refresh_from_db()
        self.assertIsNotNone(run.duration)
        self.assertGreaterEqual(run.duration, 4.0)