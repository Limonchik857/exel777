from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from files.models import UploadedFile
from files.services import export_dataframe

from .helpers import make_csv_bytes, sample_df, sample_other_df

User = get_user_model()


class MergeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="pass")
        self.client.force_login(self.user)

    def _different_structure_df(self):
        import pandas as pd

        return pd.DataFrame({"Name": ["x"], "Other": ["y"]})

    def test_merge_same_structure(self):
        url = reverse("files:merge")
        response = self.client.post(
            url,
            {
                "files": [
                    SimpleUploadedFile("a.csv", make_csv_bytes(sample_df()), content_type="text/csv"),
                    SimpleUploadedFile("b.csv", make_csv_bytes(sample_other_df()), content_type="text/csv"),
                ]
            },
        )
        self.assertRedirects(response, reverse("files:processor"))
        state = self.client.session["processing"]
        self.assertEqual(state["rows"], 7)
        # Источник загружен (объединённые файлы сохраняются только первый)
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 1)

    def test_merge_different_structure_rejected(self):
        url = reverse("files:merge")
        response = self.client.post(
            url,
            {
                "files": [
                    SimpleUploadedFile("a.csv", make_csv_bytes(sample_df()), content_type="text/csv"),
                    SimpleUploadedFile("b.csv", make_csv_bytes(self._different_structure_df()), content_type="text/csv"),
                ]
            },
        )
        self.assertRedirects(response, url)
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 0)
        self.assertNotIn("processing", self.client.session)

    def test_merge_requires_files(self):
        url = reverse("files:merge")
        response = self.client.post(url, {})
        self.assertRedirects(response, url)


class ExportTests(TestCase):
    def test_export_xlsx_bytes(self):
        data, mime = export_dataframe(sample_df(), "xlsx")
        self.assertTrue(data.startswith(b"PK"))
        self.assertIn("spreadsheetml", mime)

    def test_export_csv_bytes(self):
        data, mime = export_dataframe(sample_df(), "csv")
        self.assertIn(b"Name,Email", data)
        self.assertIn("text/csv", mime)

    def test_export_unknown_format(self):
        from operations.validators import ExportError

        with self.assertRaises(ExportError):
            export_dataframe(sample_df(), "pdf")