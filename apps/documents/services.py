import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os


def _register_fonts():
    """Register fonts for PDF generation."""
    try:
        font_paths = [
            '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
            '/usr/share/fonts/liberation/LiberationSerif-Regular.ttf',
        ]
        for path in font_paths:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont('LiberationSerif', path))
                return 'LiberationSerif'
    except Exception:
        pass
    return 'Helvetica'



def _get_company_info(employee):
    """Возвращает словарь с реквизитами компании из модели."""
    if not hasattr(employee, "company") or not employee.company:
        return {"name": "", "inn": "", "ogrn": "", "kpp": "", "okpo": "",
                "legal_address": "", "director_name": "", "director_position": "Директор",
                "phone": "", "email": ""}
    c = employee.company
    return {
        "name":              c.name or "",
        "inn":               getattr(c, "inn",               "") or "",
        "ogrn":              getattr(c, "ogrn",              "") or "",
        "kpp":               getattr(c, "kpp",               "") or "",
        "legal_address":     getattr(c, "legal_address",     "") or "",
        "director_name":     getattr(c, "director_name",     "") or "",
        "director_position": getattr(c, "director_position", "Директор") or "Директор",
        "phone":             getattr(c, "phone",             "") or "",
        "email":             getattr(c, "email",             "") or "",
        "okpo":              getattr(c, "okpo",              "") or "",
    }

def _get_ru_holidays(year):
    """Производственный календарь РФ — нерабочие праздничные дни.
    Берёт данные из модели ProductionCalendar, при отсутствии —
    фоллбэк на статический список.
    """
    from datetime import date
    try:
        from apps.employees.models import ProductionCalendar
        db_holidays = set(
            ProductionCalendar.objects.filter(
                date__year=year, day_type='holiday'
            ).values_list('date', flat=True)
        )
        if db_holidays:
            return db_holidays
    except Exception:
        pass
    # Фоллбэк — статический список (без переносов)
    fixed = [
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5),  # Новый год
        (1, 7),                                      # Рождество
        (2, 23),                                     # День защитника
        (3, 8),                                      # 8 Марта
        (5, 1),                                      # Праздник труда
        (5, 9),                                      # День Победы
        (6, 12),                                     # День России
        (11, 4),                                     # День народного единства
    ]
    return {date(year, m, d) for m, d in fixed}


def generate_t1_pdf(employee, order_number='П-001') -> bytes:
    """Generate T-1 HR order PDF for an employee."""
    font_name = _register_fonts()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=20*mm,
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        'Normal',
        fontName=font_name,
        fontSize=9,
        leading=12,
    )
    center = ParagraphStyle(
        'Center',
        fontName=font_name,
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
    )
    title_style = ParagraphStyle(
        'Title',
        fontName=font_name,
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    small = ParagraphStyle(
        'Small',
        fontName=font_name,
        fontSize=7,
        leading=9,
        alignment=TA_CENTER,
        textColor=colors.grey,
    )

    story = []

    # Header — organization name + реквизиты
    co = _get_company_info(employee)
    company_name = co['name']
    header_parts = [company_name or 'Наименование организации']
    if co['inn']:          header_parts.append('ИНН: ' + co['inn'])
    if co['ogrn']:         header_parts.append('ОГРН: ' + co['ogrn'])
    if co['legal_address']:header_parts.append(co['legal_address'])
    story.append(Paragraph(' | '.join(header_parts), normal))
    story.append(Paragraph('(наименование организации)', small))
    story.append(Spacer(1, 3*mm))

    # OKPO
    story.append(Paragraph('Код по ОКПО: ' + (co.get('okpo') or '___________'), normal))
    story.append(Spacer(1, 3*mm))

    # Form number and title
    story.append(Paragraph('Унифицированная форма № Т-1', center))
    story.append(Paragraph('Утверждена Постановлением Госкомстата России', small))
    story.append(Paragraph('от 05.01.2004 № 1', small))
    story.append(Spacer(1, 2*mm))

    story.append(Paragraph('ПРИКАЗ', title_style))
    story.append(Paragraph('(распоряжение)', small))
    story.append(Paragraph('о приёме работника на работу', title_style))
    story.append(Spacer(1, 3*mm))

    # Order number and date
    hire_date = employee.hire_date.strftime('%d.%m.%Y') if employee.hire_date else '___.___.______'
    order_data = [
        ['Номер документа', 'Дата составления'],
        [order_number, hire_date],
    ]
    order_table = Table(order_data, colWidths=[80*mm, 80*mm])
    order_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
    ]))
    story.append(order_table)
    story.append(Spacer(1, 4*mm))

    # Employee details
    patronymic = employee.middle_name if employee.middle_name else ''
    full_name = '{} {} {}'.format(employee.last_name, employee.first_name, patronymic).strip()
    
    details = [
        ['Принять на работу:', hire_date],
        ['Фамилия, имя, отчество:', full_name],
        ['Дата рождения:', employee.birth_date.strftime('%d.%m.%Y') if employee.birth_date else ''],
        ['Табельный номер:', employee.personnel_number or str(employee.id)],
        ['Структурное подразделение:', employee.department.name if hasattr(employee, 'department') and employee.department else ''],
        ['Профессия (должность):', employee.position or ''],
        ['Тарифная ставка (оклад):', '{} руб.'.format(employee.salary) if employee.salary else ''],
        ['Испытательный срок (до):', employee.probation_end_date.strftime('%d.%m.%Y') if employee.probation_end_date else 'Без испытания'],
    ]

    details_table = Table(details, colWidths=[90*mm, 80*mm])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN', (0,0), (-1,0), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('LINEBELOW', (1,0), (1,-1), 0.5, colors.black),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 6*mm))

    # Basis
    story.append(Paragraph('Основание: трудовой договор № _______ от ___________ г.', normal))
    story.append(Spacer(1, 6*mm))

    # Signatures
    sig_data = [
        ['Руководитель организации:', '', '', ''],
        ['должность', '', 'подпись', 'расшифровка подписи'],
        ['', '', '', ''],
        ['С приказом (распоряжением)', '', '', ''],
        ['работник ознакомлен:', '', '____________', '___.___.______'],
        ['', '', 'подпись', 'дата'],
    ]
    sig_table = Table(sig_data, colWidths=[55*mm, 40*mm, 35*mm, 45*mm])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('LINEBELOW', (1,0), (1,0), 0.5, colors.black),
        ('LINEBELOW', (2,0), (2,0), 0.5, colors.black),
        ('LINEBELOW', (3,0), (3,0), 0.5, colors.black),
        ('LINEBELOW', (2,3), (2,3), 0.5, colors.black),
        ('LINEBELOW', (3,3), (3,3), 0.5, colors.black),
        ('ALIGN', (0,1), (-1,1), 'CENTER'),
        ('ALIGN', (0,4), (-1,5), 'CENTER'),
        ('TEXTCOLOR', (0,1), (-1,1), colors.grey),
        ('TEXTCOLOR', (0,5), (-1,5), colors.grey),
        ('FONTSIZE', (0,1), (-1,1), 7),
        ('FONTSIZE', (0,5), (-1,5), 7),
    ]))
    story.append(sig_table)

    doc.build(story)
    return buffer.getvalue()


