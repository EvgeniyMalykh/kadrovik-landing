from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from apps.accounts.models import User
from apps.employees.models import Employee, Department
from apps.companies.models import Company, CompanyMember
from apps.documents.services import generate_t1_pdf, generate_t2_pdf, generate_t8_pdf, generate_t6_pdf
from datetime import date, timedelta


@login_required
def dashboard_home(request):
    return redirect("dashboard:employees")


@login_required
def employees_list(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if member:
        employees = Employee.objects.filter(company=member.company).select_related("department")
        company = member.company
    else:
        employees = Employee.objects.none()
        company = None
    from datetime import date as _date
    return render(request, "dashboard/employees.html", {
        "employees": employees,
        "company": company,
        "today": _date.today().isoformat(),
    })


def _save_employee_from_post(post, employee):
    """Обновляет поля сотрудника из POST-данных."""
    employee.last_name   = post.get("last_name", "")
    employee.first_name  = post.get("first_name", "")
    employee.middle_name = post.get("middle_name", "")
    employee.position    = post.get("position", "")
    employee.salary      = post.get("salary") or None

    hire_date_str = post.get("hire_date")
    employee.hire_date = date.fromisoformat(hire_date_str) if hire_date_str else date.today()

    birth_date_str = post.get("birth_date")
    employee.birth_date = date.fromisoformat(birth_date_str) if birth_date_str else None

    probation_months = post.get("probation_months")
    if probation_months:
        try:
            months = int(probation_months)
            employee.probation_end_date = employee.hire_date + timedelta(days=30 * months)
        except ValueError:
            employee.probation_end_date = None
    else:
        employee.probation_end_date = None

    employee.phone  = post.get("phone", "")
    employee.inn    = post.get("inn", "")
    employee.snils  = post.get("snils", "")
    employee.passport_series      = post.get("passport_series", "")
    employee.passport_number      = post.get("passport_number", "")
    employee.passport_issued_by   = post.get("passport_issued_by", "")
    employee.passport_registration = post.get("passport_registration", "")
    return employee


@login_required
def employee_add(request):
    if request.method == "POST":
        member = CompanyMember.objects.filter(user=request.user).first()
        if not member:
            return HttpResponse("Нет компании", status=400)
        emp = Employee(company=member.company)
        _save_employee_from_post(request.POST, emp)
        emp.save()
        employees = Employee.objects.filter(company=member.company).select_related("department")
        return render(request, "dashboard/partials/employees_table.html", {"employees": employees})
    return render(request, "dashboard/partials/employee_form.html")


@login_required
def employee_edit(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    if request.method == "POST":
        _save_employee_from_post(request.POST, employee)
        employee.save()
        employees = Employee.objects.filter(company=member.company).select_related("department")
        return render(request, "dashboard/partials/employees_table.html", {"employees": employees})
    return render(request, "dashboard/partials/employee_edit_form.html", {
        "emp": employee,
        "birth_date_str": employee.birth_date.strftime("%Y-%m-%d") if employee.birth_date else "",
        "hire_date_str": employee.hire_date.strftime("%Y-%m-%d") if employee.hire_date else "",
    })


@login_required
@require_POST
def employee_delete(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    employee.delete()
    employees = Employee.objects.filter(company=member.company).select_related("department")
    return render(request, "dashboard/partials/employees_table.html", {"employees": employees})


@login_required
def download_t1(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    pdf = generate_t1_pdf(employee, request.GET.get("order", "П-001"))
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"T1_{employee.last_name}.pdf\""
    return r


@login_required
def download_t2(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    pdf = generate_t2_pdf(employee)
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"T2_{employee.last_name}.pdf\""
    return r


@login_required
def download_t8(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    pdf = generate_t8_pdf(employee, request.GET.get("order", "У-001"))
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"T8_{employee.last_name}.pdf\""
    return r


@login_required
def download_t6(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from datetime import date as dt
    v_start = dt.fromisoformat(request.GET.get("start", dt.today().isoformat()))
    v_end   = dt.fromisoformat(request.GET.get("end",   dt.today().isoformat()))
    pdf = generate_t6_pdf(employee, v_start, v_end, request.GET.get("order", "О-001"))
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"T6_{employee.last_name}.pdf\""
    return r


@login_required
def subscription(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    sub = None
    payments = []
    if member:
        sub = getattr(member.company, "subscription", None)
        payments = member.company.payments.all()[:10]
    return render(request, "dashboard/subscription.html", {"sub": sub, "payments": payments})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:employees")
    if request.method == "POST":
        email    = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, email=email, password=password)
        if user:
            login(request, user)
            return redirect("dashboard:employees")
        return render(request, "dashboard/login.html", {"error": "Неверный email или пароль"})
    return render(request, "dashboard/login.html")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:employees")
    if request.method == "POST":
        email        = request.POST.get("email")
        password     = request.POST.get("password")
        company_name = request.POST.get("company_name")
        if User.objects.filter(email=email).exists():
            return render(request, "dashboard/register.html", {"error": "Email уже зарегистрирован"})
        user = User.objects.create_user(username=email, email=email, password=password)
        company = Company.objects.create(name=company_name, owner=user)
        CompanyMember.objects.create(user=user, company=company, role="owner")
        login(request, user)
        return redirect("dashboard:employees")
    return render(request, "dashboard/register.html")


def logout_view(request):
    logout(request)
    return redirect("dashboard:login")
