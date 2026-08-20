"""Безопасность: CSV injection, ZIP-бомбы, лимиты ресурсов, merge rollback, rate limit."""

import io
import zipfile

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from files.models import UploadedFile
from files.services import export_dataframe, validate_xlsx_security
from operations.validators import TableReadError

from .helpers import make_csv_bytes, make_xlsx_bytes, sample_df, sample_other_df

User = get_user_model()


class CsvInjectionTests(TestCase):
    def setUp(self):
        import pandas as pd

        self.df = pd.DataFrame(
            {
                "Name": ["=SUM(A1:A10)", "+cmd|' /C calc'!A0", "-2+3", "@import", "safe", 42],
            }
        )

    @override_settings(SAFE_CSV_EXPORT=True)
    def test_safe_export_escapes_formula_prefixes(self):
        data, _ = export_dataframe(self.df, "csv")
        text = data.decode("utf-8-sig")
        self.assertIn("'=SUM(A1:A10)", text)
        self.assertIn("'+cmd|' /C calc'!A0", text)
        self.assertIn("'-2+3", text)
        self.assertIn("'@import", text)
        self.assertIn("safe", text)
        # Числа не экранируются
        self.assertIn("\n42", text)

    @override_settings(SAFE_CSV_EXPORT=False)
    def test_unsafe_export_leaves_values(self):
        data, _ = export_dataframe(self.df, "csv")
        text = data.decode("utf-8-sig")
        self.assertIn("=SUM(A1:A10)", text)
        self.assertNotIn("'=SUM", text)


class XlsxSecurityTests(TestCase):
    def test_xlsx_zip_bomb_high_ratio_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("xl/worksheets/sheet1.xml", "A" * (2 * 1024 * 1024))
        path = "bomb.xlsx"
        with open(path, "wb") as fh:
            fh.write(buf.getvalue())
        try:
            with self.assertRaises(TableReadError):
                validate_xlsx_security(path)
        finally:
            import os

            os.remove(path)

    def test_xlsx_too_many_entries_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
            for i in range(10001):
                zf.writestr(f"e{i}.xml", "x")
        path = "many_entries.xlsx"
        with open(path, "wb") as fh:
            fh.write(buf.getvalue())
        try:
            with self.assertRaises(TableReadError):
                validate_xlsx_security(path)
        finally:
            import os

            os.remove(path)

    def test_valid_xlsx_passes_security(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("xl/workbook.xml", "<workbook/>")
            zf.writestr("xl/worksheets/sheet1.xml", "<sheet/>")
        path = "ok.xlsx"
        with open(path, "wb") as fh:
            fh.write(buf.getvalue())
        try:
            validate_xlsx_security(path)  # не должно быть исключений
        finally:
            import os

            os.remove(path)


class ResourceLimitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="pass")
        self.client.force_login(self.user)

    @override_settings(DATA_MAX_ROWS=4)
    def test_upload_too_many_rows_rejected(self):
        response = self.client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("big.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        self.assertRedirects(response, reverse("files:upload"))
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 0)
        self.assertNotIn("processing", self.client.session)


class MergeRollbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="pass")
        self.client.force_login(self.user)

    def _corrupt_csv(self):
        # Расширение .csv, но содержимое не читается как таблица
        return SimpleUploadedFile("bad.csv", b"\x00\x01\x02\xff\xfe broken \x00\x00", content_type="text/csv")

    def test_merge_partial_failure_rolls_back_all(self):
        """Если один файл не читается — все загруженные файлы должны быть удалены."""
        response = self.client.post(
            reverse("files:merge"),
            {
                "files": [
                    SimpleUploadedFile("a.csv", make_csv_bytes(sample_df()), content_type="text/csv"),
                    self._corrupt_csv(),
                ]
            },
        )
        self.assertRedirects(response, reverse("files:merge"))
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 0)
        self.assertNotIn("processing", self.client.session)

    @override_settings(MAX_MERGE_FILES=2)
    def test_merge_too_many_files_rejected(self):
        response = self.client.post(
            reverse("files:merge"),
            {
                "files": [
                    SimpleUploadedFile("a.csv", make_csv_bytes(sample_df()), content_type="text/csv"),
                    SimpleUploadedFile("b.csv", make_csv_bytes(sample_other_df()), content_type="text/csv"),
                    SimpleUploadedFile("c.csv", make_csv_bytes(sample_df()), content_type="text/csv"),
                ]
            },
        )
        self.assertRedirects(response, reverse("files:merge"))
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 0)

    @override_settings(MAX_TOTAL_MERGE_SIZE=100)  # 100 байт
    def test_merge_total_size_rejected(self):
        response = self.client.post(
            reverse("files:merge"),
            {
                "files": [
                    SimpleUploadedFile("a.csv", make_csv_bytes(sample_df()), content_type="text/csv"),
                    SimpleUploadedFile("b.csv", make_csv_bytes(sample_other_df()), content_type="text/csv"),
                ]
            },
        )
        self.assertRedirects(response, reverse("files:merge"))
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 0)


class RateLimitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="pass")
        self.client.force_login(self.user)

    @override_settings(RATE_LIMIT_UPLOAD_PER_MINUTE=2)
    def test_upload_rate_limited(self):
        url = reverse("files:upload")
        for _ in range(2):
            self.client.post(
                url,
                {"file": SimpleUploadedFile("a.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
            )
        response = self.client.post(
            url,
            {"file": SimpleUploadedFile("b.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
            follow=True,
        )
        self.assertContains(response, "Слишком много запросов")

    @override_settings(RATE_LIMIT_EXPORT_PER_MINUTE=1)
    def test_export_rate_limited(self):
        self.client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("a.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        first = self.client.get(reverse("files:download"), {"fmt": "xlsx"})
        self.assertEqual(first.status_code, 200)
        second = self.client.get(reverse("files:download"), {"fmt": "xlsx"})
        self.assertEqual(second.status_code, 429)

    def test_rate_limit_per_user_isolation(self):
        # Ограничение считается отдельно для каждого пользователя.
        self.client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("a.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        other = User.objects.create_user(username="bob", email="bob@example.com", password="pass")
        other_client = self.__class__.client_class()
        other_client.force_login(other)
        response = other_client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("b.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        self.assertRedirects(response, reverse("files:processor"))