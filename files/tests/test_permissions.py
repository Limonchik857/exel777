from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from files.models import ProcessedFile, UploadedFile
from workflows.models import Execution, Workflow, WorkflowOperation

from .helpers import make_csv_bytes, sample_df

User = get_user_model()


class CrossUserAccessTests(TestCase):
    """Пользователь A не должен получить доступ к данным пользователя B."""

    def setUp(self):
        self.alice = User.objects.create_user(username="alice", email="alice@example.com", password="pass")
        self.bob = User.objects.create_user(username="bob", email="bob@example.com", password="pass")

        self.alice_upload = UploadedFile.objects.create(
            user=self.alice,
            original_name="alice.csv",
            file=SimpleUploadedFile("alice.csv", make_csv_bytes(sample_df()), content_type="text/csv"),
            file_type="csv",
            size=100,
            rows_count=5,
            columns_count=4,
            columns=["Name", "Email", "Salary", "Phone"],
        )
        self.alice_result = ProcessedFile.objects.create(
            user=self.alice,
            uploaded_file=self.alice_upload,
            original_name="alice_cleaned.xlsx",
            source_name="alice.csv",
            file_type="xlsx",
            rows_before=5,
            rows_after=4,
        )
        self.alice_result.file.save("alice_cleaned.xlsx", ContentFile(b"PK-fake"), save=True)

        self.alice_workflow = Workflow.objects.create(user=self.alice, name="Secret workflow")
        WorkflowOperation.objects.create(
            workflow=self.alice_workflow,
            operation_type="remove_empty_rows",
            order=0,
        )

    def _login(self, client, user):
        client.force_login(user)
        return client

    def test_bob_cannot_download_alice_upload(self):
        client = self._login(self.client, self.bob)
        url = reverse("core:download_source", args=[self.alice_upload.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_bob_cannot_download_alice_result(self):
        client = self._login(self.client, self.bob)
        url = reverse("core:download_processed", args=[self.alice_result.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_bob_cannot_view_alice_workflow(self):
        client = self._login(self.client, self.bob)
        url = reverse("workflows:detail", args=[self.alice_workflow.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_bob_cannot_run_alice_workflow(self):
        client = self._login(self.client, self.bob)
        url = reverse("workflows:run", args=[self.alice_workflow.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_bob_cannot_delete_alice_workflow(self):
        client = self._login(self.client, self.bob)
        url = reverse("workflows:delete", args=[self.alice_workflow.pk])
        response = client.post(url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Workflow.objects.filter(pk=self.alice_workflow.pk).exists())

    def test_bob_upload_and_processor_isolated(self):
        # Боб загружает файл — его сессия отдельна от Элис
        client = self._login(self.client, self.bob)
        response = client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("bob.csv", make_csv_bytes(sample_df()), content_type="text/csv")},
        )
        self.assertRedirects(response, reverse("files:processor"))
        state = client.session["processing"]
        bob_uploads = UploadedFile.objects.filter(user=self.bob)
        self.assertEqual(bob_uploads.count(), 1)
        self.assertEqual(state["uploaded_file_id"], bob_uploads.first().pk)
        self.assertNotEqual(bob_uploads.first().pk, self.alice_upload.pk)

    def test_alice_can_access_own_workflow(self):
        client = self._login(self.client, self.alice)
        url = reverse("workflows:detail", args=[self.alice_workflow.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_anon_cannot_see_processor(self):
        url = reverse("files:processor")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response.url)