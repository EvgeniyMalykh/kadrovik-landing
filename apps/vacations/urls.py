from django.urls import path
from . import views

app_name = "vacations"

urlpatterns = [
    path("", views.vacation_list, name="list"),
    path("add/", views.vacation_add, name="add"),
    path("<int:vacation_id>/delete/", views.vacation_delete, name="delete"),
    path("<int:vacation_id>/print/", views.vacation_print, name="print"),
]