def generate_t2_pdf(employee) -> bytes:
    """Личная карточка работника Т-2."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)

    story = []
    co = _get_company_info(employee)
    company_name = co["name"]
    director = co["director_name"]
    inn_co = co["inn"]
    address_co = co["legal_address"]
    story.append(Paragraph(company_name or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Унифицированная форма № Т-2", center))
    story.append(Paragraph("ЛИЧНАЯ КАРТОЧКА РАБОТНИКА", title))
    story.append(Spacer(1, 4*mm))

    full_name = f"{employee.last_name} {employee.first_name} {employee.middle_name}".strip()
    birth = employee.birth_date.strftime("%d.%m.%Y") if employee.birth_date else ""
    hire  = employee.hire_date.strftime("%d.%m.%Y") if employee.hire_date else ""
    prob  = employee.probation_end_date.strftime("%d.%m.%Y") if employee.probation_end_date else "Без испытания"


    _edu_labels = {"secondary": "Среднее", "secondary_special": "Среднее специальное",
                   "incomplete_higher": "Неполное высшее", "higher": "Высшее",
                   "two_higher": "Два высших", "postgraduate": "Аспирантура / учёная степень"}
    _edu_raw = getattr(employee, 'education', '') or ''
    _edu_val = _edu_labels.get(_edu_raw, _edu_raw)
    _marital_labels = {
        "single": "Не женат / Не замужем", "married": "Женат / Замужем",
        "divorced": "Разведён / Разведена", "widowed": "Вдовец / Вдова",
        "cohabiting": "Гражданский брак",
    }
    _marital_raw = getattr(employee, 'marital_status', '') or ''
    _marital_val = _marital_labels.get(_marital_raw, _marital_raw)
    rows = [
        ["1. Фамилия, имя, отчество:", full_name],
        ["2. Дата рождения:", birth],
        ["3. Место рождения:", getattr(employee, "birth_place", "") or ""],
        ["4. Гражданство:", getattr(employee, "citizenship", "") or "Российская Федерация"],
        ["5. Семейное положение:", _marital_val],
        ["6. ИНН:", employee.inn or ""],
        ["7. СНИЛС:", employee.snils or ""],
        ["8. Образование:", _edu_val],
        ["9. Профессия (должность):", employee.position or ""],
        ["10. Дата приёма:", hire],
        ["11. Испытательный срок (до):", prob],
        ["12. Оклад:", f"{employee.salary} руб." if employee.salary else ""],
        ["13. Телефон:", employee.phone or ""],
        ["14. Email:", employee.email or ""],
        ["15. Серия/номер паспорта:", f"{employee.passport_series} {employee.passport_number}".strip()],
        ["16. Паспорт выдан:", employee.passport_issued_by or ""],
        ["17. Адрес регистрации:", employee.passport_registration or ""],
    ]
    t = Table(rows, colWidths=[80*mm, 95*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("LINEBELOW", (1,0), (1,-1), 0.3, colors.black),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Работник: ________________  /___________________/", normal))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("Специалист по кадрам: ________________  /___________________/", normal))
    doc.build(story)
    return buffer.getvalue()


def generate_t8_pdf(employee, order_number="У-001") -> bytes:
    """Приказ об увольнении Т-8."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)

    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)

    story = []
    co = _get_company_info(employee)
    company_name = co["name"]
    director = co["director_name"]
    inn_co = co["inn"]
    address_co = co["legal_address"]
    story.append(Paragraph(company_name or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Унифицированная форма № Т-8", center))
    story.append(Paragraph("Утверждена Постановлением Госкомстата России от 05.01.2004 № 1", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("ПРИКАЗ (РАСПОРЯЖЕНИЕ)", title))
    story.append(Paragraph("о прекращении (расторжении) трудового договора с работником (увольнении)", center))
    story.append(Spacer(1, 3*mm))

    today = employee.fire_date.strftime("%d.%m.%Y") if employee.fire_date else "___.___.______"
    order_data = [["Номер документа", "Дата составления"], [order_number, today]]
    ot = Table(order_data, colWidths=[80*mm, 80*mm])
    ot.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name), ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (0,0), (-1,-1), "CENTER"), ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
    ]))
    story.append(ot)
    story.append(Spacer(1, 4*mm))

    full_name = f"{employee.last_name} {employee.first_name} {employee.middle_name}".strip()
    hire = employee.hire_date.strftime("%d.%m.%Y") if employee.hire_date else ""
    rows = [
        ["Прекратить действие трудового договора:", today],
        ["Уволить (дата):", today],
        ["Фамилия, имя, отчество:", full_name],
        ["Табельный номер:", employee.personnel_number or str(employee.id)],
        ["Профессия (должность):", employee.position or ""],
        ["Структурное подразделение:", employee.department.name if employee.department else ""],
        ["Основание увольнения (ст. ТК РФ):", "п. 3 ч. 1 ст. 77 ТК РФ (собственное желание)"],
    ]
    t = Table(rows, colWidths=[90*mm, 80*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name), ("FONTSIZE", (0,0), (-1,-1), 9),
        ("LINEBELOW", (1,0), (1,-1), 0.5, colors.black),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Основание прекращения договора (ст. ТК РФ): п. 3 ч. 1 ст. 77 ТК РФ", normal))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Документ-основание: заявление работника от ___________ г.", normal))
    story.append(Spacer(1, 6*mm))
    sig_data = [
        ["Руководитель:", co["director_position"] or "Директор", "", ""],
        ["", "", "подпись", co["director_name"] or "расшифровка подписи"],
        ["", "", "", ""],
        ["С приказом работник ознакомлен:", "", "____________", "___.___.______"],
        ["", "", "подпись", "дата"],
    ]
    st = Table(sig_data, colWidths=[60*mm, 35*mm, 35*mm, 45*mm])
    st.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name), ("FONTSIZE", (0,0), (-1,-1), 8),
        ("LINEBELOW", (1,0), (1,0), 0.5, colors.black), ("LINEBELOW", (2,0), (2,0), 0.5, colors.black),
        ("LINEBELOW", (3,0), (3,0), 0.5, colors.black), ("LINEBELOW", (2,3), (2,3), 0.5, colors.black),
        ("LINEBELOW", (3,3), (3,3), 0.5, colors.black),
        ("ALIGN", (0,1), (-1,1), "CENTER"), ("ALIGN", (0,4), (-1,4), "CENTER"),
        ("TEXTCOLOR", (0,1), (-1,1), colors.grey), ("TEXTCOLOR", (0,4), (-1,4), colors.grey),
        ("FONTSIZE", (0,1), (-1,1), 7), ("FONTSIZE", (0,4), (-1,4), 7),
    ]))
    story.append(st)
    doc.build(story)
    return buffer.getvalue()


