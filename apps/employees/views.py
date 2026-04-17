from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from .models import Employee, Department
from .serializers import (
    EmployeeSerializer, EmployeeCreateSerializer, DepartmentSerializer,
    HREventSerializer, DocumentSerializer, CompanySerializer,
)
from .permissions import HasAPIAccess
from apps.documents.services import generate_t1_pdf
from apps.events.models import HREvent
from apps.documents.models import Document
from apps.companies.models import Company, CompanyMember


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    permission_classes = [HasAPIAccess]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Department.objects.all()
        return Department.objects.filter(company__members__user=user)


class EmployeeViewSet(viewsets.ModelViewSet):
    permission_classes = [HasAPIAccess]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Employee.objects.select_related("department", "company").all()
        return Employee.objects.select_related(
            "department", "company"
        ).filter(company__members__user=user)

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return EmployeeCreateSerializer
        return EmployeeSerializer

    @action(detail=True, methods=["get"], url_path="t1")
    def download_t1(self, request, pk=None):
        employee = self.get_object()
        order_number = request.query_params.get("order", f"П-{pk}")
        try:
            pdf_bytes = generate_t1_pdf(employee, order_number)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        filename = f"T1_{employee.last_name}_{pk}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class HREventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasAPIAccess]
    serializer_class = HREventSerializer

    def get_queryset(self):
        member = CompanyMember.objects.filter(user=self.request.user).first()
        if not member:
            return HREvent.objects.none()
        return HREvent.objects.filter(company=member.company).select_related('employee').order_by('-event_date')


class DocumentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasAPIAccess]
    serializer_class = DocumentSerializer

    def get_queryset(self):
        member = CompanyMember.objects.filter(user=self.request.user).first()
        if not member:
            return Document.objects.none()
        return Document.objects.filter(company=member.company).select_related('employee').order_by('-created_at')


class CompanyAPIViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasAPIAccess]
    serializer_class = CompanySerializer

    def get_queryset(self):
        member = CompanyMember.objects.filter(user=self.request.user).first()
        if not member:
            return Company.objects.none()
        return Company.objects.filter(id=member.company_id)
