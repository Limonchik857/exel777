from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from files.models import UploadedFile
from files.services import detect_file_type, validate_uploaded
from operations.validators import FileValidationError

from .helpers import make_csv_bytes, make_xlsx_bytes, sample_df

User = get_user_model()


class UploadValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="pass")
        self.client.force_login(self.user)

    def test_detect_file_type(self):
        self.assertEqual(detect_file_type("a.XLSX"), "xlsx")
        self.assertEqual(detect_file_type("b.CSV"), "csv")
        self.assertIsNone(detect_file_type("c.txt"))
        self.assertIsNone(detect_file_type("d"))

    def test_validate_ok(self):
        data = SimpleUploadedFile("clients.csv", make_csv_bytes(sample_df()), content_type="text/csv")
        file_type, name = validate_uploaded(data, 20 * 1024 * 1024)
        self.assertEqual(file_type, "csv")
        self.assertEqual(name, "clients.csv")

    def test_validate_wrong_extension(self):
        data = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        with self.assertRaises(FileValidationError):
            validate_uploaded(data, 20 * 1024 * 1024)

    def test_validate_bad_mime(self):
        data = SimpleUploadedFile("script.xlsx", b"PK", content_type="application/x-msdownload")
        with self.assertRaises(FileValidationError):
            validate_uploaded(data, 20 * 1024 * 1024)

    def test_validate_too_large(self):
        data = SimpleUploadedFile("big.csv", b"a" * 1000, content_type="text/csv")
        with self.assertRaises(FileValidationError):
            validate_uploaded(data, 100)

    def test_validate_empty(self):
        data = SimpleUploadedFile("empty.csv", b"", content_type="text/csv")
        with self.assertRaises(FileValidationError):
            validate_uploaded(data, 20 * 1024 * 1024)

    def test_safe_name(self):
        data = SimpleUploadedFile("../weird/name.csv", b"x", content_type="text/csv")
        file_type, name = validate_uploaded(data, 20 * 1024 * 1024)
        self.assertNotIn("/", name)
        self.assertNotIn("..", name)

    def test_upload_csv_view(self):
        url = reverse("files:upload")
        response = self.client.post(
            url,
            {"file": SimpleUploadedFile("clients.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        self.assertRedirects(response, reverse("files:processor"))
        uploaded = UploadedFile.objects.get(user=self.user)
        self.assertEqual(uploaded.file_type, "csv")
        self.assertEqual(uploaded.rows_count, 5)
        self.assertEqual(uploaded.columns_count, 4)

    def test_upload_xlsx_view(self):
        url = reverse("files:upload")
        response = self.client.post(
            url,
            {"file": SimpleUploadedFile("clients.xlsx", make_xlsx_bytes(sample_df()))},
        )
        self.assertRedirects(response, reverse("files:processor"))
        uploaded = UploadedFile.objects.get(user=self.user)
        self.assertEqual(uploaded.file_type, "xlsx")

    def test_upload_wrong_extension_view(self):
        url = reverse("files:upload")
        response = self.client.post(
            url,
            {"file": SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")},
        )
        self.assertRedirects(response, url)
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 0)

    def test_upload_too_large_view(self):
        url = reverse("files:upload")
        big = make_xlsx_bytes(sample_df())
        with override_settings(DATA_MAX_FILE_SIZE=10):
            response = self.client.post(
                url,
                {"file": SimpleUploadedFile("big.xlsx", big)},
            )
        self.assertRedirects(response, url)
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 0)

    def test_upload_non_table_content(self):
        url = reverse("files:upload")
        response = self.client.post(
            url,
            {"file": SimpleUploadedFile("fake.xlsx", b"this is not an excel file")},
        )
        self.assertRedirects(response, url)
        self.assertEqual(UploadedFile.objects.filter(user=self.user).count(), 0)
