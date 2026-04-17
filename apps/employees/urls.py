from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import (
    EmployeeViewSet, DepartmentViewSet,
    HREventViewSet, DocumentViewSet, CompanyAPIViewSet,
)

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("departments", DepartmentViewSet, basename="department")
router.register("events", HREventViewSet, basename="event")
router.register("documents", DocumentViewSet, basename="document")
router.register("company", CompanyAPIViewSet, basename="company")

urlpatterns = [
    path('auth/token/', obtain_auth_token, name='api_token_auth'),
    path('', include(router.urls)),
]
