from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include('apps.accounts.urls')),
    path('api/companies/', include('apps.companies.urls')),
    path('api/employees/', include('apps.employees.urls')),
    path('api/documents/', include('apps.documents.urls')),
    path('api/vacations/', include('apps.vacations.urls')),
    path('api/events/', include('apps.events.urls')),
    path('api/billing/', include('apps.billing.urls')),
]
