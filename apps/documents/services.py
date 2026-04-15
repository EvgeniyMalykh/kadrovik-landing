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

    # Header — organization name
    company_name = ''
    if hasattr(employee, 'company') and employee.company:
        company_name = employee.company.name
    
    story.append(Paragraph(company_name or 'Наименование организации', normal))
    story.append(Paragraph('(наименование организации)', small))
    story.append(Spacer(1, 3*mm))

    # OKPO
    story.append(Paragraph('Код по ОКПО: ___________', normal))
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
        ['Табельный номер:', str(employee.id)],
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
    company_name = employee.company.name if hasattr(employee, "company") and employee.company else ""
    story.append(Paragraph(company_name or "Наименование организации", normal))
    story.append(Paragraph("(наименование организации)", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Унифицированная форма № Т-2", center))
    story.append(Paragraph("ЛИЧНАЯ КАРТОЧКА РАБОТНИКА", title))
    story.append(Spacer(1, 4*mm))

    full_name = f"{employee.last_name} {employee.first_name} {employee.middle_name}".strip()
    birth = employee.birth_date.strftime("%d.%m.%Y") if employee.birth_date else ""
    hire  = employee.hire_date.strftime("%d.%m.%Y") if employee.hire_date else ""
    prob  = employee.probation_end_date.strftime("%d.%m.%Y") if employee.probation_end_date else "Без испытания"

    rows = [
        ["1. Фамилия, имя, отчество:", full_name],
        ["2. Дата рождения:", birth],
        ["3. Место рождения:", ""],
        ["4. Гражданство:", "Российская Федерация"],
        ["5. ИНН:", employee.inn or ""],
        ["6. СНИЛС:", employee.snils or ""],
        ["7. Образование:", ""],
        ["8. Профессия (должность):", employee.position or ""],
        ["9. Дата приёма:", hire],
        ["10. Испытательный срок (до):", prob],
        ["11. Оклад:", f"{employee.salary} руб." if employee.salary else ""],
        ["12. Телефон:", employee.phone or ""],
        ["13. Email:", employee.email or ""],
        ["14. Серия/номер паспорта:", f"{employee.passport_series} {employee.passport_number}".strip()],
        ["15. Паспорт выдан:", employee.passport_issued_by or ""],
        ["16. Адрес регистрации:", employee.passport_registration or ""],
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
    company_name = employee.company.name if hasattr(employee, "company") and employee.company else ""
    story.append(Paragraph(company_name or "Наименование организации", normal))
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
        ["Прекратить действие трудового договора:", hire],
        ["Уволить:", today],
        ["Фамилия, имя, отчество:", full_name],
        ["Табельный номер:", str(employee.id)],
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
    story.append(Paragraph("Основание: заявление работника от ___________ г.", normal))
    story.append(Spacer(1, 6*mm))
    sig_data = [
        ["Руководитель организации:", "", "", ""],
        ["должность", "", "подпись", "расшифровка подписи"],
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


def generate_t6_pdf(employee, vacation_start=None, vacation_end=None, order_number="О-001") -> bytes:
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
    company_name = employee.company.name if hasattr(employee, "company") and employee.company else ""
    story.append(Paragraph(company_name or "Наименование организации", normal))
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
        ["Табельный номер:", str(employee.id)],
        ["Профессия (должность):", employee.position or ""],
        ["Структурное подразделение:", employee.department.name if employee.department else ""],
        ["За период работы:", f"с {hire} по ___.___.______"],
        ["Вид отпуска:", "Ежегодный основной оплачиваемый"],
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
        ["Руководитель организации:", "", "", ""],
        ["должность", "", "подпись", "расшифровка подписи"],
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
