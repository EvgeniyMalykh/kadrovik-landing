from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("chat-support/",  views.chat_support,  name="chat_support"),
    path("chat-history/",  views.chat_history,  name="chat_history"),
    path("chat-webhook/",  views.chat_webhook,  name="chat_webhook"),
    path("chat-poll/",     views.chat_poll,     name="chat_poll"),


    path("", views.dashboard_home, name="home"),
    path("employees/", views.employees_list, name="employees"),
    path("employees/add/", views.employee_add, name="employee_add"),
    path("employees/<int:employee_id>/edit/", views.employee_edit, name="employee_edit"),
    path("documents/<int:doc_id>/delete/", views.delete_document, name="delete_document"),
    path("employees/<int:employee_id>/delete/", views.employee_delete, name="employee_delete"),
    # Кадровые приказы
    path("employees/<int:employee_id>/t1/", views.download_t1, name="download_t1"),
    path("employees/<int:employee_id>/t2/", views.download_t2, name="download_t2"),
    path("employees/<int:employee_id>/t5/", views.download_t5, name="download_t5"),
    path("employees/<int:employee_id>/t6/", views.download_t6, name="download_t6"),
    path("employees/<int:employee_id>/t8/", views.download_t8, name="download_t8"),
    path("employees/<int:employee_id>/salary-change/", views.download_salary_change, name="download_salary_change"),
    path("employees/<int:employee_id>/transfer-order/", views.download_transfer_order, name="download_transfer_order"),
    path("employees/<int:employee_id>/dismissal-order/", views.download_dismissal_order, name="download_dismissal_order"),
    path("employees/<int:employee_id>/bonus-order/", views.download_bonus_order, name="download_bonus_order"),
    path("employees/<int:employee_id>/disciplinary-order/", views.download_disciplinary_order, name="download_disciplinary_order"),
    path("employees/<int:employee_id>/certificate/", views.download_work_certificate, name="download_certificate"),
    path("employees/<int:employee_id>/labor-contract/", views.download_labor_contract, name="download_labor_contract"),
    path("employees/<int:employee_id>/gph-contract/", views.download_gph_contract, name="download_gph_contract"),
    path("employees/<int:employee_id>/gph-act/", views.download_gph_act, name="download_gph_act"),
    # Табель — на всю компанию
    # Excel export
    path("export/employees/", views.export_employees_excel, name="export_employees_excel"),
    path("export/timesheet/", views.export_timesheet_excel, name="export_timesheet_excel"),
    path("t13/", views.download_t13, name="download_t13"),
    path("timesheet/", views.timesheet_edit, name="timesheet_edit"),
    path("timesheet/save/", views.timesheet_save, name="timesheet_save"),
    # Формы и документы
    path("documents/<int:doc_id>/delete/", views.delete_document, name="delete_document"),
    path("forms/", views.forms_list, name="forms_list"),
    path("forms/api/employee/<int:employee_id>/", views.employee_data_api, name="employee_data_api"),
    path("forms/<str:doc_type>/save/", views.form_save, name="form_save"),
    path("forms/<str:doc_type>/", views.form_editor, name="form_editor"),
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
    # Команда
    path("team/", views.team_list, name="team_list"),
    path("team/invite/", views.team_invite, name="team_invite"),
    path("team/member/<int:member_id>/remove/", views.team_member_remove, name="team_member_remove"),
    path("team/invite/<int:invite_id>/cancel/", views.team_invite_cancel, name="team_invite_cancel"),
    path("invite/<uuid:token>/", views.invite_accept, name="invite_accept"),
    # API
    path("api/", views.api_settings, name="api_settings"),
    path("api/token/regenerate/", views.api_token_regenerate, name="api_token_regenerate"),
    # Шаблоны документов
    path("templates/", views.document_templates, name="document_templates"),
    path("sfr/", views.sfr_export, name="sfr_export"),
    path("templates/<str:doc_type>/upload/", views.document_template_upload, name="document_template_upload"),
    path("templates/<str:doc_type>/delete/", views.document_template_delete, name="document_template_delete"),
    path("templates/<str:doc_type>/download/<int:employee_id>/", views.document_template_download, name="document_template_download"),
]
