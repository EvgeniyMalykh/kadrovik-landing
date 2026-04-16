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
    from apps.billing.models import Subscription

def subscription_required(view_func):
    """Декоратор: проверяет активную подписку. При истечении — редирект на тарифы."""
    from functools import wraps
    from django.contrib import messages
    from django.shortcuts import redirect
    from apps.billing.models import Subscription as _Sub
    from apps.companies.models import CompanyMember as _CM
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        member = _CM.objects.filter(user=request.user).first()
        if not member:
            return view_func(request, *args, **kwargs)
        sub = getattr(member.company, "subscription", None)
        if sub and not sub.is_active:
            messages.error(request, "Подписка истекла. Выберите тариф для продолжения работы.")
            return redirect("dashboard:subscription")
        return view_func(request, *args, **kwargs)
    return wrapper


    from django.utils import timezone
    import datetime as _dt
    sub = getattr(company, "subscription", None) if company else None
    # Для старых аккаунтов без подписки — создаём trial
    if company and not sub:
        sub = Subscription.objects.create(
            company=company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + _dt.timedelta(days=7),
            max_employees=10,
        )
    # Оставшиеся дни trial
    trial_days_left = None
    if sub and sub.plan == Subscription.Plan.TRIAL and sub.expires_at:
        delta = sub.expires_at - timezone.now()
        trial_days_left = max(0, delta.days)
    # Если подписка истекла — редирект на тарифы
    if sub and not sub.is_active:
        from django.contrib import messages
        messages.error(request, "Ваша подписка истекла. Выберите тариф для продолжения работы.")
        return redirect("dashboard:subscription")
    return render(request, "dashboard/employees.html", {
        "employees": employees,
        "company": company,
        "today": _date.today().isoformat(),
        "sub": sub,
        "trial_days_left": trial_days_left,
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
@subscription_required
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
@subscription_required
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
    from datetime import date as _date
    employees = Employee.objects.filter(company=member.company).select_related("department")
    return render(request, "dashboard/partials/employees_table.html", {
        "employees": employees,
        "today": _date.today().strftime("%Y-%m-%d"),
    })


@login_required
@subscription_required
def download_t1(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    pdf = generate_t1_pdf(employee, request.GET.get("order", "П-001"))
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"T1_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_t2(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    pdf = generate_t2_pdf(employee)
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"T2_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_t8(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    pdf = generate_t8_pdf(employee, request.GET.get("order", "У-001"))
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"T8_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
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
        # Создаём пробную подписку на 7 дней
        from apps.billing.models import Subscription
        from django.utils import timezone
        import datetime
        Subscription.objects.create(
            company=company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + datetime.timedelta(days=7),
            max_employees=10,
        )
        login(request, user)
        return redirect("dashboard:employees")
    return render(request, "dashboard/register.html")


def logout_view(request):
    logout(request)
    return redirect("dashboard:login")


@login_required
@subscription_required
def download_t5(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_t5_pdf
    new_position = request.GET.get("position", employee.position or "Новая должность")
    new_salary   = request.GET.get("salary")
    pdf = generate_t5_pdf(employee, new_position, new_salary, request.GET.get("order", "ПР-001"))
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"T5_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_salary_change(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_salary_change_pdf
    new_salary = request.GET.get("salary", str(employee.salary or "0"))
    pdf = generate_salary_change_pdf(employee, new_salary, request.GET.get("order", "З-001"))
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"SalaryChange_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_work_certificate(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_work_certificate_pdf
    pdf = generate_work_certificate_pdf(employee)
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"Certificate_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_labor_contract(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_labor_contract_pdf
    pdf = generate_labor_contract_pdf(employee)
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"LaborContract_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_gph_contract(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_gph_contract_pdf
    pdf = generate_gph_contract_pdf(employee)
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"GPH_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_gph_act(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_gph_act_pdf
    pdf = generate_gph_act_pdf(employee)
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"GPH_Act_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_t13(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return HttpResponse("Нет компании", status=400)
    from apps.documents.services import generate_t13_pdf
    employees = list(Employee.objects.filter(company=member.company))
    if not employees:
        return HttpResponse("Нет сотрудников", status=400)
    from datetime import date
    today = date.today()
    try:
        y = int(request.GET.get("year", today.year))
        m = int(request.GET.get("month", today.month))
        if not (1 <= m <= 12): m = today.month
        if not (2000 <= y <= 2100): y = today.year
    except (ValueError, TypeError):
        y, m = today.year, today.month
    pdf = generate_t13_pdf(employees, y, m)
    r = HttpResponse(pdf, content_type="application/pdf")
    fname = "%04d_%02d" % (y, m)
    r["Content-Disposition"] = "attachment; filename=T13_" + fname + ".pdf"
    return r


@login_required
def company_profile(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    company = member.company
    saved = False
    if request.method == "POST":
        company.name             = request.POST.get("name", company.name)
        company.inn              = request.POST.get("inn", company.inn)
        company.ogrn             = request.POST.get("ogrn", company.ogrn)
        company.kpp              = request.POST.get("kpp", company.kpp)
        company.okpo             = request.POST.get("okpo", company.okpo)
        company.legal_address    = request.POST.get("legal_address", company.legal_address)
        company.actual_address   = request.POST.get("actual_address", company.actual_address)
        company.director_name    = request.POST.get("director_name", company.director_name)
        company.director_position = request.POST.get("director_position", company.director_position)
        company.phone            = request.POST.get("phone", company.phone)
        company.email            = request.POST.get("email", company.email)
        company.save()
        saved = True
    return render(request, "dashboard/company.html", {"company": company, "saved": saved})
