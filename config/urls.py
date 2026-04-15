from django.contrib import admin
from django.urls import path, include
from apps.documents.views import download_t1

urlpatterns = [
    path("admin/", admin.site.urls),

    # API v1
    path("api/v1/", include("apps.employees.urls")),

    # Прямая ссылка на PDF (для теста в браузере)
    path("documents/t1/<int:employee_id>/", download_t1, name="document-t1"),
]
