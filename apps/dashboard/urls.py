from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),
    path('employees/', views.employees_list, name='employees'),
    path('employees/add/', views.employee_add, name='employee_add'),
    path('employees/<int:employee_id>/t1/', views.download_t1, name='download_t1'),
    path('subscription/', views.subscription, name='subscription'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
]
