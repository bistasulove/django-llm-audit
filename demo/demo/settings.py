"""Django settings for the django-llm-audit demo project.

This project exists only to develop, test, and showcase the ``llm_audit`` plugin.
It is excluded from the published PyPI package.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load secrets (e.g. ANTHROPIC_API_KEY) from a repo-root .env before they are read
# below. BASE_DIR is the demo/ dir, so the repo root is one level up.
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = "django-insecure-demo-key-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # The plugin under development.
    "llm_audit",
    # The demo app.
    "store",
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

ROOT_URLCONF = "demo.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "demo.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# django-llm-audit configuration.
LLM_AUDIT = {
    "BACKEND": "llm_audit.backends.openai.OpenAIBackend",
    "API_KEY": os.environ.get("OPENAI_API_KEY", ""),
    "MODEL": os.environ.get("OPENAI_LLM_MODEL", ""),
    # "BACKEND": "llm_audit.backends.anthropic.AnthropicBackend",
    # "API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
    # "MODEL": os.environ.get("ANTHROPIC_LLM_MODEL", ""),
    "MAX_TOKENS": 1024,
    "CHUNK_TOKEN_THRESHOLD": 3000,
    "DEFAULT_RECORD_LIMIT": 50,
}
