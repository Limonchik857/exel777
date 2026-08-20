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

    def test_undo_then_new_operation_discards_branch(self):
        self._upload()
        # op1
        self.client.post(reverse("files:apply"), {"op": "remove_empty_rows"})
        # op2 — фильтр, оставляющий 3 строки
        self.client.post(
            reverse("files:apply"),
            {"op": "filter", "column": "Salary", "operator": "gt", "value": "90000"},
        )
        state = self.client.session["processing"]
        self.assertEqual(len(state["versions"]), 3)
        self.assertEqual(len(proc.applied_history(state)), 2)
        old_ops = [h["op"] for h in proc.applied_history(state)]
        self.assertEqual(old_ops, ["remove_empty_rows", "filter"])

        # undo → op2 отменена
        self.client.post(reverse("files:undo"))
        state = self.client.session["processing"]
        self.assertEqual(state["current"], 1)
        self.assertEqual(len(proc.applied_history(state)), 1)

        # op3 вместо op2
        self.client.post(
            reverse("files:apply"),
            {"op": "sort", "column": "Salary", "order": "desc"},
        )
        state = self.client.session["processing"]
        self.assertEqual(state["current"], 2)
        self.assertEqual(len(state["versions"]), 3)
        ops = [h["op"] for h in proc.applied_history(state)]
        self.assertEqual(ops, ["remove_empty_rows", "sort"])
        # Текущая версия — результат op3 (сортировка), а не старого фильтра.
        request = self._request_with_session()
        df = proc.current_df(request)
        self.assertEqual(len(df), 4)
        self.assertNotEqual(
            df["Salary"].tolist(), [100000, 80000, 120000, 100000]
        )

    def test_history_trimming_keeps_sync(self):
        self._upload()
        # Применяем больше операций, чем MAX_UNDO_STEPS (3).
        with self.settings(MAX_UNDO_STEPS=3):
            for i in range(5):
                self.client.post(
                    reverse("files:apply"),
                    {"op": "filter", "column": "Salary", "operator": "gte", "value": str(i)},
                )
            state = self.client.session["processing"]
            self.assertLessEqual(len(state["versions"]), 3)
            self.assertEqual(state["current"], len(state["versions"]) - 1)
            # История ограничена MAX_UNDO_STEPS и соответствует текущей версии.
            self.assertEqual(len(proc.applied_history(state)), 3)
            df = proc.current_df(self._request_with_session())
            self.assertEqual(state["rows"], len(df))
            # Undo из ограниченной истории остаётся синхронным.
            request = self._request_with_session()
            state = request.session["processing"]
            while state["current"] > 0:
                self.assertTrue(proc.undo(request))
                snapshots = state["history_snapshots"]
                self.assertEqual(
                    len(proc.applied_history(state)),
                    len(snapshots[state["current"]]),
                )

    def _request_with_session(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.session = self.client.session
        return request

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