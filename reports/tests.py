from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from files.tests.helpers import make_csv_bytes
from reports.services import (
    chart_bar,
    chart_line,
    chart_pie,
    detect_kind,
    kpi_cards,
    report_table,
)

User = get_user_model()


def _df():
    import pandas as pd

    return pd.DataFrame(
        {
            "Name": ["Ivan", "Ivan", "Petr", "Alex", "Petr", "Maria"],
            "City": ["Moscow", "Moscow", "SPb", "SPb", "Kazan", "Kazan"],
            "Salary": [90000, 80000, 120000, 70000, 95000, 110000],
        }
    )


class ReportServiceTests(TestCase):
    def test_kpi_cards(self):
        cards = kpi_cards(_df())
        labels = {c["label"]: c["value"] for c in cards}
        self.assertEqual(labels["Строк"], 6)
        self.assertEqual(labels["Столбцов"], 3)
        self.assertEqual(labels["Дубликаты"], 0)

    def test_charts_return_svg(self):
        df = _df()
        self.assertIn("<svg", chart_bar(df, "City"))
        self.assertIn("<svg", chart_line(df, "Salary"))
        self.assertIn("<svg", chart_pie(df, "City"))

    def test_charts_empty_column(self):
        import pandas as pd

        df = pd.DataFrame({"A": ["", "", ""], "B": [1, 2, 3]})
        self.assertIsNone(chart_bar(df, "A"))
        self.assertIsNotNone(chart_line(df, "B"))

    def test_detect_kind(self):
        df = _df()
        self.assertEqual(detect_kind(df, "Salary"), "numeric")
        self.assertEqual(detect_kind(df, "Name"), "text")

    def test_report_table(self):
        table = report_table(_df(), limit=2)
        self.assertEqual(len(table["rows"]), 2)
        self.assertIn("Name", table["columns"])


class ReportViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="carol", email="c@example.com", password="pass")
        self.client.force_login(self.user)

    def test_report_requires_session(self):
        response = self.client.get(reverse("reports:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Файл не загружен")
        self.assertContains(response, "Загрузить файл")

    def test_report_page_renders(self):
        self.client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("r.csv", make_csv_bytes(_df()), content_type="text/csv")},
        )
        response = self.client.get(reverse("reports:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Отчёт")
        self.assertContains(response, "Строк")
        self.assertContains(response, "svg")
        self.assertContains(response, "Скачать отчёт")

    def test_report_export(self):
        self.client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("r.csv", make_csv_bytes(_df()), content_type="text/csv")},
        )
        response = self.client.get(reverse("reports:export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("report.html", response["Content-Disposition"])
        self.assertContains(response, "office data studio")