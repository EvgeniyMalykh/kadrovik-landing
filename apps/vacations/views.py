from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from apps.companies.models import Company, CompanyMember
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
        # Создаём запись в журнале документов
        try:
            from apps.documents.models import Document
            from apps.billing.services import PLANS
            sub = getattr(company, "subscription", None)
            plan_key = sub.plan if sub else "start"
            plan_data = PLANS.get(plan_key, PLANS["start"])
            # Авто-номер: следующий по типу vacation для этой компании
            import re as _re_doc
            existing_nums = Document.objects.filter(company=company, doc_type="vacation").values_list("number", flat=True)
            max_n = 0
            for num in existing_nums:
                if num:
                    m = _re_doc.search(r"(\d+)", str(num))
                    if m:
                        max_n = max(max_n, int(m.group(1)))
            doc_number = f"О-{max_n + 1}"
            doc = Document.objects.create(
                company=company,
                employee=emp,
                doc_type="vacation",
                number=doc_number,
                date=start,
                extra_data={
                    "vacation_type": vtype,
                    "start_date": str(start),
                    "end_date": str(end),
                    "days_count": str(v.days_count),
                    "reason": reason,
                },
            )
            v.document = doc
            v.save(update_fields=["document"])
        except Exception as _doc_err:
            pass  # Не ломаем сохранение отпуска если документ не создался
        # Return JSON with vacation id so JS can show print button
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').startswith('application/json'):
            return JsonResponse({"success": True, "vacation_id": v.id, "employee_name": emp.full_name})
        # Fallback: return updated vacation list partial
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


# ─── ПУБЛИЧНАЯ ФОРМА ДЛЯ РАБОТНИКА ──────────────────────────────────────────

VACATION_TYPE_LABELS = {
    'annual':      'Ежегодный оплачиваемый',
    'unpaid':      'За свой счёт (без сохранения зарплаты)',
    'educational': 'Учебный',
    'maternity':   'Декретный',
}

def vacation_request_public(request, company_id):
    """Публичная форма заявления на отпуск для работника (без авторизации)."""
    company = get_object_or_404(Company, id=company_id)

    if request.method == "POST":
        last_name   = request.POST.get("last_name", "").strip()
        first_name  = request.POST.get("first_name", "").strip()
        middle_name = request.POST.get("middle_name", "").strip()
        position    = request.POST.get("position", "").strip()
        vtype       = request.POST.get("vacation_type", "annual")
        start_str   = request.POST.get("start_date", "").strip()
        end_str     = request.POST.get("end_date", "").strip()
        reason      = request.POST.get("reason", "").strip()

        form_data = {
            "last_name": last_name, "first_name": first_name,
            "middle_name": middle_name, "position": position,
            "start_date": start_str, "end_date": end_str, "reason": reason,
        }

        # Validation
        if not last_name or not first_name or not position:
            return render(request, "dashboard/vacation_request_form.html", {
                "company": company,
                "error": "Пожалуйста, заполните обязательные поля: Фамилия, Имя, Должность.",
                "form_data": form_data,
            })

        start = _parse_date(start_str)
        end   = _parse_date(end_str)
        if not start or not end:
            return render(request, "dashboard/vacation_request_form.html", {
                "company": company,
                "error": "Пожалуйста, введите даты в формате ДД.ММ.ГГГГ.",
                "form_data": form_data,
            })
        if end < start:
            return render(request, "dashboard/vacation_request_form.html", {
                "company": company,
                "error": "Дата окончания не может быть раньше даты начала.",
                "form_data": form_data,
            })

        # Ищем сотрудника по ФИО в данной компании
        emp_qs = Employee.objects.filter(
            company=company,
            last_name__iexact=last_name,
            first_name__iexact=first_name,
        )
        if middle_name:
            emp_qs = emp_qs.filter(middle_name__iexact=middle_name)

        emp = emp_qs.first()

        if not emp:
            # Создаём временную запись сотрудника если не найден
            # (или можно отклонить — но лучше создать черновик)
            from apps.employees.models import Department
            emp = Employee.objects.create(
                company=company,
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
                position=position,
                status='working',
            )

        v = Vacation.objects.create(
            employee=emp,
            vacation_type=vtype,
            start_date=start,
            end_date=end,
            reason=reason,
        )

        days = (end - start).days + 1
        return render(request, "dashboard/vacation_request_success.html", {
            "company": company,
            "last_name": last_name,
            "first_name": first_name,
            "middle_name": middle_name,
            "vacation_type_display": VACATION_TYPE_LABELS.get(vtype, vtype),
            "start_date": start.strftime("%d.%m.%Y"),
            "end_date": end.strftime("%d.%m.%Y"),
            "days_count": days,
            "reason": reason,
            "company_id": company_id,
        })

    # GET
    return render(request, "dashboard/vacation_request_form.html", {
        "company": company,
        "form_data": {},
    })
