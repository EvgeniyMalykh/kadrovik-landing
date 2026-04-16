import re
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



def _parse_date_flexible(val):
    """Parse date from DD.MM.YYYY or YYYY-MM-DD format. Returns date or None."""
    if not val or not val.strip():
        return None
    val = val.strip()
    # Try DD.MM.YYYY
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", val)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    # Try YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None


def _save_employee_from_post(post, employee):
    """Обновляет поля сотрудника из POST-данных."""
    employee.last_name   = post.get("last_name", "")
    employee.first_name  = post.get("first_name", "")
    employee.middle_name = post.get("middle_name", "")
    employee.position    = post.get("position", "")
    employee.salary      = post.get("salary") or None

    # Структурное подразделение
    dept_id = post.get("department_id")
    dept_name_new = post.get("department_new", "").strip()
    if dept_name_new and hasattr(employee, 'company') and employee.company:
        from apps.employees.models import Department as _Dept
        dept, _ = _Dept.objects.get_or_create(company=employee.company, name=dept_name_new)
        employee.department = dept
    elif dept_id:
        from apps.employees.models import Department as _Dept
        try:
            employee.department = _Dept.objects.get(id=int(dept_id))
        except (_Dept.DoesNotExist, ValueError):
            employee.department = None
    else:
        employee.department = None

    hire_date_str = post.get("hire_date")
    employee.hire_date = _parse_date_flexible(hire_date_str) or date.today()

    birth_date_str = post.get("birth_date")
    employee.birth_date = _parse_date_flexible(birth_date_str)

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
    employee.email  = post.get("email", "")
    employee.inn    = post.get("inn", "")
    employee.snils  = post.get("snils", "")
    employee.passport_series        = post.get("passport_series", "")
    employee.passport_number        = post.get("passport_number", "")
    employee.passport_issued_by     = post.get("passport_issued_by", "")
    employee.passport_registration  = post.get("passport_registration", "")
    employee.personnel_number       = post.get("personnel_number", "")
    employee.status                 = post.get("status", "active")
    employee.contract_type          = post.get("contract_type", "permanent")

    passport_issued_date_str = post.get("passport_issued_date")
    employee.passport_issued_date = _parse_date_flexible(passport_issued_date_str)

    contract_end_str = post.get("contract_end_date")
    employee.contract_end_date = _parse_date_flexible(contract_end_str)

    fire_date_str = post.get("fire_date")
    employee.fire_date = _parse_date_flexible(fire_date_str)

    probation_end_str = post.get("probation_end_date")
    if probation_end_str:
        employee.probation_end_date = _parse_date_flexible(probation_end_str)
    elif not post.get("probation_end_date") and post.get("probation_months"):
        pass  # уже обработано выше
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
    member = CompanyMember.objects.filter(user=request.user).first()
    departments = []
    if member:
        from apps.employees.models import Department as _Dept
        departments = list(_Dept.objects.filter(company=member.company).values('id', 'name'))
    return render(request, "dashboard/partials/employee_form.html", {"departments": departments})


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
    from apps.employees.models import Department as _Dept
    departments = list(_Dept.objects.filter(company=member.company).values('id', 'name'))
    return render(request, "dashboard/partials/employee_edit_form.html", {
        "emp": employee,
        "birth_date_str":           employee.birth_date.strftime("%d.%m.%Y") if employee.birth_date else "",
        "hire_date_str":            employee.hire_date.strftime("%d.%m.%Y") if employee.hire_date else "",
        "probation_end_str":        employee.probation_end_date.strftime("%d.%m.%Y") if employee.probation_end_date else "",
        "contract_end_str":         employee.contract_end_date.strftime("%d.%m.%Y") if employee.contract_end_date else "",
        "fire_date_str":            employee.fire_date.strftime("%d.%m.%Y") if employee.fire_date else "",
        "passport_issued_date_str": employee.passport_issued_date.strftime("%d.%m.%Y") if employee.passport_issued_date else "",
        "departments": departments,
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
        email        = request.POST.get("email", "").strip().lower()
        password     = request.POST.get("password")
        password2    = request.POST.get("password2")
        company_name = request.POST.get("company_name", "").strip()

        if not email or not password or not company_name:
            return render(request, "dashboard/register.html", {"error": "Заполните все поля"})
        if password != password2:
            return render(request, "dashboard/register.html", {"error": "Пароли не совпадают"})
        if User.objects.filter(email=email).exists():
            return render(request, "dashboard/register.html", {"error": "Email уже зарегистрирован"})

        import uuid, hashlib
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone
        import datetime

        # Сохраняем данные регистрации в Redis (не в БД!) до подтверждения email
        token = str(uuid.uuid4())
        expires_at = (timezone.now() + datetime.timedelta(hours=24)).isoformat()
        password_hash = make_password(password)

        import redis as _redis
        from django.conf import settings
        r = _redis.from_url(getattr(settings, "REDIS_RELAY_URL", "redis://redis:6379/2"))
        import json as _json
        pending_key = f"pending_registration:{token}"
        r.setex(pending_key, 86400, _json.dumps({
            "email": email,
            "password_hash": password_hash,
            "company_name": company_name,
            "expires_at": expires_at,
        }, ensure_ascii=False))

        verify_url = request.build_absolute_uri(f"/dashboard/verify-email/{token}/")

        # Отправляем только письмо — в БД ничего не создаётся
        from apps.accounts.tasks import send_verification_email_pending
        send_verification_email_pending.delay(email, verify_url)

        return render(request, "dashboard/email_sent.html", {"email": email})
    return render(request, "dashboard/register.html")


def verify_email_view(request, token):
    import redis as _redis, json as _json
    from django.utils import timezone
    from django.conf import settings
    import datetime

    r = _redis.from_url(getattr(settings, "REDIS_RELAY_URL", "redis://redis:6379/2"))
    pending_key = f"pending_registration:{token}"
    data_raw = r.get(pending_key)

    if not data_raw:
        return render(request, "dashboard/register.html", {"error": "Ссылка недействительна или устарела"})

    data = _json.loads(data_raw)
    email        = data["email"]
    password_hash = data["password_hash"]
    company_name  = data["company_name"]

    # Проверяем — вдруг успели зарегистрироваться с тем же email
    if User.objects.filter(email=email).exists():
        r.delete(pending_key)
        return render(request, "dashboard/register.html", {"error": "Email уже зарегистрирован"})

    # Создаём пользователя, компанию, подписку — только сейчас
    from apps.billing.models import Subscription

    user = User(username=email, email=email, email_verified=True, is_active=True)
    user.password = password_hash
    user.save()

    company = Company.objects.create(name=company_name, owner=user)
    CompanyMember.objects.create(user=user, company=company, role="owner")
    Subscription.objects.create(
        company=company,
        plan=Subscription.Plan.TRIAL,
        status=Subscription.Status.ACTIVE,
        expires_at=timezone.now() + datetime.timedelta(days=7),
        max_employees=10,
    )

    # Удаляем pending запись
    r.delete(pending_key)

    # Уведомления — Telegram + Google Sheets (только после реальной регистрации)
    from apps.accounts.tasks import notify_new_registration
    notify_new_registration.delay(
        email=email,
        company_name=company_name,
        registered_at=timezone.now().strftime("%d.%m.%Y %H:%M"),
    )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return render(request, "dashboard/email_verified.html")


def resend_verification_view(request):
    import redis as _redis, json as _json, uuid
    from django.utils import timezone
    from django.conf import settings
    import datetime

    email = request.GET.get("email", "").strip().lower()
    if not email:
        return redirect("dashboard:register")

    r = _redis.from_url(getattr(settings, "REDIS_RELAY_URL", "redis://redis:6379/2"))

    # Ищем pending запись по email
    existing_data = None
    existing_key = None
    for key in r.scan_iter("pending_registration:*"):
        raw = r.get(key)
        if raw:
            d = _json.loads(raw)
            if d.get("email") == email:
                existing_data = d
                existing_key = key
                break

    if not existing_data:
        return redirect("dashboard:register")

    # Создаём новый токен
    new_token = str(uuid.uuid4())
    new_key = f"pending_registration:{new_token}"
    r.setex(new_key, 86400, _json.dumps(existing_data, ensure_ascii=False))
    if existing_key:
        r.delete(existing_key)

    verify_url = request.build_absolute_uri(f"/dashboard/verify-email/{new_token}/")
    from apps.accounts.tasks import send_verification_email_pending
    send_verification_email_pending.delay(email, verify_url)

    return render(request, "dashboard/email_sent.html", {"email": email, "resent": True})


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


@login_required
@subscription_required
def timesheet_edit(request):
    """Редактирование табеля Т-13 по месяцу."""
    import calendar
    from datetime import date as dt_date
    from apps.employees.models import TimeRecord
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    try:
        y = int(request.GET.get("year", dt_date.today().year))
        m = int(request.GET.get("month", dt_date.today().month))
    except (ValueError, TypeError):
        y, m = dt_date.today().year, dt_date.today().month

    employees = Employee.objects.filter(company=member.company).select_related("department")
    days_in_month = calendar.monthrange(y, m)[1]
    days = list(range(1, days_in_month + 1))

    # Получаем все отметки за месяц
    from django.db.models import Q
    import datetime
    start = datetime.date(y, m, 1)
    end = datetime.date(y, m, days_in_month)
    records = TimeRecord.objects.filter(
        employee__in=employees,
        date__gte=start, date__lte=end
    )
    # Словарь: {(employee_id, day): record}
    rec_map = {(r.employee_id, r.date.day): r for r in records}

    # Праздники и выходные
    holidays = _get_ru_holidays_dashboard(y)
    day_types = []
    for d in days:
        dd = datetime.date(y, m, d)
        if dd in holidays:
            day_types.append('holiday')
        elif dd.weekday() >= 5:
            day_types.append('weekend')
        else:
            day_types.append('work')

    days_with_types = list(zip(days, day_types))
    CODES = [
        ('Я','Явка'), ('ОТ','Отпуск'), ('ОД','Доп.отпуск'),
        ('Б','Больничный'), ('К','Командировка'), ('НН','Неявка'),
        ('П','Праздник'), ('В','Выходной'), ('Я½','Неполный'),
    ]

    month_names = ["Январь","Февраль","Март","Апрель","Май","Июнь",
                   "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]

    import json as _json
    from django.utils.safestring import mark_safe
    day_types_json = mark_safe(_json.dumps(day_types, ensure_ascii=False))
    return render(request, "dashboard/timesheet.html", {
        "employees": employees,
        "days": days,
        "day_types": day_types,
        "day_types_json": day_types_json,
        "days_with_types": days_with_types,
        "rec_map_json": _rec_map_to_json(rec_map),
        "year": y,
        "month": m,
        "month_name": month_names[m-1],
        "codes": CODES,
    })


def _rec_map_to_json(rec_map):
    import json
    d = {}
    for (emp_id, day), rec in rec_map.items():
        d[f"{emp_id}_{day}"] = {"code": rec.code, "hours": rec.hours}
    return json.dumps(d, ensure_ascii=False)


def _get_ru_holidays_dashboard(year):
    """Обёртка _get_ru_holidays для использования в views."""
    from apps.documents.services import _get_ru_holidays
    return _get_ru_holidays(year)


@login_required
@subscription_required
def timesheet_save(request):
    """Сохраняет отметки табеля из POST (JSON body)."""
    import json
    from apps.employees.models import TimeRecord
    from datetime import date as dt_date
    if request.method != "POST":
        from django.http import JsonResponse
        return JsonResponse({"error": "POST required"}, status=405)
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        from django.http import JsonResponse
        return JsonResponse({"error": "no company"}, status=403)
    try:
        data = json.loads(request.body)
    except Exception:
        from django.http import JsonResponse
        return JsonResponse({"error": "invalid json"}, status=400)

    # data = {"records": [{"employee_id": 1, "date": "2026-04-15", "code": "ОТ", "hours": 8}, ...]}
    employee_ids = set(Employee.objects.filter(company=member.company).values_list('id', flat=True))
    saved = 0
    for rec in data.get("records", []):
        emp_id = rec.get("employee_id")
        if emp_id not in employee_ids:
            continue
        try:
            d = dt_date.fromisoformat(rec["date"])
        except Exception:
            continue
        code = rec.get("code", "Я")[:3]
        hours = int(rec.get("hours", 8))
        TimeRecord.objects.update_or_create(
            employee_id=emp_id, date=d,
            defaults={"code": code, "hours": hours}
        )
        saved += 1
    from django.http import JsonResponse
    return JsonResponse({"saved": saved})


# ─── СБРОС ПАРОЛЯ ──────────────────────────────────────────────────────────

def forgot_password_view(request):
    """Запрос ссылки для сброса пароля."""
    if request.user.is_authenticated:
        return redirect("dashboard:employees")

    if request.method == "POST":
        import uuid, json as _json, datetime
        import redis as _redis
        from django.conf import settings
        from django.utils import timezone

        email = request.POST.get("email", "").strip().lower()
        if not email:
            return render(request, "dashboard/forgot_password.html",
                          {"error": "Введите email"})

        # Не раскрываем, есть ли такой пользователь (защита от перебора)
        user = User.objects.filter(email=email).first()
        if user:
            token = str(uuid.uuid4())
            r = _redis.from_url(getattr(settings, "REDIS_RELAY_URL", "redis://redis:6379/2"))
            r.setex(f"password_reset:{token}", 3600, _json.dumps({
                "user_id": user.id,
                "email": email,
            }))
            reset_url = request.build_absolute_uri(f"/dashboard/reset-password/{token}/")
            from apps.accounts.tasks import send_password_reset_email
            send_password_reset_email.delay(email, reset_url)

        return render(request, "dashboard/forgot_password.html", {
            "success": f"Если аккаунт с адресом {email} существует, письмо будет отправлено в течение нескольких минут."
        })

    return render(request, "dashboard/forgot_password.html")


def reset_password_view(request, token):
    """Смена пароля по ссылке из письма."""
    from django.conf import settings
    import redis as _redis, json as _json
    from django.contrib.auth.hashers import make_password

    r = _redis.from_url(getattr(settings, "REDIS_RELAY_URL", "redis://redis:6379/2"))
    data_raw = r.get(f"password_reset:{token}")

    if not data_raw:
        return render(request, "dashboard/reset_password.html",
                      {"valid_token": False, "token": token})

    data = _json.loads(data_raw)

    if request.method == "POST":
        post_token = request.POST.get("token", "")
        password   = request.POST.get("password", "")
        password2  = request.POST.get("password2", "")

        if len(password) < 8:
            return render(request, "dashboard/reset_password.html",
                          {"valid_token": True, "token": token,
                           "error": "Пароль должен быть не менее 8 символов"})
        if password != password2:
            return render(request, "dashboard/reset_password.html",
                          {"valid_token": True, "token": token,
                           "error": "Пароли не совпадают"})

        try:
            user = User.objects.get(id=data["user_id"])
            user.set_password(password)
            user.save()
            r.delete(f"password_reset:{token}")
            return render(request, "dashboard/reset_password.html",
                          {"valid_token": True, "token": token,
                           "success": "Пароль успешно изменён! Теперь вы можете войти."})
        except User.DoesNotExist:
            return render(request, "dashboard/reset_password.html",
                          {"valid_token": False, "token": token})

    return render(request, "dashboard/reset_password.html",
                  {"valid_token": True, "token": token})


@login_required
def change_password_view(request):
    """Смена пароля для авторизованного пользователя."""
    from django.contrib.auth import update_session_auth_hash

    if request.method == "POST":
        old_password = request.POST.get("old_password", "")
        password     = request.POST.get("password", "")
        password2    = request.POST.get("password2", "")

        if not request.user.check_password(old_password):
            return render(request, "dashboard/change_password.html",
                          {"error": "Текущий пароль введён неверно"})
        if len(password) < 8:
            return render(request, "dashboard/change_password.html",
                          {"error": "Новый пароль должен быть не менее 8 символов"})
        if password != password2:
            return render(request, "dashboard/change_password.html",
                          {"error": "Пароли не совпадают"})

        request.user.set_password(password)
        request.user.save()
        # Обновляем сессию чтобы не разлогинило
        update_session_auth_hash(request, request.user)
        return render(request, "dashboard/change_password.html",
                      {"success": "Пароль успешно изменён!"})

    return render(request, "dashboard/change_password.html")
