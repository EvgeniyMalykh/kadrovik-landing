from .base import *

DEBUG = True

try:
    import debug_toolbar
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
except ImportError:
    pass

INTERNAL_IPS = ['127.0.0.1']