_VACATION_TYPE_DISPLAY = {
    'annual':      'Ежегодный основной оплачиваемый',
    'additional':  'Дополнительный оплачиваемый',
    'unpaid':      'Без сохранения заработной платы',
    'educational': 'Учебный',
    'maternity':   'По беременности и родам',
}

def _vacation_type_display(vacation_type):
    return _VACATION_TYPE_DISPLAY.get(vacation_type, 'Ежегодный основной оплачиваемый')


def generate_t6_pdf(employee, vacation_start=None, vacation_end=None, order_number="О-001", vacation_type=None) -> bytes:
    """Приказ об отпуске Т-6."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)

    from datetime import date as dt_date
    today = dt_date.today()
    v_start = vacation_start or today
    v_end   = vacation_end or today
    days = (v_end - v_start).days + 1

    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)

    story = []
    co = _get_company_info(employee)
    company_name = co["name"]
    director = co["director_name"]
    inn_co = co["inn"]
    address_co = co["legal_address"]
    story.append(Paragraph(company_name or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Унифицированная форма № Т-6", center))
    story.append(Paragraph("Утверждена Постановлением Госкомстата России от 05.01.2004 № 1", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("ПРИКАЗ (РАСПОРЯЖЕНИЕ)", title))
    story.append(Paragraph("о предоставлении отпуска работнику", center))
    story.append(Spacer(1, 3*mm))

    order_data = [["Номер документа", "Дата составления"], [order_number, today.strftime("%d.%m.%Y")]]
    ot = Table(order_data, colWidths=[80*mm, 80*mm])
    ot.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name), ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (0,0), (-1,-1), "CENTER"), ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
    ]))
    story.append(ot)
    story.append(Spacer(1, 4*mm))

    full_name = f"{employee.last_name} {employee.first_name} {employee.middle_name}".strip()
    hire = employee.hire_date.strftime("%d.%m.%Y") if employee.hire_date else ""
    rows = [
        ["Фамилия, имя, отчество:", full_name],
        ["Табельный номер:", employee.personnel_number or str(employee.id)],
        ["Профессия (должность):", employee.position or ""],
        ["Структурное подразделение:", employee.department.name if employee.department else ""],
        ["За период работы:", f"с {hire} по ___.___.______"],
        ["Вид отпуска:", _vacation_type_display(vacation_type)],
        ["Количество календарных дней:", str(days)],
        ["Дата начала:", v_start.strftime("%d.%m.%Y")],
        ["Дата окончания:", v_end.strftime("%d.%m.%Y")],
    ]
    t = Table(rows, colWidths=[90*mm, 80*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name), ("FONTSIZE", (0,0), (-1,-1), 9),
        ("LINEBELOW", (1,0), (1,-1), 0.5, colors.black),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))
    sig_data = [
        ["Руководитель:", co["director_position"] or "Директор", "", ""],
        ["", "", "подпись", co["director_name"] or "расшифровка подписи"],
        ["", "", "", ""],
        ["С приказом работник ознакомлен:", "", "____________", "___.___.______"],
        ["", "", "подпись", "дата"],
    ]
    st = Table(sig_data, colWidths=[60*mm, 35*mm, 35*mm, 45*mm])
    st.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name), ("FONTSIZE", (0,0), (-1,-1), 8),
        ("LINEBELOW", (1,0), (1,0), 0.5, colors.black), ("LINEBELOW", (2,0), (2,0), 0.5, colors.black),
        ("LINEBELOW", (3,0), (3,0), 0.5, colors.black), ("LINEBELOW", (2,3), (2,3), 0.5, colors.black),
        ("LINEBELOW", (3,3), (3,3), 0.5, colors.black),
        ("ALIGN", (0,1), (-1,1), "CENTER"), ("ALIGN", (0,4), (-1,4), "CENTER"),
        ("TEXTCOLOR", (0,1), (-1,1), colors.grey), ("TEXTCOLOR", (0,4), (-1,4), colors.grey),
        ("FONTSIZE", (0,1), (-1,1), 7), ("FONTSIZE", (0,4), (-1,4), 7),
    ]))
    story.append(st)
    doc.build(story)
    return buffer.getvalue()

def generate_additional_vacation_application(vacation) -> bytes:
    """Заявление на дополнительный оплачиваемый отпуск (PDF)."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=25*mm, rightMargin=15*mm, topMargin=20*mm, bottomMargin=20*mm)

    from datetime import date as dt_date
    employee = vacation.employee
    co = _get_company_info(employee)

    normal = ParagraphStyle("N", fontName=font_name, fontSize=12, leading=16)
    center = ParagraphStyle("C", fontName=font_name, fontSize=12, leading=16, alignment=TA_CENTER)
    right  = ParagraphStyle("R", fontName=font_name, fontSize=12, leading=16, alignment=TA_RIGHT)
    small  = ParagraphStyle("S", fontName=font_name, fontSize=10, leading=13)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=14, leading=18, alignment=TA_CENTER)

    story = []

    # Шапка — кому
    director_position = co["director_position"] or "Директору"
    director_name = co["director_name"] or "________________"
    company_name = co["name"] or "________________"
    story.append(Paragraph(f"{director_position}", right))
    story.append(Paragraph(f"{company_name}", right))
    story.append(Paragraph(f"{director_name}", right))
    story.append(Spacer(1, 3*mm))

    full_name = f"{employee.last_name} {employee.first_name} {employee.middle_name}".strip()
    position = employee.position or ""
    story.append(Paragraph(f"от {full_name}", right))
    story.append(Paragraph(f"{position}", right))
    story.append(Spacer(1, 10*mm))

    story.append(Paragraph("Заявление", title))
    story.append(Spacer(1, 8*mm))

    start_str = vacation.start_date.strftime("%d.%m.%Y")
    end_str = vacation.end_date.strftime("%d.%m.%Y")
    days = vacation.days_count

    body_text = (
        f"Прошу предоставить мне дополнительный оплачиваемый отпуск "
        f"с {start_str} по {end_str} ({days} календарных дней)."
    )
    story.append(Paragraph(body_text, normal))
    story.append(Spacer(1, 6*mm))

    if vacation.reason:
        story.append(Paragraph(f"Основание: {vacation.reason}", normal))
        story.append(Spacer(1, 6*mm))

    today_str = dt_date.today().strftime("%d.%m.%Y")
    sig_data = [
        [today_str, "________________", full_name],
        ["дата", "подпись", "расшифровка подписи"],
    ]
    st = Table(sig_data, colWidths=[40*mm, 50*mm, 70*mm])
    st.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name), ("FONTSIZE", (0,0), (-1,-1), 10),
        ("LINEBELOW", (0,0), (0,0), 0.5, colors.black),
        ("LINEBELOW", (1,0), (1,0), 0.5, colors.black),
        ("LINEBELOW", (2,0), (2,0), 0.5, colors.black),
        ("ALIGN", (0,1), (-1,1), "CENTER"),
        ("TEXTCOLOR", (0,1), (-1,1), colors.grey),
        ("FONTSIZE", (0,1), (-1,1), 7),
    ]))
    story.append(st)

    doc.build(story)
    return buffer.getvalue()


