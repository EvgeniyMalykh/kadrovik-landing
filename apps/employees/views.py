from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from .models import Employee, Department
from .serializers import EmployeeSerializer, EmployeeCreateSerializer, DepartmentSerializer
from apps.documents.services import generate_t1_pdf


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Department.objects.all()
        return Department.objects.filter(company__members__user=user)


class EmployeeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

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
