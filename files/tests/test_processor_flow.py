from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from files.models import ProcessedFile
from files import processing as proc

from .helpers import make_csv_bytes, make_xlsx_bytes, sample_df

User = get_user_model()


class ProcessorFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="pass")
        self.client.force_login(self.user)

    def _upload(self):
        url = reverse("files:upload")
        self.client.post(
            url,
            {"file": SimpleUploadedFile("clients.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )

    def test_processor_requires_upload(self):
        response = self.client.get(reverse("files:processor"))
        self.assertRedirects(response, reverse("files:upload"))

    def test_processor_shows_preview(self):
        self._upload()
        response = self.client.get(reverse("files:processor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "clients.csv")
        self.assertContains(response, "Name")
        self.assertContains(response, "ivan@mail.ru")

    def test_apply_dedupe(self):
        self._upload()
        response = self.client.post(
            reverse("files:apply"),
            {"op": "remove_duplicates", "scope": "all"},
        )
        self.assertRedirects(response, reverse("files:processor") + "?op=remove_duplicates")
        state = self.client.session["processing"]
        self.assertEqual(state["history"][-1]["op"], "remove_duplicates")
        self.assertEqual(len(state["history"]), 1)

    def test_apply_drop_columns(self):
        self._upload()
        response = self.client.post(
            reverse("files:apply"),
            {"op": "drop_columns", "columns": ["Phone"]},
        )
        self.assertEqual(response.status_code, 302)
        state = self.client.session["processing"]
        self.assertEqual(state["columns"], ["Name", "Email", "Salary", "Phone"])
        self.assertEqual(len(state["history"]), 1)

    def test_apply_filter(self):
        self._upload()
        self.client.post(
            reverse("files:apply"),
            {"op": "filter", "column": "Salary", "operator": "gt", "value": "90000"},
        )
        state = self.client.session["processing"]
        self.assertEqual(len(state["history"]), 1)

    def test_apply_sort(self):
        self._upload()
        self.client.post(
            reverse("files:apply"),
            {"op": "sort", "column": "Salary", "order": "desc"},
        )
        state = self.client.session["processing"]
        self.assertEqual(state["history"][-1]["config"]["ascending"], False)

    def test_apply_invalid_op_keeps_state(self):
        self._upload()
        self.client.post(
            reverse("files:apply"),
            {"op": "drop_columns"},
        )
        state = self.client.session["processing"]
        self.assertEqual(len(state["history"]), 0)

    def test_undo_redo(self):
        self._upload()
        self.client.post(reverse("files:apply"), {"op": "remove_empty_rows"})
        state = self.client.session["processing"]
        self.assertEqual(state["current"], 1)
        self.client.post(reverse("files:undo"))
        state = self.client.session["processing"]
        self.assertEqual(state["current"], 0)
        self.assertEqual(len(proc.applied_history(state)), 0)
        self.client.post(reverse("files:redo"))
        state = self.client.session["processing"]
        self.assertEqual(state["current"], 1)
        self.assertEqual(len(proc.applied_history(state)), 1)

    def test_download_creates_processed_file(self):
        self._upload()
        self.client.post(
            reverse("files:apply"),
            {"op": "filter", "column": "Salary", "operator": "gt", "value": "90000"},
        )
        response = self.client.get(reverse("files:download"), {"fmt": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProcessedFile.objects.filter(user=self.user).count(), 1)
        processed = ProcessedFile.objects.get(user=self.user)
        self.assertEqual(processed.rows_before, 5)
        self.assertEqual(processed.rows_after, 3)

    def test_download_csv(self):
        self._upload()
        response = self.client.get(reverse("files:download"), {"fmt": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProcessedFile.objects.filter(user=self.user).count(), 1)

    def test_reset(self):
        self._upload()
        response = self.client.post(reverse("files:reset"))
        self.assertRedirects(response, reverse("files:upload"))
        self.assertNotIn("processing", self.client.session)