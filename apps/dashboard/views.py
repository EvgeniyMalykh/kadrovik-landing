import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from apps.accounts.models import User
from apps.employees.models import Employee, Department
from apps.companies.models import Company, CompanyMember
from apps.documents.services import generate_t1_pdf, generate_t2_pdf, generate_t8_pdf, generate_t6_pdf
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


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
            max_employees=50,
        )
    # Оставшиеся дни trial
    trial_days_left = None
    if sub and sub.plan == Subscription.Plan.TRIAL and sub.expires_at:
        delta = sub.expires_at - timezone.now()
        trial_days_left = max(0, delta.days)
    from apps.billing.services import get_subscription_context
    sub_ctx = get_subscription_context(company)
    # Если подписка истекла — рендерим страницу с флагом (не редирект, т.к. главная)
    subscription_expired = bool(sub and not sub.is_active)
    return render(request, "dashboard/employees.html", {
        "employees": employees,
        "company": company,
        "today": _date.today().isoformat(),
        "sub": sub,
        "trial_days_left": trial_days_left,
        "subscription_expired": subscription_expired,
        **sub_ctx,
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
    is_new = not employee.pk

    employee.last_name   = post.get("last_name", "")
    employee.first_name  = post.get("first_name", "")
    employee.middle_name = post.get("middle_name", "")
    employee.position    = post.get("position", "")
    salary_raw = post.get('salary')
    if salary_raw not in (None, ''):
        try:
            employee.salary = Decimal(salary_raw)
        except (InvalidOperation, ValueError):
            employee.salary = None
    else:
        employee.salary = None

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

    # Даты: при редактировании пустое поле не затирает старое значение
    parsed_hire = _parse_date_flexible(post.get("hire_date"))
    if parsed_hire:
        employee.hire_date = parsed_hire
    elif is_new:
        employee.hire_date = date.today()

    parsed_birth = _parse_date_flexible(post.get("birth_date"))
    if parsed_birth:
        employee.birth_date = parsed_birth
    elif is_new:
        employee.birth_date = None

    probation_months = post.get("probation_months")
    if probation_months:
        try:
            months = int(probation_months)
            employee.probation_end_date = employee.hire_date + timedelta(days=30 * months)
        except ValueError:
            if is_new:
                employee.probation_end_date = None
    else:
        probation_end_str = post.get("probation_end_date")
        parsed_probation = _parse_date_flexible(probation_end_str)
        if parsed_probation:
            employee.probation_end_date = parsed_probation
        elif is_new:
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

    parsed_passport_date = _parse_date_flexible(post.get("passport_issued_date"))
    if parsed_passport_date:
        employee.passport_issued_date = parsed_passport_date
    elif is_new:
        employee.passport_issued_date = None

    parsed_contract_end = _parse_date_flexible(post.get("contract_end_date"))
    if parsed_contract_end:
        employee.contract_end_date = parsed_contract_end
    elif is_new:
        employee.contract_end_date = None

    parsed_fire = _parse_date_flexible(post.get("fire_date"))
    if parsed_fire:
        employee.fire_date = parsed_fire
    elif is_new:
        employee.fire_date = None

    # Новые поля
    employee.birth_place = post.get("birth_place", "")
    employee.education   = post.get("education", "")
    employee.marital_status = post.get("marital_status") or None
    employee.citizenship    = post.get("citizenship") or None

    return employee


@login_required
@subscription_required
def employee_add(request):
    from apps.billing.services import get_subscription_context
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return HttpResponse("Нет компании", status=400)
    sub_ctx = get_subscription_context(member.company)

    if request.method == "POST":
        # Проверяем лимит сотрудников по тарифу
        if not sub_ctx["can_add_employee"]:
            return HttpResponse(
                f'<div class="alert alert-error" style="padding:12px 16px;border-radius:8px;background:#fee2e2;color:#991b1b;margin:8px 0;">'
                f'Достигнут лимит тарифа — <strong>{sub_ctx["max_employees"]} сотрудников</strong>. '
                f'<a href="/dashboard/subscription/" style="color:#991b1b;font-weight:600;">Обновите тариф</a> для добавления новых.</div>',
                status=200
            )
        emp = Employee(company=member.company)
        _save_employee_from_post(request.POST, emp)
        emp.save()
        employees = Employee.objects.filter(company=member.company).select_related("department")
        return render(request, "dashboard/partials/employees_table.html", {"employees": employees})

    departments = list(member.company.departments.values('id', 'name')) if hasattr(member.company, 'departments') else []
    from apps.employees.models import Department as _Dept
    departments = list(_Dept.objects.filter(company=member.company).values('id', 'name'))
    # Автотабельный номер
    import re as _re_pn
    existing_nums = Employee.objects.filter(company=member.company).values_list('personnel_number', flat=True)
    max_pn = 0
    for pn in existing_nums:
        if pn:
            m = _re_pn.search(r'(\d+)', str(pn))
            if m:
                max_pn = max(max_pn, int(m.group(1)))
    next_personnel_number = str(max_pn + 1).zfill(3)
    return render(request, "dashboard/partials/employee_form.html", {
        "departments": departments,
        "can_add_employee": sub_ctx["can_add_employee"],
        "max_employees": sub_ctx["max_employees"],
        "employee_count": sub_ctx["employee_count"],
        "next_personnel_number": next_personnel_number,
    })


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
        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)
            if request.POST.get("remember_me"):
                request.session.set_expiry(60 * 60 * 24 * 30)  # 30 дней
            else:
                request.session.set_expiry(0)  # до закрытия браузера
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
    # Прежний оклад: сначала из документа (надёжный источник), потом из GET-параметра
    old_salary = ""
    from apps.documents.models import Document
    last_doc = Document.objects.filter(
        employee=employee, doc_type='salary_change'
    ).order_by('-date', '-id').first()
    if last_doc and last_doc.extra_data and last_doc.extra_data.get('old_salary'):
        old_salary = last_doc.extra_data['old_salary']
    if not old_salary:
        old_salary = request.GET.get("old_salary", "")
    pdf = generate_salary_change_pdf(employee, new_salary, request.GET.get("order", "З-001"), previous_salary=old_salary)
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"SalaryChange_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_transfer_order(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_transfer_order_pdf
    new_position = request.GET.get("new_position", "")
    new_salary = request.GET.get("new_salary", "")
    transfer_date = request.GET.get("transfer_date", "")
    reason = request.GET.get("reason", "")
    pdf = generate_transfer_order_pdf(
        employee,
        new_position=new_position or (employee.position or "Новая должность"),
        new_salary=new_salary or None,
        order_number=request.GET.get("order", "ПР-001"),
        transfer_date=transfer_date or None,
        reason=reason or None,
    )
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"Transfer_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_dismissal_order(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_dismissal_order_pdf
    pdf = generate_dismissal_order_pdf(
        employee,
        order_number=request.GET.get("order", "У-001"),
        dismissal_date=request.GET.get("dismissal_date", "") or None,
        dismissal_reason=request.GET.get("dismissal_reason", "") or None,
        dismissal_basis_doc=request.GET.get("dismissal_basis_doc", "") or None,
    )
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"Dismissal_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_bonus_order(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_bonus_order_pdf
    pdf = generate_bonus_order_pdf(
        employee,
        bonus_amount=request.GET.get("bonus_amount", "0"),
        order_number=request.GET.get("order", "П-001"),
        reason=request.GET.get("reason", "") or None,
        payment_date=request.GET.get("payment_date", "") or None,
    )
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"Bonus_{employee.last_name}.pdf\""
    return r


@login_required
@subscription_required
def download_disciplinary_order(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    from apps.documents.services import generate_disciplinary_order_pdf
    pdf = generate_disciplinary_order_pdf(
        employee,
        penalty_type=request.GET.get("penalty_type", "Выговор"),
        order_number=request.GET.get("order", "ДВ-001"),
        violation_date=request.GET.get("violation_date", "") or None,
        violation_description=request.GET.get("violation_description", "") or None,
        reason=request.GET.get("reason", "") or None,
    )
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f"attachment; filename=\"Disciplinary_{employee.last_name}.pdf\""
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
        ('Я','Явка'), ('ОТ','Отпуск'), ('ДО','Доп.отпуск'),
        ('Б','Больничный'), ('К','Командировка'), ('НН','Неявка'),
        ('П','Праздник'), ('В','Выходной'), ('Я½','Неполный'),
        ('РВ','Работа в выходной'), ('Я/С','Сверхурочные'),
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
            # Автологин после смены пароля
            from django.contrib.auth import login as auth_login
            auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("dashboard:employees")
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


# ─── ФОРМЫ И ДОКУМЕНТЫ ────────────────────────────────────────────────────

@login_required
@subscription_required
def forms_list(request):
    """Журнал всех документов компании с фильтром по типу"""
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    company = member.company
    from apps.documents.models import Document
    doc_type = request.GET.get('type', '')
    documents = Document.objects.filter(company=company).select_related('employee').order_by('-created_at')
    if doc_type:
        documents = documents.filter(doc_type=doc_type)
    employees = Employee.objects.filter(company=company, status='active').order_by('last_name')
    return render(request, 'dashboard/forms_list.html', {
        'documents': documents,
        'employees': employees,
        'active_type': doc_type,
    })



@require_POST
@login_required
def delete_document(request, doc_id):
    """Удаление документа из журнала"""
    from django.http import JsonResponse
    from apps.documents.models import Document
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return JsonResponse({'success': False, 'error': 'Компания не найдена'}, status=403)
    try:
        doc = Document.objects.get(id=doc_id, company=member.company)
        doc.delete()
        return JsonResponse({'success': True})
    except Document.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Документ не найден'}, status=404)


def _next_doc_number(company, doc_type):
    """Генерирует следующий номер документа по типу для компании."""
    from apps.documents.models import Document
    PREFIX = {
        "vacation":     "О",
        "gph_contract": "ГПХ",
        "gph_act":      "АКТ",
        "reference":    "С",
        "salary_change":"З",
        "transfer":     "ПР",
        "dismissal":    "У",
        "bonus":        "П",
        "disciplinary": "ДВ",
    }
    prefix = PREFIX.get(doc_type, "Д")
    existing = Document.objects.filter(company=company, doc_type=doc_type).values_list("number", flat=True)
    max_n = 0
    for num in existing:
        if num:
            import re
            m = re.search(r"(\d+)", str(num))
            if m:
                max_n = max(max_n, int(m.group(1)))
    return f"{prefix}-{max_n + 1}"


@login_required
@subscription_required
def form_editor(request, doc_type):
    """Редактор формы (новый или существующий документ)"""
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    company = member.company
    from apps.documents.models import Document
    doc_id = request.GET.get('doc_id')
    document = None
    if doc_id:
        document = get_object_or_404(Document, id=doc_id, company=company)
    employees = Employee.objects.filter(company=company, status='active').order_by('last_name')

    FORM_TITLES = {
        'vacation': 'Приказ об отпуске (Т-6)',
        'gph_contract': 'Договор ГПХ',
        'gph_act': 'Акт выполненных работ',
        'reference': 'Справка с места работы',
        'salary_change': 'Изменение оклада',
        'transfer': 'Приказ о переводе (Т-5)',
        'dismissal': 'Приказ об увольнении (Т-8)',
        'bonus': 'Приказ о премии',
        'disciplinary': 'Приказ о дисциплинарном взыскании',
    }
    if doc_type not in FORM_TITLES:
        from django.http import Http404
        raise Http404

    next_number = _next_doc_number(company, doc_type) if not document else (document.number or _next_doc_number(company, doc_type))
    return render(request, 'dashboard/form_editor.html', {
        'doc_type': doc_type,
        'form_title': FORM_TITLES[doc_type],
        'document': document,
        'employees': employees,
        'extra_data': document.extra_data if document else {},
        'next_number': next_number,
    })


@login_required
@subscription_required
@require_POST
def form_save(request, doc_type):
    """Сохранение документа"""
    import json as _json_save
    from apps.documents.models import Document
    from django.http import JsonResponse
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return JsonResponse({'error': 'no company'}, status=403)
    company = member.company
    doc_id = request.POST.get('doc_id')
    employee_id = request.POST.get('employee_id')

    employee = None
    if employee_id:
        employee = get_object_or_404(Employee, id=employee_id, company=company)

    # Собираем extra_data из POST
    skip_keys = {'csrfmiddlewaretoken', 'doc_id', 'employee_id', 'doc_number', 'doc_date'}
    extra_data = {}
    for key, value in request.POST.items():
        if key not in skip_keys and value:
            extra_data[key] = value

    doc_number = request.POST.get('doc_number', '')
    doc_date_str = request.POST.get('doc_date', '')

    doc_date = date.today()
    if doc_date_str:
        parsed = _parse_date_flexible(doc_date_str)
        if parsed:
            doc_date = parsed

    FORM_TITLES = {
        'vacation': 'vacation',
        'gph_contract': 'gph_contract',
        'gph_act': 'gph_act',
        'reference': 'reference',
        'salary_change': 'salary_change',
        'transfer': 'transfer',
        'dismissal': 'dismissal',
        'bonus': 'bonus',
        'disciplinary': 'disciplinary',
    }
    if doc_type not in FORM_TITLES:
        return JsonResponse({'error': 'invalid doc_type'}, status=400)

    if doc_id:
        document = get_object_or_404(Document, id=doc_id, company=company)
        document.employee = employee
        document.number = doc_number
        document.date = doc_date
        document.extra_data = extra_data
        document.save()
    else:
        document = Document.objects.create(
            company=company,
            employee=employee,
            doc_type=doc_type,
            number=doc_number,
            date=doc_date,
            extra_data=extra_data,
        )

    # При сохранении salary_change — записываем старый оклад в историю и обновляем employee.salary
    if doc_type == 'salary_change' and employee:
        new_salary_raw = extra_data.get('new_salary')
        if new_salary_raw:
            try:
                new_salary_val = Decimal(new_salary_raw)
            except (InvalidOperation, ValueError):
                new_salary_val = None
            if new_salary_val and employee.salary != new_salary_val:
                from apps.employees.models import SalaryHistory
                old_salary = employee.salary  # сохраняем СТАРЫЙ оклад ДО обновления
                effective = _parse_date_flexible(extra_data.get('change_date')) or date.today()
                if old_salary:
                    SalaryHistory.objects.create(
                        employee=employee,
                        salary=old_salary,
                        effective_date=effective,
                    )
                # Сохраняем старый оклад в extra_data документа для PDF
                extra_data['old_salary'] = str(old_salary) if old_salary else '0'
                document.extra_data = extra_data
                document.save()
                # Только ПОТОМ обновляем оклад сотрудника
                employee.salary = new_salary_val
                employee.save()

    # При сохранении dismissal — обновляем fire_date и статус сотрудника
    if doc_type == 'dismissal' and employee:
        dismissal_date_raw = extra_data.get('dismissal_date')
        fire_date = _parse_date_flexible(dismissal_date_raw) or date.today()
        employee.fire_date = fire_date
        employee.status = 'fired'
        employee.save()

    # При сохранении transfer — обновляем должность и оклад сотрудника
    if doc_type == 'transfer' and employee:
        new_pos = extra_data.get('new_position')
        if new_pos:
            # Сохраняем старые данные в extra_data для PDF
            extra_data['old_position'] = employee.position or ''
            extra_data['old_salary'] = str(employee.salary) if employee.salary else ''
            document.extra_data = extra_data
            document.save()
            employee.position = new_pos
        new_sal = extra_data.get('new_salary')
        if new_sal:
            try:
                employee.salary = Decimal(new_sal)
            except (InvalidOperation, ValueError):
                pass
        employee.save()

    return JsonResponse({'success': True, 'doc_id': document.id, 'doc_type': doc_type})


@login_required
def employee_data_api(request, employee_id):
    """JSON данные сотрудника для автозаполнения"""
    from django.http import JsonResponse
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return JsonResponse({'error': 'no company'}, status=403)
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    # Последняя запись из истории окладов
    from apps.employees.models import SalaryHistory
    last_hist = employee.salary_history.order_by('-effective_date', '-created_at').first()
    data = {
        'id': employee.id,
        'full_name': employee.full_name,
        'first_name': employee.first_name,
        'last_name': employee.last_name,
        'middle_name': employee.middle_name or '',
        'position': employee.position or '',
        'salary': str(employee.salary) if employee.salary else '',
        'hire_date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else '',
        'inn': employee.inn or '',
        'snils': employee.snils or '',
        'phone': employee.phone or '',
        'email': employee.email or '',
        'passport_series': employee.passport_series or '',
        'passport_number': employee.passport_number or '',
        'previous_salary': str(last_hist.salary) if last_hist else '',
        'previous_salary_date': last_hist.effective_date.strftime('%d.%m.%Y') if last_hist else '',
    }
    return JsonResponse(data)


import hashlib as _hashlib
import time as _time

_CHAT_REDIS = 'redis://redis:6379/3'   # db=3 — чат (отдельно от celery и relay)
_BOT_TOKEN  = '7718001813:AAH4KBXZId8CurJdxpmno9jCJr5Bgcx01mM'
_ADMIN_CHAT = 1113292310


def _get_chat_session(request):
    """Уникальный 8-символьный ID сессии по email пользователя."""
    uid = request.user.email if request.user.is_authenticated else (
        request.session.session_key or 'anon'
    )
    return _hashlib.md5(uid.encode()).hexdigest()[:8]


def _chat_redis():
    import redis as _r
    return _r.from_url(_CHAT_REDIS)


def _save_msg(session_id, role, text, email=''):
    """Сохраняет сообщение в историю и обновляет индекс сессий."""
    import json as _j
    r = _chat_redis()
    msg = _j.dumps({'role': role, 'text': text, 'ts': int(_time.time())},
                   ensure_ascii=False)
    hist_key = f'chat_hist:{session_id}'
    r.rpush(hist_key, msg)
    r.expire(hist_key, 86400 * 7)   # храним 7 дней

    # Индекс всех сессий: hash  session_id -> {email, last_msg, ts}
    meta = _j.dumps({'email': email, 'last': text[:80], 'ts': int(_time.time())},
                    ensure_ascii=False)
    r.hset('chat_sessions', session_id, meta)


@require_POST
def chat_support(request):
    """Принимает сообщение клиента, сохраняет в историю, шлёт в Telegram."""
    from django.http import JsonResponse
    import json as _json, requests as _req

    try:
        data = _json.loads(request.body)
        text = data.get('text', '').strip()
    except Exception:
        text = request.POST.get('text', '').strip()

    if not text:
        return JsonResponse({'ok': False, 'error': 'empty'})

    user_email = request.user.email if request.user.is_authenticated else 'аноним'
    session_id = _get_chat_session(request)

    # Сохраняем сообщение клиента в историю
    _save_msg(session_id, 'user', text, email=user_email)

    tg_text = (
        f'\U0001f4ac Чат поддержки [{session_id}]\n'
        f'\U0001f464 {user_email}\n'
        f'\U0001f4dd {text}\n\n'
        f'<i>Reply на это сообщение чтобы ответить клиенту</i>'
    )

    try:
        resp = _req.post(
            f'https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage',
            json={'chat_id': _ADMIN_CHAT, 'text': tg_text, 'parse_mode': 'HTML'},
            timeout=10,
        )
        result = resp.json()
        return JsonResponse({'ok': result.get('ok', False), 'session': session_id})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


def chat_history(request):
    """Возвращает историю переписки для сессии (вызывается при загрузке страницы)."""
    from django.http import JsonResponse
    import json as _json

    session_id = request.GET.get('session', '')
    if not session_id or len(session_id) != 8:
        # Вычисляем session_id из текущего пользователя
        session_id = _get_chat_session(request)

    r = _chat_redis()
    hist_key = f'chat_hist:{session_id}'
    raw_list = r.lrange(hist_key, 0, -1)

    messages = []
    for raw in raw_list:
        try:
            messages.append(_json.loads(raw))
        except Exception:
            pass

    return JsonResponse({'session': session_id, 'messages': messages})


@csrf_exempt
def chat_webhook(request):
    """Webhook от Telegram — ответы оператора и команды бота."""
    from django.http import JsonResponse
    import json as _json, re as _re, requests as _req

    if request.method != 'POST':
        return JsonResponse({'ok': True})

    try:
        data = _json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False})

    msg = data.get('message', {})
    if not msg:
        return JsonResponse({'ok': True})

    from_chat = msg.get('chat', {}).get('id')
    text = msg.get('text', '').strip()

    # ── Команда /чаты ──────────────────────────────────────────────────────
    if text in ('/чаты', '/chats', '/чаты@kadrovik_leads_bot'):
        r = _chat_redis()
        sessions = r.hgetall('chat_sessions')

        if not sessions:
            reply = '\U0001f4c2 Активных чатов нет.'
        else:
            import json as _j2
            lines = ['\U0001f4cb <b>Активные сессии чата:</b>\n']
            for sid, meta_raw in sessions.items():
                sid = sid.decode() if isinstance(sid, bytes) else sid
                try:
                    meta = _j2.loads(meta_raw)
                except Exception:
                    continue
                import datetime
                ts = datetime.datetime.fromtimestamp(meta['ts']).strftime('%d.%m %H:%M')
                lines.append(
                    f'\U0001f464 <b>{meta.get("email","?")}</b> [{sid}]\n'
                    f'   \U0001f4dd {meta.get("last","...")}\n'
                    f'   \U0001f552 {ts}\n'
                )
            reply = '\n'.join(lines)

        _req.post(
            f'https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage',
            json={'chat_id': from_chat, 'text': reply, 'parse_mode': 'HTML'},
            timeout=10,
        )
        return JsonResponse({'ok': True})

    # ── Ответ оператора клиенту ────────────────────────────────────────────
    session_id = None

    # Способ 1: reply на сообщение бота
    reply_to = msg.get('reply_to_message', {})
    if reply_to:
        orig = reply_to.get('text', '')
        m = _re.search(r'\[([a-f0-9]{8})\]', orig)
        if m:
            session_id = m.group(1)

    # Способ 2: оператор пишет [session_id] текст
    if not session_id:
        m = _re.match(r'\[([a-f0-9]{8})\]\s*(.*)', text, _re.DOTALL)
        if m:
            session_id = m.group(1)
            text = m.group(2).strip()

    if not session_id or not text:
        return JsonResponse({'ok': True})

    # Сохраняем ответ в историю
    _save_msg(session_id, 'bot', text)

    # Кладём в очередь для poll
    r = _chat_redis()
    import json as _j3
    r.rpush(f'chat_replies:{session_id}',
            _j3.dumps({'text': text, 'ts': int(_time.time())}, ensure_ascii=False))
    r.expire(f'chat_replies:{session_id}', 3600)

    return JsonResponse({'ok': True})


def chat_poll(request):
    """Клиент опрашивает новые сообщения от оператора (только новые, не история)."""
    from django.http import JsonResponse
    import json as _json

    session_id = request.GET.get('session', '')
    if not session_id or len(session_id) != 8:
        return JsonResponse({'messages': []})

    r = _chat_redis()
    key = f'chat_replies:{session_id}'
    messages = []
    while True:
        raw = r.lpop(key)
        if not raw:
            break
        try:
            messages.append(_json.loads(raw))
        except Exception:
            pass

    return JsonResponse({'messages': messages})


@require_POST
@login_required
def delete_document(request, doc_id):
    from django.http import JsonResponse
    from apps.documents.models import Document
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return JsonResponse({"success": False, "error": "Нет доступа"}, status=403)
    try:
        doc = Document.objects.get(id=doc_id, company=member.company)
        doc.delete()
        return JsonResponse({"success": True})
    except Document.DoesNotExist:
        return JsonResponse({"success": False, "error": "Документ не найден"}, status=404)
