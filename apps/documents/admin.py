from django.contrib import admin
from .models import Document

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('doc_type', 'employee', 'number', 'date', 'created_at')
    list_filter = ('doc_type', 'company')
    search_fields = ('number', 'employee__last_name')