def generate_t5_pdf(employee, new_position, new_salary=None, order_number="ПР-001") -> bytes:
    """Приказ о переводе на другую работу Т-5."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    story = []
    co = _get_company_info(employee)
    company_name = co["name"]
    director = co["director_name"]
    inn_co = co["inn"]
    address_co = co["legal_address"]
    story.append(Paragraph(company_name or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Унифицированная форма № Т-5", center))
    story.append(Paragraph("Утверждена Постановлением Госкомстата России от 05.01.2004 № 1", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("ПРИКАЗ (РАСПОРЯЖЕНИЕ)", title))
    story.append(Paragraph("о переводе работника на другую работу", center))
    story.append(Spacer(1, 3*mm))
    order_data = [["Номер документа", "Дата составления"], [order_number, today_str]]
    ot = Table(order_data, colWidths=[80*mm, 80*mm])
    ot.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("GRID",(0,0),(-1,-1),0.5,colors.black),
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
    ]))
    story.append(ot)
    story.append(Spacer(1, 4*mm))
    full_name = (employee.last_name + " " + employee.first_name + " " + employee.middle_name).strip()
    old_position = employee.position or "-"
    salary_text = (str(new_salary) + " руб.") if new_salary else "Без изменений"
    old_salary_str = (str(employee.salary) + " руб.") if employee.salary else "—"
    rows = [
        ["Фамилия, имя, отчество:", full_name],
        ["Табельный номер:", employee.personnel_number or str(employee.id)],
        ["Вид перевода:", "Постоянный"],
        ["Прежнее структурное подразделение:", employee.department.name if employee.department else "—"],
        ["Прежняя должность:", old_position],
        ["Прежний оклад:", old_salary_str],
        ["Новое структурное подразделение:", employee.department.name if employee.department else "—"],
        ["Новая должность:", new_position],
        ["Новый оклад:", salary_text],
        ["Дата перевода:", today_str],
        ["Основание:", "Заявление работника / доп. соглашение к ТД"],
    ]
    t = Table(rows, colWidths=[90*mm, 80*mm])
    t.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("LINEBELOW",(1,0),(1,-1),0.5,colors.black),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Руководитель организации: ________________  /___________________/", normal))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("С приказом работник ознакомлен: ________________  ___.___.______", normal))
    doc.build(story)
    return buffer.getvalue()


def generate_salary_change_pdf(employee, new_salary, order_number="З-001", previous_salary=None, effective_date=None) -> bytes:
    """Приказ об изменении оклада."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    effective_date_str = effective_date.strftime("%d.%m.%Y") if effective_date else today_str
    story = []
    co = _get_company_info(employee)
    company_name = co["name"]
    director = co["director_name"]
    inn_co = co["inn"]
    address_co = co["legal_address"]
    story.append(Paragraph(company_name or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("ПРИКАЗ", title))
    story.append(Paragraph("N " + order_number + " от " + today_str + " г.", center))
    story.append(Paragraph("об изменении размера оклада", center))
    story.append(Spacer(1, 5*mm))
    full_name = (employee.last_name + " " + employee.first_name + " " + employee.middle_name).strip()
    position = employee.position or "должность"
    # Прежний оклад: используем явно переданное значение, иначе из истории
    if not previous_salary:
        from apps.employees.models import SalaryHistory
        salary_hist = employee.salary_history.order_by('-effective_date', '-created_at').first()
        previous_salary = salary_hist.salary if salary_hist else None
    old_salary_text = (" Прежний оклад: " + str(previous_salary) + " руб.") if previous_salary else ""
    story.append(Paragraph("Основание: дополнительное соглашение к трудовому договору N ______ от ___________ г. (ст. 72 ТК РФ)", normal))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("В связи с соглашением сторон <b>ПРИКАЗЫВАЮ:</b>", normal))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "1. Установить " + full_name + ", " + position +
        ", должностной оклад в размере <b>" + str(new_salary) + " (рублей)</b> в месяц с " + effective_date_str + " г." + old_salary_text,
        normal))
    story.append(Paragraph(
        "2. Бухгалтерии производить начисление заработной платы в соответствии с настоящим приказом.", normal))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Руководитель организации: ________________  /___________________/", normal))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("С приказом ознакомлен: ________________  " + today_str, normal))
    doc.build(story)
    return buffer.getvalue()


