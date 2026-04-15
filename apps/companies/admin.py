from django.contrib import admin
from .models import Company, CompanyMember

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'inn', 'director_name', 'created_at')
    search_fields = ('name', 'inn')

@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ('company', 'user', 'role')