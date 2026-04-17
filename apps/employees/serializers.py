from rest_framework import serializers
from .models import Employee, Department
from apps.events.models import HREvent
from apps.documents.models import Document
from apps.companies.models import Company


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name', 'company']


class EmployeeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    full_name = serializers.CharField(read_only=True)
    short_name = serializers.CharField(read_only=True)

    class Meta:
        model = Employee
        fields = '__all__'


class EmployeeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = '__all__'


class HREventSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)

    class Meta:
        model = HREvent
        fields = ['id', 'employee', 'employee_name', 'event_type', 'event_type_display',
                  'event_date', 'notify_days_before', 'notified', 'notified_at', 'created_at']
        read_only_fields = ['notified', 'notified_at', 'created_at']


class DocumentSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    doc_type_display = serializers.CharField(source='get_doc_type_display', read_only=True)

    class Meta:
        model = Document
        fields = ['id', 'employee', 'employee_name', 'doc_type', 'doc_type_display',
                  'number', 'date', 'created_at']


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'inn', 'ogrn', 'kpp', 'legal_address',
                  'director_name', 'director_position', 'phone', 'email']
        read_only_fields = fields
