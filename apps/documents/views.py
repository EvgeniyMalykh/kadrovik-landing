from django.http import HttpResponse, Http404
from django.contrib.admin.views.decorators import staff_member_required
from apps.employees.models import Employee
from .services import generate_t1_pdf


@staff_member_required
def download_t1(request, employee_id: int):
    try:
        employee = Employee.objects.select_related("department").get(pk=employee_id)
    except Employee.DoesNotExist:
        raise Http404("Сотрудник не найден")

    order_number = request.GET.get("order", f"П-{employee_id}")
    pdf_bytes = generate_t1_pdf(employee, order_number)

    filename = f"T1_{employee.last_name}_{employee_id}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
