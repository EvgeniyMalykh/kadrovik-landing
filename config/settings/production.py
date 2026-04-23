from .base import *
import os

DEBUG = False

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

# Security
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = False  # nginx handles SSL redirect
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [
    'https://app.kadrovik-auto.ru',
    'https://kadrovik-auto.ru',
    'https://www.kadrovik-auto.ru',
]

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'kadrovik_db'),
        'USER': os.environ.get('DB_USER', 'kadrovik_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'db'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Redis / Celery
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')

# Static & media
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': '/app/logs/django.log',
        },
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}

# Email — через Redis relay (SMTP с хоста, т.к. контейнер не имеет доступа к SMTP)
EMAIL_BACKEND = "apps.accounts.email_backend.RedisRelayEmailBackend"
REDIS_RELAY_URL = os.environ.get("REDIS_RELAY_URL", "redis://redis:6379/2")
GAS_URL = os.environ.get("GAS_URL", "")
EMAIL_RELAY_QUEUE_KEY = "email_relay_queue"
DEFAULT_FROM_EMAIL = "Кадровый автопилот <evgeniymalykh@gmail.com>"
SERVER_EMAIL = "evgeniymalykh@gmail.com"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "evgeniymalykh@gmail.com"
EMAIL_HOST_PASSWORD = "dchpmpvepvhphulg"

LOGIN_URL = "/dashboard/login/"
REPLY_TO_EMAIL = "evgeniymalykh@gmail.com"

# ЮKassa
YUKASSA_SHOP_ID  = '1332087'
YUKASSA_SECRET_KEY = 'live_OmueBYSyeOrmeDFAq6FSnp3sD7h_ZDJrLeXAxPkpshg'

# Google Sheets (Service Account через gspread)
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '')
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '1JS9iTtGaBCC2ElW-BaGRiLZh10-T8F8NJF6_ZLMdewg')
