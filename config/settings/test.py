"""
Test settings — extends production with test-specific overrides.
Usage: python manage.py test --settings=config.settings.test
"""
from .production import *

# Allow testserver host used by Django test client
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1', 'app.kadrovik-auto.ru']

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
