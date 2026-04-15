from django.contrib import admin
from django.urls import path, include
from apps.documents.views import download_t1

urlpatterns = [
    path("admin/",                      admin.site.urls),
    path("api/v1/",                     include("apps.employees.urls")),
    path("documents/t1/<int:employee_id>/", download_t1, name="document-t1"),
    path("dashboard/",                  include("apps.dashboard.urls")),
    path("dashboard/",                  include("apps.billing.urls")),
    path("",                            include("apps.dashboard.urls")),
]