def generate_transfer_order_pdf(employee, new_position, new_salary=None, order_number="ПР-001", transfer_date=None, reason=None) -> bytes:
    """Приказ о переводе работника на другую работу (Т-5) — через форму."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    transfer_date_str = transfer_date or today_str
    story = []
    co = _get_company_info(employee)
    story.append(Paragraph(co["name"] or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Унифицированная форма № Т-5", center))
    story.append(Paragraph("Утверждена Постановлением Госкомстата России от 05.01.2004 № 1", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("ПРИКАЗ (РАСПОРЯЖЕНИЕ)", title))
    story.append(Paragraph("о переводе работника на другую работу", center))
    story.append(Spacer(1, 3*mm))
    order_data = [["Номер документа", "Дата составления"], [order_number, today_str]]
    ot = Table(order_data, colWidths=[80*mm, 80*mm])
    ot.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("GRID",(0,0),(-1,-1),0.5,colors.black),
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
    ]))
    story.append(ot)
    story.append(Spacer(1, 4*mm))
    full_name = (employee.last_name + " " + employee.first_name + " " + (employee.middle_name or "")).strip()
    old_position = employee.position or "—"
    old_salary_str = (str(employee.salary) + " руб.") if employee.salary else "—"
    salary_text = (str(new_salary) + " руб.") if new_salary else "Без изменений"
    reason_text = reason or "Заявление работника / доп. соглашение к ТД"
    rows = [
        ["Фамилия, имя, отчество:", full_name],
        ["Табельный номер:", employee.personnel_number or str(employee.id)],
        ["Прежняя должность:", old_position],
        ["Прежний оклад:", old_salary_str],
        ["Новая должность:", new_position],
        ["Новый оклад:", salary_text],
        ["Дата перевода:", transfer_date_str],
        ["Основание:", reason_text],
    ]
    t = Table(rows, colWidths=[90*mm, 80*mm])
    t.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("LINEBELOW",(1,0),(1,-1),0.5,colors.black),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Руководитель организации: ________________  /___________________/", normal))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("С приказом работник ознакомлен: ________________  ___.___.______", normal))
    doc.build(story)
    return buffer.getvalue()


def generate_dismissal_order_pdf(employee, order_number="У-001", dismissal_date=None, dismissal_reason=None, dismissal_basis_doc=None) -> bytes:
    """Приказ об увольнении (Т-8) — через форму."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    dismiss_date_str = dismissal_date or today_str
    dismiss_reason = dismissal_reason or "По собственному желанию (п. 3 ч. 1 ст. 77 ТК РФ)"
    basis_doc = dismissal_basis_doc or "Заявление работника"
    story = []
    co = _get_company_info(employee)
    story.append(Paragraph(co["name"] or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Унифицированная форма № Т-8", center))
    story.append(Paragraph("Утверждена Постановлением Госкомстата России от 05.01.2004 № 1", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("ПРИКАЗ (РАСПОРЯЖЕНИЕ)", title))
    story.append(Paragraph("о прекращении (расторжении) трудового договора с работником (увольнении)", center))
    story.append(Spacer(1, 3*mm))
    order_data = [["Номер документа", "Дата составления"], [order_number, today_str]]
    ot = Table(order_data, colWidths=[80*mm, 80*mm])
    ot.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("GRID",(0,0),(-1,-1),0.5,colors.black),
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
    ]))
    story.append(ot)
    story.append(Spacer(1, 4*mm))
    full_name = (employee.last_name + " " + employee.first_name + " " + (employee.middle_name or "")).strip()
    rows = [
        ["Уволить:", full_name],
        ["Должность:", employee.position or "—"],
        ["Табельный номер:", employee.personnel_number or str(employee.id)],
        ["Структурное подразделение:", employee.department.name if employee.department else "—"],
        ["Дата увольнения:", dismiss_date_str],
        ["Основание:", dismiss_reason],
        ["Документ-основание:", basis_doc],
    ]
    t = Table(rows, colWidths=[90*mm, 80*mm])
    t.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("LINEBELOW",(1,0),(1,-1),0.5,colors.black),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))
    sig_data = [
        ["Руководитель:", co["director_position"] or "Директор", "", ""],
        ["", "", "подпись", co["director_name"] or "расшифровка подписи"],
        ["", "", "", ""],
        ["С приказом работник ознакомлен:", "", "____________", "___.___.______"],
        ["", "", "подпись", "дата"],
    ]
    st = Table(sig_data, colWidths=[60*mm, 35*mm, 35*mm, 45*mm])
    st.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),8),
        ("LINEBELOW",(1,0),(1,0),0.5,colors.black),("LINEBELOW",(2,0),(2,0),0.5,colors.black),
        ("LINEBELOW",(3,0),(3,0),0.5,colors.black),("LINEBELOW",(2,3),(2,3),0.5,colors.black),
        ("LINEBELOW",(3,3),(3,3),0.5,colors.black),
        ("ALIGN",(0,1),(-1,1),"CENTER"),("ALIGN",(0,4),(-1,4),"CENTER"),
        ("TEXTCOLOR",(0,1),(-1,1),colors.grey),("TEXTCOLOR",(0,4),(-1,4),colors.grey),
        ("FONTSIZE",(0,1),(-1,1),7),("FONTSIZE",(0,4),(-1,4),7),
    ]))
    story.append(st)
    doc.build(story)
    return buffer.getvalue()


def generate_bonus_order_pdf(employee, bonus_amount, order_number="П-001", reason=None, payment_date=None) -> bytes:
    """Приказ о премии (произвольная форма)."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    reason_text = reason or "За добросовестное исполнение трудовых обязанностей"
    payment_date_str = payment_date or today_str
    story = []
    co = _get_company_info(employee)
    story.append(Paragraph(co["name"] or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("ПРИКАЗ", title))
    story.append(Paragraph("N " + order_number + " от " + today_str + " г.", center))
    story.append(Paragraph("о поощрении работника", center))
    story.append(Spacer(1, 5*mm))
    full_name = (employee.last_name + " " + employee.first_name + " " + (employee.middle_name or "")).strip()
    position = employee.position or "должность"
    story.append(Paragraph(
        "В связи с: <b>" + reason_text + "</b>", normal))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("<b>ПРИКАЗЫВАЮ:</b>", normal))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "1. Поощрить " + full_name + ", " + position +
        ", премией в размере <b>" + str(bonus_amount) + " (рублей)</b>.",
        normal))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "2. Выплатить премию: " + payment_date_str + " г.", normal))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "3. Бухгалтерии произвести начисление и выплату премии.", normal))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Руководитель организации: ________________  /___________________/", normal))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("С приказом ознакомлен: ________________  " + today_str, normal))
    doc.build(story)
    return buffer.getvalue()


def generate_disciplinary_order_pdf(employee, penalty_type, order_number="ДВ-001", violation_date=None, violation_description=None, reason=None) -> bytes:
    """Приказ о дисциплинарном взыскании (произвольная форма)."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    small  = ParagraphStyle("S", fontName=font_name, fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.grey)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    penalty = penalty_type or "Выговор"
    violation_date_str = violation_date or today_str
    violation_desc = violation_description or "Нарушение трудовой дисциплины"
    reason_text = reason or "Акт о нарушении трудовой дисциплины"
    story = []
    co = _get_company_info(employee)
    story.append(Paragraph(co["name"] or "Наименование организации", center))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("ПРИКАЗ", title))
    story.append(Paragraph("N " + order_number + " от " + today_str + " г.", center))
    story.append(Paragraph("о применении дисциплинарного взыскания", center))
    story.append(Spacer(1, 5*mm))
    full_name = (employee.last_name + " " + employee.first_name + " " + (employee.middle_name or "")).strip()
    position = employee.position or "должность"
    story.append(Paragraph(
        "В связи с нарушением трудовой дисциплины (дата нарушения: " + violation_date_str + "):", normal))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(violation_desc, normal))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("<b>ПРИКАЗЫВАЮ:</b>", normal))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "1. К " + full_name + ", " + position +
        ", применить дисциплинарное взыскание в виде: <b>" + penalty + "</b>.",
        normal))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "2. Основание: " + reason_text + ".", normal))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Руководитель организации: ________________  /___________________/", normal))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("С приказом ознакомлен: ________________  " + today_str, normal))
    doc.build(story)
    return buffer.getvalue()


