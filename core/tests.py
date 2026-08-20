from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AuthTests(TestCase):
    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("core:register"),
            {
                "email": "user@example.com",
                "username": "user1",
                "password1": "StrongPass123",
                "password2": "StrongPass123",
            },
        )
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_register_duplicate_email_rejected(self):
        User.objects.create_user(username="existing", email="dup@example.com", password="x")
        response = self.client.post(
            reverse("core:register"),
            {
                "email": "dup@example.com",
                "username": "newuser",
                "password1": "StrongPass123",
                "password2": "StrongPass123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "уже существует")

    def test_login_by_email(self):
        User.objects.create_user(username="user2", email="login@example.com", password="secret123")
        response = self.client.post(
            reverse("core:login"),
            {"username": "login@example.com", "password": "secret123"},
        )
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_login_wrong_password(self):
        User.objects.create_user(username="user3", email="nope@example.com", password="secret123")
        response = self.client.post(
            reverse("core:login"),
            {"username": "nope@example.com", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_logout(self):
        user = User.objects.create_user(username="user4", email="out@example.com", password="secret123")
        self.client.force_login(user)
        response = self.client.post(reverse("core:logout"))
        self.assertRedirects(response, reverse("core:login"))

    def test_authenticated_user_redirected_from_register(self):
        user = User.objects.create_user(username="user5", email="reg@example.com", password="secret123")
        self.client.force_login(user)
        response = self.client.get(reverse("core:register"))
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_shows_stats(self):
        user = User.objects.create_user(username="user6", email="dash@example.com", password="secret123")
        self.client.force_login(user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сводка")

    def test_settings_save_profile(self):
        user = User.objects.create_user(username="user7", email="set@example.com", password="secret123")
        self.client.force_login(user)
        response = self.client.post(
            reverse("core:settings"),
            {"first_name": "Иван", "last_name": "Петров"},
        )
        self.assertRedirects(response, reverse("core:settings"))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Иван")
        self.assertEqual(user.last_name, "Петров")