from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("employees/", views.employees_list, name="employees"),
    path("employees/add/", views.employee_add, name="employee_add"),
    path("employees/<int:employee_id>/edit/", views.employee_edit, name="employee_edit"),
    path("employees/<int:employee_id>/delete/", views.employee_delete, name="employee_delete"),
    # Кадровые приказы
    path("employees/<int:employee_id>/t1/", views.download_t1, name="download_t1"),
    path("employees/<int:employee_id>/t2/", views.download_t2, name="download_t2"),
    path("employees/<int:employee_id>/t5/", views.download_t5, name="download_t5"),
    path("employees/<int:employee_id>/t6/", views.download_t6, name="download_t6"),
    path("employees/<int:employee_id>/t8/", views.download_t8, name="download_t8"),
    path("employees/<int:employee_id>/salary-change/", views.download_salary_change, name="download_salary_change"),
    path("employees/<int:employee_id>/certificate/", views.download_work_certificate, name="download_certificate"),
    path("employees/<int:employee_id>/labor-contract/", views.download_labor_contract, name="download_labor_contract"),
    path("employees/<int:employee_id>/gph-contract/", views.download_gph_contract, name="download_gph_contract"),
    path("employees/<int:employee_id>/gph-act/", views.download_gph_act, name="download_gph_act"),
    # Табель — на всю компанию
    path("t13/", views.download_t13, name="download_t13"),
    path("timesheet/", views.timesheet_edit, name="timesheet_edit"),
    path("timesheet/save/", views.timesheet_save, name="timesheet_save"),
    # Подписка и auth
    path("company/", views.company_profile, name="company"),
    path("subscription/", views.subscription, name="subscription"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("forgot-password/", views.forgot_password_view, name="forgot_password"),
    path("reset-password/<str:token>/", views.reset_password_view, name="reset_password"),
    path("change-password/", views.change_password_view, name="change_password"),
    # Email верификация
    path("verify-email/<uuid:token>/", views.verify_email_view, name="verify_email"),
    path("resend-verification/", views.resend_verification_view, name="resend_verification"),
]
