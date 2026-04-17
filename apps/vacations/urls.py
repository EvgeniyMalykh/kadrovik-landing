from django.urls import path
from . import views

app_name = "vacations"

urlpatterns = [
    path("", views.vacation_list, name="list"),
    path("add/", views.vacation_add, name="add"),
    path("<int:vacation_id>/delete/", views.vacation_delete, name="delete"),
    path("<int:vacation_id>/print/", views.vacation_print, name="print"),
    # Публичная форма для работника (без авторизации)
    path("request/<int:company_id>/", views.vacation_request_public, name="request_public"),
    # График отпусков
    path("schedule/history/", views.vacation_schedule_history, name="schedule_history"),
    path("schedule/", views.vacation_schedule, name="schedule"),
    path("schedule/save/", views.vacation_schedule_save, name="schedule_save"),
    path("schedule/pdf/", views.vacation_schedule_pdf, name="schedule_pdf"),
]