def generate_work_certificate_pdf(employee) -> bytes:
    """Справка с места работы."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=10, leading=14, firstLineIndent=12)
    center = ParagraphStyle("C", fontName=font_name, fontSize=10, leading=14, alignment=TA_CENTER)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=12, leading=16, alignment=TA_CENTER)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    story = []
    co = _get_company_info(employee)
    company_name = co["name"] or "Организация"
    director = co["director_name"]
    inn_co = co["inn"]
    story.append(Paragraph(company_name, title))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("СПРАВКА", title))
    story.append(Paragraph("от " + today_str + " г.", center))
    story.append(Spacer(1, 8*mm))
    full_name = (employee.last_name + " " + employee.first_name + " " + employee.middle_name).strip()
    hire = employee.hire_date.strftime("%d.%m.%Y") if employee.hire_date else "___.___.______"
    position = employee.position or "-"
    salary_text = ("Должностной оклад составляет " + str(employee.salary) + " (рублей) в месяц. ") if employee.salary else ""
    story.append(Paragraph(
        "Настоящая справка выдана " + full_name + " в том, что он(а) действительно работает "
        + "в " + company_name + " в должности <b>" + position + "</b> "
        + "с " + hire + " г. по настоящее время. " + salary_text
        + "Справка выдана для предъявления по месту требования.", normal))
    story.append(Spacer(1, 12*mm))
    story.append(Paragraph("Руководитель: ________________  /___________________/", normal))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("М.П.", normal))
    doc.build(story)
    return buffer.getvalue()


def generate_labor_contract_pdf(employee) -> bytes:
    """Трудовой договор."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=13)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    story = []
    co = _get_company_info(employee)
    company_name = co["name"] or "Работодатель"
    director = co["director_name"]
    inn_co = co["inn"]
    address_co = co["legal_address"]
    full_name = (employee.last_name + " " + employee.first_name + " " + employee.middle_name).strip()
    hire = employee.hire_date.strftime("%d.%m.%Y") if employee.hire_date else today_str
    position = employee.position or "-"
    salary = str(employee.salary) if employee.salary else "-"
    passport = (employee.passport_series or "__") + " " + (employee.passport_number or "______")
    probation = employee.probation_end_date.strftime("%d.%m.%Y") if employee.probation_end_date else "не установлен"
    if employee.contract_end_date:
        contract_type = "срочный, до " + employee.contract_end_date.strftime("%d.%m.%Y") + " г."
    else:
        contract_type = "бессрочный"
    story.append(Paragraph("ТРУДОВОЙ ДОГОВОР", title))
    story.append(Paragraph("N ТД-" + str(employee.id) + " от " + hire + " г.", title))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(
        "<b>" + company_name + "</b> (далее — Работодатель), с одной стороны, и "
        "<b>" + full_name + "</b> (далее — Работник), с другой стороны, заключили настоящий договор:", normal))
    story.append(Spacer(1, 3*mm))
    paragraphs = [
        ("1. ПРЕДМЕТ ДОГОВОРА", [
            "1.1. Работодатель принимает Работника на должность <b>" + position + "</b>.",
            "1.2. Дата начала работы: " + hire + " г.",
            "1.3. Вид договора: " + contract_type + ".",
        ]),
        ("2. ПРАВА И ОБЯЗАННОСТИ РАБОТНИКА", [
            "2.1. Работник обязан добросовестно исполнять свои трудовые обязанности.",
            "2.2. Работник обязан соблюдать правила внутреннего трудового распорядка.",
            "2.3. Работник имеет право на предоставление работы, обусловленной договором.",
        ]),
        ("3. ОПЛАТА ТРУДА", [
            "3.1. Работнику устанавливается должностной оклад: <b>" + salary + " руб.</b> в месяц.",
            "3.2. Выплата заработной платы производится 2 раза в месяц.",
        ]),
        ("4. РЕЖИМ РАБОТЫ", [
            "4.1. Режим рабочего времени: пятидневная рабочая неделя, 40 часов.",
            "4.2. Ежегодный основной оплачиваемый отпуск: 28 календарных дней.",
        ]),
        ("5. ИСПЫТАТЕЛЬНЫЙ СРОК", [
            "5.1. Работнику установлен испытательный срок до: " + probation + ".",
        ]),
        ("6. ГАРАНТИИ И КОМПЕНСАЦИИ", [
            "6.1. Работник подлежит обязательному социальному страхованию в соответствии с ФЗ от 29.12.2006 N 255-ФЗ, ФЗ от 15.12.2001 N 167-ФЗ.",
            "6.2. Условия труда на рабочем месте: допустимые (класс 2) — в соответствии с ФЗ от 28.12.2013 N 426-ФЗ.",
            "6.3. Работнику гарантируется ежегодный основной оплачиваемый отпуск продолжительностью 28 календарных дней (ст. 115 ТК РФ).",
        ]),
        ("7. ОТВЕТСТВЕННОСТЬ СТОРОН", [
            "7.1. Стороны несут ответственность за неисполнение обязательств по настоящему договору в соответствии с законодательством РФ.",
        ]),
        ("8. ПРОЧИЕ УСЛОВИЯ", [
            "8.1. Настоящий договор составлен в 2 экземплярах, по одному для каждой из сторон.",
            "8.2. Конкретные даты выплаты заработной платы: 5-е и 20-е число каждого месяца (ст. 136 ТК РФ).",
        ]),
    ]
    for section_title, items in paragraphs:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph("<b>" + section_title + "</b>", normal))
        for item in items:
            story.append(Paragraph(item, normal))
    story.append(Spacer(1, 8*mm))
    employer_details = company_name
    if inn_co:
        employer_details += "\nИНН: " + inn_co
    if address_co:
        employer_details += "\n" + address_co
    if director:
        employer_details += "\nРуководитель: " + director
    sig = [
        ["РАБОТОДАТЕЛЬ:", "РАБОТНИК:"],
        [employer_details, full_name],
        ["", "Паспорт: " + passport],
        ["Подпись: ________________", "Подпись: ________________"],
        ["Дата: " + today_str, "Дата: " + today_str],
    ]
    st = Table(sig, colWidths=[85*mm, 85*mm])
    st.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),3),
    ]))
    story.append(st)
    doc.build(story)
    return buffer.getvalue()


