from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from files.tests.helpers import make_csv_bytes

from .services import analyze_quality

User = get_user_model()


class QualityServiceTests(TestCase):
    def test_clean_data_high_score(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Name": ["Ivan", "Petr", "Alex"],
                "Email": ["i@mail.ru", "p@mail.ru", "a@mail.ru"],
                "Phone": ["+79000000001", "+79011112233", "+79020000003"],
            }
        )
        report = analyze_quality(df)
        self.assertEqual(report["rows"], 3)
        self.assertEqual(report["duplicates"], 0)
        self.assertEqual(report["empty_values"], 0)
        self.assertGreaterEqual(report["score"], 90)
        self.assertIn(report["status"], ("GOOD", "WARNING"))

    def test_duplicates_detected(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Name": ["Ivan", "Ivan", "Petr"],
                "Email": ["i@mail.ru", "i@mail.ru", "p@mail.ru"],
            }
        )
        report = analyze_quality(df)
        self.assertEqual(report["duplicates"], 1)
        categories = [i["category"] for i in report["issues"]]
        self.assertIn("duplicates", categories)
        dup_issue = next(i for i in report["issues"] if i["category"] == "duplicates")
        self.assertEqual(dup_issue["count"], 1)
        self.assertEqual(dup_issue["action"], "remove_duplicates")

    def test_invalid_emails_detected(self):
        import pandas as pd

        df = pd.DataFrame({"Email": ["good@mail.ru", "bad-email", "no-at-sign"]})
        report = analyze_quality(df)
        email_issue = next(
            (i for i in report["issues"] if i["category"] == "email"), None
        )
        self.assertIsNotNone(email_issue)
        self.assertEqual(email_issue["count"], 2)
        self.assertLess(report["breakdown"]["email_valid_pct"], 40)
        self.assertEqual(report["status"], "CRITICAL")

    def test_invalid_phones_detected(self):
        import pandas as pd

        df = pd.DataFrame({"Phone": ["+79000000001", "abc", "123"]})
        report = analyze_quality(df)
        phone_issue = next(
            (i for i in report["issues"] if i["category"] == "phone"), None
        )
        self.assertIsNotNone(phone_issue)
        self.assertEqual(phone_issue["count"], 2)

    def test_empty_values_detected(self):
        import pandas as pd

        df = pd.DataFrame({"A": ["x", None, ""], "B": [1, 2, 3]})
        report = analyze_quality(df)
        self.assertEqual(report["empty_values"], 2)
        self.assertIn(
            "empty", [i["category"] for i in report["issues"]]
        )

    def test_score_penalizes_dirty_data(self):
        import pandas as pd

        clean = pd.DataFrame(
            {
                "Email": ["a@mail.ru", "b@mail.ru", "c@mail.ru"],
                "Phone": ["+79000000001", "+79011112233", "+79020000003"],
            }
        )
        dirty = pd.DataFrame(
            {
                "Email": ["a@mail.ru", "bad", "c@mail.ru", "bad"],
                "Phone": ["+79000000001", "x", "+79020000003", "y"],
            }
        )
        clean_score = analyze_quality(clean)["score"]
        dirty_score = analyze_quality(dirty)["score"]
        self.assertGreater(clean_score, dirty_score)


class QualityViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="a@example.com", password="pass")
        self.client.force_login(self.user)

    def test_quality_requires_session(self):
        response = self.client.get(reverse("quality:index"))
        self.assertRedirects(response, reverse("files:upload"))

    def test_quality_page_renders(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Name": ["Ivan", "Ivan", "Petr"],
                "Email": ["i@mail.ru", "i@mail.ru", "bad"],
            }
        )
        self.client.post(
            reverse("files:upload"),
            {"file": SimpleUploadedFile("q.csv", make_csv_bytes(df), content_type="text/csv")},
        )
        response = self.client.get(reverse("quality:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Data Quality Score")
        self.assertContains(response, "дублирующихся строк")
        self.assertContains(response, "некорректных email")