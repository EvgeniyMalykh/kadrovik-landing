from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from apps.companies.models import CompanyMember
from apps.employees.models import Employee
from .models import Vacation
import re


def _parse_date(val):
    """Parse DD.MM.YYYY or YYYY-MM-DD"""
    if not val:
        return None
    val = val.strip()
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", val)
    if m:
        from datetime import date
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m2 = re.match(r"^\d{4}-\d{2}-\d{2}$", val)
    if m2:
        from datetime import date
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None


@login_required
def vacation_list(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    company = member.company
    vacations = Vacation.objects.filter(
        employee__company=company
    ).select_related("employee")
    employees = Employee.objects.filter(company=company).order_by("last_name")
    return render(request, "dashboard/vacations.html", {
        "vacations": vacations,
        "employees": employees,
        "company": company,
    })


@login_required
def vacation_add(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return JsonResponse({"error": "no company"}, status=400)
    company = member.company
    employees = list(Employee.objects.filter(company=company)
                     .order_by("last_name")
                     .values("id", "last_name", "first_name", "middle_name", "position"))

    if request.method == "POST":
        emp_id       = request.POST.get("employee_id")
        vtype        = request.POST.get("vacation_type", "annual")
        start_str    = request.POST.get("start_date")
        end_str      = request.POST.get("end_date")
        reason       = request.POST.get("reason", "").strip()

        try:
            emp = Employee.objects.get(id=emp_id, company=company)
        except Employee.DoesNotExist:
            return JsonResponse({"error": "employee not found"}, status=400)

        start = _parse_date(start_str)
        end   = _parse_date(end_str)
        if not start or not end or end < start:
            return JsonResponse({"error": "invalid dates"}, status=400)

        v = Vacation.objects.create(
            employee=emp,
            vacation_type=vtype,
            start_date=start,
            end_date=end,
            reason=reason,
        )
        # Return updated vacation list partial
        vacations = Vacation.objects.filter(
            employee__company=company
        ).select_related("employee")
        return render(request, "dashboard/partials/vacations_table.html",
                      {"vacations": vacations})

    # GET — return form partial for drawer
    return render(request, "dashboard/partials/vacation_form.html",
                  {"employees": employees})


@login_required
@require_POST
def vacation_delete(request, vacation_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return JsonResponse({"error": "no company"}, status=400)
    v = get_object_or_404(Vacation, id=vacation_id, employee__company=member.company)
    v.delete()
    vacations = Vacation.objects.filter(
        employee__company=member.company
    ).select_related("employee")
    return render(request, "dashboard/partials/vacations_table.html",
                  {"vacations": vacations})


@login_required
def vacation_print(request, vacation_id):
    """Страница для печати заявления об отпуске."""
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    v = get_object_or_404(Vacation, id=vacation_id, employee__company=member.company)
    company = member.company
    return render(request, "dashboard/vacation_print.html", {
        "v": v,
        "company": company,
    })