def generate_gph_contract_pdf(employee) -> bytes:
    """Договор ГПХ."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=13)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    story = []
    co = _get_company_info(employee)
    company_name = co["name"] or "Заказчик"
    director = co["director_name"]
    inn_co = co["inn"]
    address_co = co["legal_address"]
    full_name = (employee.last_name + " " + employee.first_name + " " + employee.middle_name).strip()
    hire = employee.hire_date.strftime("%d.%m.%Y") if employee.hire_date else today_str
    position = employee.position or "-"
    salary = str(employee.salary) if employee.salary else "-"
    inn = employee.inn or "-"
    story.append(Paragraph("ДОГОВОР ОКАЗАНИЯ УСЛУГ (ГПХ)", title))
    story.append(Paragraph("N ГПХ-" + str(employee.id) + " от " + hire + " г.", title))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(
        "<b>" + company_name + "</b> (далее — Заказчик), с одной стороны, и "
        "<b>" + full_name + "</b> (далее — Исполнитель), с другой стороны, заключили настоящий договор:", normal))
    story.append(Spacer(1, 3*mm))
    sections = [
        ("1. ПРЕДМЕТ ДОГОВОРА", [
            "1.1. Исполнитель обязуется оказывать услуги по направлению: <b>" + position + "</b>.",
            "1.2. Срок оказания услуг: с " + hire + " г.",
        ]),
        ("2. СТОИМОСТЬ И ПОРЯДОК ОПЛАТЫ", [
            "2.1. Стоимость услуг составляет <b>" + salary + " руб.</b> в месяц.",
            "2.2. Оплата производится на основании подписанного акта выполненных работ.",
        ]),
        ("3. ПРАВА И ОБЯЗАННОСТИ СТОРОН", [
            "3.1. Исполнитель обязан оказывать услуги лично и в согласованные сроки.",
            "3.2. Заказчик обязан принять и оплатить надлежащим образом оказанные услуги.",
        ]),
        ("4. ОТВЕТСТВЕННОСТЬ СТОРОН", [
            "4.1. За неисполнение или ненадлежащее исполнение обязательств стороны несут ответственность в соответствии с законодательством РФ.",
            "4.2. Заказчик вправе отказаться от договора при нарушении Исполнителем сроков оказания услуг.",
        ]),
        ("5. ПРОЧИЕ УСЛОВИЯ", [
            "5.1. Договор составлен в 2 экземплярах, имеющих одинаковую юридическую силу.",
            "5.2. Исполнитель является плательщиком НПД (самозанятый) / НДФЛ удерживается Заказчиком.",
            "5.3. Настоящий договор не является трудовым договором и не порождает трудовых отношений (ст. 15 ТК РФ).",
        ]),
    ]
    for section_title, items in sections:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph("<b>" + section_title + "</b>", normal))
        for item in items:
            story.append(Paragraph(item, normal))
    story.append(Spacer(1, 8*mm))
    zakazchik_details = company_name
    if inn_co:
        zakazchik_details += "\nИНН: " + inn_co
    if director:
        zakazchik_details += "\nРуководитель: " + director
    sig = [
        ["ЗАКАЗЧИК:", "ИСПОЛНИТЕЛЬ:"],
        [zakazchik_details, full_name],
        ["", "ИНН: " + inn],
        ["Подпись: ________________", "Подпись: ________________"],
        ["Дата: " + today_str, "Дата: " + today_str],
    ]
    st = Table(sig, colWidths=[85*mm, 85*mm])
    st.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),3),
    ]))
    story.append(st)
    doc.build(story)
    return buffer.getvalue()


def generate_gph_act_pdf(employee, work_description=None, amount=None) -> bytes:
    """Акт выполненных работ (ГПХ)."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=20*mm)
    normal = ParagraphStyle("N", fontName=font_name, fontSize=9, leading=13)
    title  = ParagraphStyle("T", fontName=font_name, fontSize=11, leading=14, alignment=TA_CENTER)
    from datetime import date as dt_date
    today = dt_date.today()
    today_str = today.strftime("%d.%m.%Y")
    story = []
    co = _get_company_info(employee)
    company_name = co["name"] or "Заказчик"
    director = co["director_name"]
    inn_co = co["inn"]
    address_co = co["legal_address"]
    full_name = (employee.last_name + " " + employee.first_name + " " + employee.middle_name).strip()
    work_desc = work_description or employee.position or "Услуги согласно договору ГПХ"
    act_amount = str(amount or employee.salary or "-")
    story.append(Paragraph("АКТ ВЫПОЛНЕННЫХ РАБОТ (ОКАЗАННЫХ УСЛУГ)", title))
    story.append(Paragraph("N АКТ-" + str(employee.id) + " от " + today_str + " г.", title))
    story.append(Spacer(1, 5*mm))
    contract_ref = "N ГПХ-" + str(employee.id)
    story.append(Paragraph(
        "<b>" + company_name + "</b> (Заказчик) и <b>" + full_name + "</b> (Исполнитель) "
        "составили настоящий акт в соответствии с договором оказания услуг "
        + contract_ref + " о том, что Исполнитель выполнил следующие работы (услуги) "
        "в полном объёме и надлежащего качества:", normal))
    story.append(Spacer(1, 3*mm))
    work_rows = [
        ["N", "Наименование услуги", "Сумма (руб.)"],
        ["1", work_desc, act_amount],
        ["", "ИТОГО:", act_amount],
    ]
    wt = Table(work_rows, colWidths=[10*mm, 120*mm, 35*mm])
    wt.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("GRID",(0,0),(-1,-1),0.5,colors.black),
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
        ("ALIGN",(2,0),(2,-1),"RIGHT"),
    ]))
    story.append(wt)
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("Услуги оказаны в полном объёме. Стороны претензий друг к другу не имеют.", normal))
    story.append(Spacer(1, 8*mm))
    company_name_with_director = company_name
    if director:
        company_name_with_director = company_name + "\nРуководитель: " + director
    sig = [
        ["ЗАКАЗЧИК:", "ИСПОЛНИТЕЛЬ:"],
        [company_name_with_director, full_name],
        ["Подпись: ________________", "Подпись: ________________"],
        ["Дата: " + today_str, "Дата: " + today_str],
    ]
    st = Table(sig, colWidths=[85*mm, 85*mm])
    st.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),9),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),3),
    ]))
    story.append(st)
    doc.build(story)
    return buffer.getvalue()


