from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("employees/", views.employees_list, name="employees"),
    path("employees/add/", views.employee_add, name="employee_add"),
    path("employees/<int:employee_id>/edit/", views.employee_edit, name="employee_edit"),
    path("employees/<int:employee_id>/delete/", views.employee_delete, name="employee_delete"),
    path("employees/<int:employee_id>/t1/", views.download_t1, name="download_t1"),
    path("employees/<int:employee_id>/t2/", views.download_t2, name="download_t2"),
    path("employees/<int:employee_id>/t8/", views.download_t8, name="download_t8"),
    path("employees/<int:employee_id>/t6/", views.download_t6, name="download_t6"),
    path("subscription/", views.subscription, name="subscription"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
]
