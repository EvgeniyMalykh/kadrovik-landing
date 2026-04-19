from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.db.models import Count
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee

# ===== ROLE-BASED ACCESS CONTROL =====
ROLE_RANK = {
    'owner': 4,
    'admin': 3,
    'hr': 2,
    'accountant': 1,
}

def _check_role(request, min_role):
    """Проверяет роль. Возвращает True если доступ разрешён."""
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return False
    return ROLE_RANK.get(member.role, 0) >= ROLE_RANK.get(min_role, 99)
from .models import Vacation, VacationSchedule, VacationScheduleEntry
import re
import json
from datetime import date, datetime


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

    # Проверка роли — только hr и выше могут добавлять отпуска
    if not _check_role(request, 'hr'):
        return JsonResponse({"error": "Недостаточно прав"}, status=403)

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


@login_required
def vacation_additional_pdf(request, vacation_id):
    """PDF-заявление на дополнительный оплачиваемый отпуск."""
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    v = get_object_or_404(Vacation, id=vacation_id, employee__company=member.company)
    from apps.documents.services import generate_additional_vacation_application
    pdf = generate_additional_vacation_application(v)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="additional_vacation_{v.employee.last_name}.pdf"'
    return response


# ─── ПУБЛИЧНАЯ ФОРМА ДЛЯ РАБОТНИКА ──────────────────────────────────────────

