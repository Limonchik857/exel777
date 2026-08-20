import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

# SECRET_KEY берём только из environment. Без него приложение не стартует.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY не задан. Задайте его в переменной окружения "
        "или в файле .env (например: DJANGO_SECRET_KEY=<случайная строка>)."
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1,[::1]",
    ).split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "files",
    "operations",
    "workflows",
    "quality",
    "reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.nav_section",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

# Почта (доставка результатов пайплайнов).
# По умолчанию console backend — письма пишутся в консоль, SMTP не нужен.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "office-data-studio@example.com")

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# При запуске тестов файлы уходят во временную папку и не засоряют dev-media.
if "test" in sys.argv:
    MEDIA_ROOT = BASE_DIR / "media_test"

LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:login"

AUTHENTICATION_BACKENDS = [
    "core.auth_backend.EmailAuthBackend",
    "django.contrib.auth.backends.ModelBackend",
]

SESSION_COOKIE_SECURE = os.environ.get("DJANGO_SESSION_COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = os.environ.get("DJANGO_CSRF_COOKIE_SECURE", "false").lower() == "true"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = os.environ.get("DJANGO_SECURE_REFERRER_POLICY", "same-origin")
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "false").lower() == "true"
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "false"
).lower() == "true"
SECURE_HSTS_PRELOAD = os.environ.get("DJANGO_SECURE_HSTS_PRELOAD", "false").lower() == "true"

# -- Лимиты на загружаемые файлы --
# Максимальный размер исходного файла (XLSX/CSV), конфигурируемый через env.
DATA_MAX_FILE_SIZE = int(os.environ.get("DATA_MAX_FILE_SIZE", 20)) * 1024 * 1024
# Ограничение Django на размер multipart-тела согласовано с лимитом файла.
DATA_UPLOAD_MAX_MEMORY_SIZE = DATA_MAX_FILE_SIZE
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_MAX_FILE_SIZE
# Ограничения на таблицу (защита от слишком тяжёлых файлов).
DATA_MAX_ROWS = int(os.environ.get("DATA_MAX_ROWS", 100000))
DATA_MAX_COLUMNS = int(os.environ.get("DATA_MAX_COLUMNS", 200))
DATA_MAX_CELLS = int(os.environ.get("DATA_MAX_CELLS", 5000000))
# Merge: максимум файлов и суммарный размер до обработки.
MAX_MERGE_FILES = int(os.environ.get("MAX_MERGE_FILES", 10))
MAX_TOTAL_MERGE_SIZE = int(os.environ.get("MAX_TOTAL_MERGE_SIZE", 100)) * 1024 * 1024
# Сколько строк показывать в preview таблицы.
PREVIEW_ROWS = 50
# Максимальное число версий в истории отмены (undo/redo).
MAX_UNDO_STEPS = 25
# Время жизни processing-сессий (в часах) для cleanup_processing.
PROCESSING_RETENTION_HOURS = int(os.environ.get("PROCESSING_RETENTION_HOURS", 24))
# Экранирование формул при экспорте CSV (=, +, -, @ в начале ячейки).
SAFE_CSV_EXPORT = os.environ.get("SAFE_CSV_EXPORT", "true").lower() == "true"

# -- Rate limiting (на пользователя, за минуту) --
RATE_LIMIT_UPLOAD_PER_MINUTE = int(os.environ.get("RATE_LIMIT_UPLOAD_PER_MINUTE", 10))
RATE_LIMIT_MERGE_PER_MINUTE = int(os.environ.get("RATE_LIMIT_MERGE_PER_MINUTE", 5))
RATE_LIMIT_WORKFLOW_RUN_PER_MINUTE = int(
    os.environ.get("RATE_LIMIT_WORKFLOW_RUN_PER_MINUTE", 20)
)
RATE_LIMIT_EXPORT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_EXPORT_PER_MINUTE", 30))