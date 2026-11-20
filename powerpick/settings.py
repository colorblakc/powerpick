"""Django settings for the Power Pick shop.

Secrets and deployment values come from the environment (or a local .env file), never from this file.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
# Accept the shorter variable names some local .env files use for the same keys.
for canonical, alias in (("GROQ_API_KEY", "GROQ_API"), ("RAZORPAY_KEY_ID", "RZP_KEY_ID"), ("RAZORPAY_KEY_SECRET", "RZP_KEY_SECRET")):
    if not os.environ.get(canonical) and os.environ.get(alias):
        os.environ[canonical] = os.environ[alias]

# Developers can run the shop locally. A hosted shop must supply its own secret.
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or ("development-only" if DEBUG else "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY before deployment.")
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split()
# Cookies are only marked secure outside debug mode, because local development runs over plain HTTP.
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG
# Behind a hosting proxy the shop sees plain HTTP; this header tells Django the visitor really used HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Everything that must survive a restart (database and uploaded photos) lives under DATA_DIR.
# On a container host, point DATA_DIR at the folder the host keeps between deployments.
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR))


INSTALLED_APPS = [
    'store',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # serves the collected static files without a separate web server
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'powerpick.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'store.context.shell',
            ],
        },
    },
]

WSGI_APPLICATION = 'powerpick.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'db.sqlite3',
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# STATIC_ROOT is where collectstatic gathers the shop's files; MEDIA_ROOT holds product photos uploaded by staff.
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = DATA_DIR / "media"
MEDIA_URL = "/media/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Public contact details shown on the Contact page. Set the variables to replace these sample values.
STORE_CONTACT_NAME = os.environ.get("STORE_CONTACT_NAME", "Janhavi Pravin Jivanwal, Founder")
STORE_CONTACT_EMAIL = os.environ.get("STORE_CONTACT_EMAIL", "janhavi@powerpick.example")
STORE_CONTACT_PHONE = os.environ.get("STORE_CONTACT_PHONE", "+91 98765 43210")
STORE_CONTACT_ADDRESS = os.environ.get("STORE_CONTACT_ADDRESS", "Power Pick, 12 Sinhgad Road\nVadgaon Budruk, Pune\nMaharashtra 411041, India")

AUTHENTICATION_BACKENDS = ["store.backends.EmailOrUsernameBackend"]
LOGIN_URL = "login"
