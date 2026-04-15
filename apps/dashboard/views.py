from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from apps.accounts.models import User
from apps.employees.models import Employee, Department
from apps.companies.models import Company, CompanyMember
from apps.documents.services import generate_t1_pdf
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
    return render(request, "dashboard/employees.html", {
        "employees": employees,
        "company": company,
    })


@login_required
def employee_add(request):
    if request.method == "POST":
        member = CompanyMember.objects.filter(user=request.user).first()
        if not member:
            return HttpResponse("Нет компании", status=400)

        hire_date_str = request.POST.get("hire_date")
        hire_date = date.fromisoformat(hire_date_str) if hire_date_str else date.today()

        birth_date_str = request.POST.get("birth_date")
        birth_date = date.fromisoformat(birth_date_str) if birth_date_str else None

        probation_months = request.POST.get("probation_months")
        probation_end_date = None
        if probation_months:
            try:
                months = int(probation_months)
                probation_end_date = hire_date + timedelta(days=30 * months)
            except ValueError:
                pass

        Employee.objects.create(
            company=member.company,
            first_name=request.POST.get("first_name", ""),
            last_name=request.POST.get("last_name", ""),
            middle_name=request.POST.get("middle_name", ""),
            position=request.POST.get("position", ""),
            salary=request.POST.get("salary") or None,
            hire_date=hire_date,
            birth_date=birth_date,
            probation_end_date=probation_end_date,
        )
        employees = Employee.objects.filter(company=member.company).select_related("department")
        return render(request, "dashboard/partials/employees_table.html", {"employees": employees})
    return render(request, "dashboard/partials/employee_form.html")


@login_required
def download_t1(request, employee_id):
    member = CompanyMember.objects.filter(user=request.user).first()
    employee = get_object_or_404(Employee, id=employee_id, company=member.company)
    order_number = request.GET.get("order", "П-001")
    pdf_bytes = generate_t1_pdf(employee, order_number)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=\"T1_{employee.last_name}.pdf\""
    return response


@login_required
def subscription(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    sub = None
    payments = []
    if member:
        sub = getattr(member.company, "subscription", None)
        payments = member.company.payments.all()[:10]
    return render(request, "dashboard/subscription.html", {
        "sub": sub,
        "payments": payments,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:employees")
    if request.method == "POST":
        email = request.POST.get("email")
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
        email = request.POST.get("email")
        password = request.POST.get("password")
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
