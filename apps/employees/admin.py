from django.contrib import admin
from .models import Employee, Department

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'company', 'position', 'status', 'hire_date')
    list_filter = ('status', 'company', 'contract_type')
    search_fields = ('last_name', 'first_name', 'inn')

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'company')