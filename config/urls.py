from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from apps.documents.views import download_t1

urlpatterns = [
    path("admin/",                      admin.site.urls),
    path("api/v1/",                     include("apps.employees.urls")),
    path("documents/t1/<int:employee_id>/", download_t1, name="document-t1"),
    path("dashboard/",                  include("apps.dashboard.urls", namespace="dashboard")),
    path("dashboard/",                  include("apps.billing.urls")),
    path("vacations/",                  include("apps.vacations.urls", namespace="vacations")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
