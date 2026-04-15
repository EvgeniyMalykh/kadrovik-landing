from django.contrib import admin
from django.urls import path
from apps.documents.views import download_t1

urlpatterns = [
    path("admin/", admin.site.urls),
    path("documents/t1/<int:employee_id>/", download_t1, name="document-t1"),
]