def generate_t13_pdf(employees, year=None, month=None) -> bytes:
    """Табель учёта рабочего времени Т-13."""
    import calendar
    from reportlab.lib.pagesizes import landscape
    from datetime import date as dt_date
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=15*mm)
    normal  = ParagraphStyle("N",  fontName=font_name, fontSize=7, leading=9)
    title   = ParagraphStyle("T",  fontName=font_name, fontSize=10, leading=12,
                              alignment=TA_CENTER, spaceAfter=1)
    sub     = ParagraphStyle("S",  fontName=font_name, fontSize=8,  leading=10,
                              alignment=TA_CENTER, spaceAfter=0)
    today = dt_date.today()
    y = year or today.year
    m = month or today.month
    days_in_month = calendar.monthrange(y, m)[1]
    month_names = ["Январь","Февраль","Март","Апрель","Май","Июнь",
                   "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
    month_name = month_names[m-1]
    company_name = employees[0].company.name if employees and hasattr(employees[0], "company") and employees[0].company else ""
    story = []
    # Шапка: название компании — левее, форма и заголовок — по центру
    # Используем двухколоночную таблицу: [компания слева | форма справа]
    from reportlab.platypus import Table as _Tbl, TableStyle as _TS
    hdr_left  = ParagraphStyle("HL", fontName=font_name, fontSize=9, leading=11, alignment=0)  # LEFT
    hdr_right = ParagraphStyle("HR", fontName=font_name, fontSize=8, leading=10, alignment=2)  # RIGHT
    hdr_tbl = _Tbl(
        [[Paragraph(company_name or "Организация", hdr_left),
          Paragraph("Унифицированная форма N Т-13", hdr_right)]],
        colWidths=[None, 60*mm],
    )
    hdr_tbl.setStyle(_TS([
        ("VALIGN", (0,0), (-1,-1), "BOTTOM"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(hdr_tbl)
    story.append(Paragraph("ТАБЕЛЬ УЧЁТА РАБОЧЕГО ВРЕМЕНИ — " + month_name + " " + str(y) + " г.", title))
    story.append(Spacer(1, 3*mm))
    header = ["N", "ФИО / должность"] + [str(d) for d in range(1, days_in_month+1)] + ["Дней", "Часов"]
    col_widths = [7*mm, 48*mm] + [5.5*mm]*days_in_month + [11*mm, 11*mm]
    rows = [header]
    holidays = _get_ru_holidays(y)
    # Сокращённые предпраздничные дни (7 часов)
    try:
        from apps.employees.utils import get_holidays_and_short_days
        _, short_days = get_holidays_and_short_days(y, m)
    except Exception:
        short_days = set()
    # Определяем типы дней для подсветки (colspan не нужен — используем стили)
    day_types = []  # 'work', 'short', 'weekend', 'holiday'
    for d in range(1, days_in_month+1):
        date_d = dt_date(y, m, d)
        if date_d in holidays:
            day_types.append('holiday')
        elif date_d.weekday() >= 5:
            day_types.append('weekend')
        elif date_d in short_days:
            day_types.append('short')
        else:
            day_types.append('work')

    # Загружаем ручные отметки из БД
    import datetime as _dt_module
    start_d = _dt_module.date(y, m, 1)
    end_d   = _dt_module.date(y, m, days_in_month)
    try:
        from apps.employees.models import TimeRecord
        emp_ids = [e.id for e in employees]
        tr_qs = TimeRecord.objects.filter(
            employee_id__in=emp_ids,
            date__gte=start_d, date__lte=end_d
        )
        tr_map = {(r.employee_id, r.date.day): r for r in tr_qs}
    except Exception:
        tr_map = {}

    # Коды, при которых считаются рабочие дни и часы
    _WORK_CODES = {"Я", "К", "Я½", "РВ", "Я/С"}

    for i, emp in enumerate(employees, 1):
        ln = emp.last_name or ""
        fn = (emp.first_name[:1] + ".") if emp.first_name else ""
        mn = (emp.middle_name[:1] + ".") if emp.middle_name else ""
        short_name = ln + " " + fn + mn
        row = [str(i), short_name.strip() + "\n" + (emp.position or "")]
        work_days = 0
        work_hours = 0
        for d in range(1, days_in_month+1):
            rec = tr_map.get((emp.id, d))
            dtype = day_types[d-1]
            if rec:
                code = rec.code
                if code in _WORK_CODES:
                    hrs = rec.hours or (4 if code == "Я½" else 8)
                    work_days += 1
                    work_hours += hrs
                    row.append(code + "\n" + str(hrs))
                else:
                    # В, П, ОТ, ДО, ОД, УЧ, ОЖ, Б, НН — нерабочие коды
                    row.append(code + "\n")
            else:
                if dtype == 'work':
                    row.append("Я\n8")
                    work_days += 1
                    work_hours += 8
                elif dtype == 'short':
                    row.append("Я\n7")
                    work_days += 1
                    work_hours += 7
                elif dtype == 'holiday':
                    row.append("П\n")
                else:
                    row.append("В\n")
        row.append(str(work_days))
        row.append(str(work_hours))
        rows.append(row)
    t = Table(rows, colWidths=col_widths)
    # Базовые стили
    style_cmds = [
        ("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),6),
        ("GRID",(0,0),(-1,-1),0.3,colors.black),
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("ALIGN",(1,0),(1,-1),"LEFT"),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]
    # Подсветка выходных (серый) и праздников (светло-красный) в заголовке и ячейках
    for d_idx, dtype in enumerate(day_types):
        col = d_idx + 2  # смещение: 0=N, 1=ФИО, затем дни
        if dtype == 'weekend':
            style_cmds.append(("BACKGROUND", (col, 0), (col, -1), colors.Color(0.85, 0.85, 0.85)))
        elif dtype == 'holiday':
            style_cmds.append(("BACKGROUND", (col, 0), (col, -1), colors.Color(1.0, 0.75, 0.75)))
            style_cmds.append(("TEXTCOLOR", (col, 1), (col, -1), colors.Color(0.8, 0, 0)))
    t.setStyle(TableStyle(style_cmds))
    story.append(t)
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("Ответственный: ________________  /___________________/", normal))
    doc.build(story)
    return buffer.getvalue()
