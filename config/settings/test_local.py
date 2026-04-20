"""
Local test settings — uses SQLite in-memory for fast tests without PostgreSQL.
Usage: python manage.py test --settings=config.settings.test_local
"""
from .base import *

DEBUG = False

ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1', 'app.kadrovik-auto.ru']

# SQLite in-memory for tests (no PostgreSQL needed)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Use faster password hasher for tests
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Use in-memory email backend
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Disable HTTPS redirects in tests
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Keep CSRF trust
CSRF_TRUSTED_ORIGINS = [
    'http://testserver',
    'https://app.kadrovik-auto.ru',
]

# Logging: quiet for tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'null': {'class': 'logging.NullHandler'},
    },
    'root': {'handlers': ['null'], 'level': 'CRITICAL'},
}

LOGIN_URL = "/dashboard/login/"
DEFAULT_FROM_EMAIL = "test@kadrovik-auto.ru"