VACATION_TYPE_LABELS = {
    'annual':      'Ежегодный оплачиваемый',
    'additional':  'Дополнительный оплачиваемый',
    'unpaid':      'За свой счёт (без сохранения зарплаты)',
    'educational': 'Учебный',
    'maternity':   'По беременности и родам',
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
                status='active',
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


# ─── ГРАФИК ОТПУСКОВ ──────────────────────────────────────────────────────────

@login_required
def vacation_schedule_history(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect('dashboard:employees')
    schedules = VacationSchedule.objects.filter(
        company=member.company
    ).annotate(
        employee_count=Count('entries')
    ).order_by('-year')
    return render(request, 'dashboard/vacation_schedule_history.html', {
        'schedules': schedules,
        'company': member.company,
    })


@login_required
def vacation_schedule(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    company = member.company

    current_year = date.today().year
    year = int(request.GET.get("year", current_year))
    years = [current_year - 1, current_year, current_year + 1]

    schedule, _ = VacationSchedule.objects.get_or_create(company=company, year=year)

    employees = Employee.objects.filter(company=company, status='active').order_by('last_name')

    entries = []
    for emp in employees:
        entry, _ = VacationScheduleEntry.objects.get_or_create(
            schedule=schedule, employee=emp,
            defaults={'days_total': 28},
        )
        entries.append(entry)

    # Праздники для JS-подсчёта (year и year+1, т.к. периоды могут перекрывать два года)
    from apps.employees.models import ProductionCalendar
    import json as _json
    holidays_qs = ProductionCalendar.objects.filter(
        date__year__in=[year - 1, year, year + 1],
        day_type='holiday',
    ).values_list('date', flat=True)
    holidays_js = _json.dumps([str(d) for d in holidays_qs])

    return render(request, "dashboard/vacation_schedule.html", {
        "entries": entries,
        "year": year,
        "years": years,
        "company": company,
        "schedule": schedule,
        "holidays_js": holidays_js,
    })


@login_required
@require_POST
def vacation_schedule_save(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return JsonResponse({"error": "no company"}, status=400)

    # Проверка роли — только hr и выше
    if not _check_role(request, 'hr'):
        return JsonResponse({"error": "Недостаточно прав"}, status=403)
    company = member.company

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    year = data.get("year", date.today().year)
    schedule, _ = VacationSchedule.objects.get_or_create(company=company, year=year)
    rows = data.get("rows", [])

    saved = 0
    for row in rows:
        entry_id = row.get("entry_id")
        try:
            entry = VacationScheduleEntry.objects.get(id=entry_id, schedule=schedule)
        except VacationScheduleEntry.DoesNotExist:
            continue

        entry.days_total = int(row.get("days_total", 28))
        for i in range(1, 4):
            s_val = row.get(f"period{i}_start") or None
            e_val = row.get(f"period{i}_end") or None
            setattr(entry, f"period{i}_start", _parse_date(s_val) if s_val else None)
            setattr(entry, f"period{i}_end", _parse_date(e_val) if e_val else None)

        entry.days_north = int(row.get('days_north') or 0)
        entry.north_start = _parse_date(row.get('north_start'))
        entry.north_end = _parse_date(row.get('north_end'))
        entry.days_extra = int(row.get('days_extra') or 0)
        entry.extra_start = _parse_date(row.get('extra_start'))
        entry.extra_end = _parse_date(row.get('extra_end'))

        entry.save()
        saved += 1

    return JsonResponse({"success": True, "saved": saved})


@login_required
def vacation_schedule_pdf(request):
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:employees")
    company = member.company

    year = int(request.GET.get("year", date.today().year))
    schedule = VacationSchedule.objects.filter(company=company, year=year).first()

    entries = []
    if schedule:
        # Ensure entries exist for all active employees (same as HTML view)
        employees = Employee.objects.filter(company=company, status='active').order_by('last_name')
        for emp in employees:
            VacationScheduleEntry.objects.get_or_create(
                schedule=schedule, employee=emp,
                defaults={'days_total': 28},
            )
        entries = list(schedule.entries.select_related('employee').order_by('employee__last_name'))

    pdf_bytes = generate_t7_pdf(company, year, entries)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="vacation_schedule_T7_{year}.pdf"'
    return response


def generate_t7_pdf(company, year, entries):
    import io
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    import os

    # Register fonts
    font_name = 'Helvetica'
    try:
        font_paths = [
            '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
            '/usr/share/fonts/liberation/LiberationSerif-Regular.ttf',
        ]
        for path in font_paths:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont('LiberationSerif', path))
                font_name = 'LiberationSerif'
                break
    except Exception:
        pass

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=10 * mm,
        bottomMargin=15 * mm,
    )

    normal = ParagraphStyle('Normal', fontName=font_name, fontSize=8, leading=10)
    center = ParagraphStyle('Center', fontName=font_name, fontSize=8, leading=10, alignment=TA_CENTER)
    title_style = ParagraphStyle('Title', fontName=font_name, fontSize=12, leading=14, alignment=TA_CENTER)
    small = ParagraphStyle('Small', fontName=font_name, fontSize=7, leading=9)
    small_center = ParagraphStyle('SmallCenter', fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER)
    right = ParagraphStyle('Right', fontName=font_name, fontSize=8, leading=10, alignment=TA_RIGHT)

    elements = []

    # Header
    header_data = [
        [,
         ,
         Paragraph(УТВЕРЖДАЮ, right)],
        [, ,
         Paragraph(company.name or , right)],
        [, ,
         Paragraph(f{company.director_position or Директор} ________________, right)],
        [, ,
         Paragraph(f____ _____________ {year} г., right)],
    ]
    header_table = Table(header_data, colWidths=[110 * mm, 57 * mm, 100 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 5 * mm))

    elements.append(Paragraph('ГРАФИК ОТПУСКОВ', title_style))
    elements.append(Paragraph('Унифицированная форма № Т-7', center))
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph(f'на {year} год', center))
    elements.append(Spacer(1, 5 * mm))

    # Table header
    # Полезная ширина: 297 - 15 - 15 = 267 мм
    # 8+35+50+32+16+40+40+18+28 = 267 мм
    col_widths = [8 * mm, 35 * mm, 50 * mm, 32 * mm, 16 * mm, 40 * mm, 40 * mm, 18 * mm, 28 * mm]

    table_data = [
        [Paragraph('№<br/>п/п', small_center),
         Paragraph('Структурное<br/>подразделение', small_center),
         Paragraph('Фамилия, имя,<br/>отчество', small_center),
         Paragraph('Должность', small_center),
         Paragraph('Кол-во<br/>дней', small_center),
         Paragraph('Запланированная<br/>дата', small_center),
         Paragraph('Фактическая<br/>дата', small_center),
         Paragraph('Перенос', small_center),
         Paragraph('Примечание', small_center)],
    ]

    for idx, entry in enumerate(entries, 1):
        emp = entry.employee
        dept = emp.department.name if emp.department else ''

        periods = []
        days_planned = 0
        for i in range(1, 4):
            s = getattr(entry, f'period{i}_start')
            e = getattr(entry, f'period{i}_end')
            if s and e:
                periods.append(f'{s.strftime("%d.%m.%Y")} - {e.strftime("%d.%m.%Y")}')
                days_planned += (e - s).days + 1
        if entry.north_start and entry.north_end:
            periods.append(f'Сев: {entry.north_start.strftime("%d.%m.%Y")} - {entry.north_end.strftime("%d.%m.%Y")}')
            days_planned += (entry.north_end - entry.north_start).days + 1
        if entry.extra_start and entry.extra_end:
            periods.append(f'Доп: {entry.extra_start.strftime("%d.%m.%Y")} - {entry.extra_end.strftime("%d.%m.%Y")}')
            days_planned += (entry.extra_end - entry.extra_start).days + 1
        planned = '\n'.join(periods) if periods else ''
        days_display = days_planned if days_planned > 0 else entry.days_total_all

        table_data.append([
            Paragraph(str(idx), small_center),
            Paragraph(dept, small),
            Paragraph(emp.full_name, small),
            Paragraph(emp.position or '', small),
            Paragraph(str(days_display), small_center),
            Paragraph(planned, small),
            Paragraph('', small),
            Paragraph('', small_center),
            Paragraph('', small),
        ])

    # Add empty rows if less than 5
    for i in range(max(0, 5 - len(entries))):
        table_data.append([
            Paragraph(str(len(entries) + i + 1), small_center),
            '', '', '', '', '', '', '', '',
        ])

    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    main_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(main_table)
    elements.append(Spacer(1, 10 * mm))

    # Footer
    director_position = 'Ответственное лицо'
    director_name = ''
    elements.append(Paragraph(
        f'{director_position}: _______________________________',
        normal
    ))
    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph(
        f'Дата составления: "____" _____________ {year} г.',
        normal
    ))

    doc.build(elements)
    return buffer.getvalue()
