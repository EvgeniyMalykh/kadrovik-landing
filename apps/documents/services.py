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
        ['Табельный номер:', str(employee.id)],
        ['Структурное подразделение:', employee.department.name if hasattr(employee, 'department') and employee.department else ''],
        ['Профессия (должность):', employee.position or ''],
        ['Тарифная ставка (оклад):', '{} руб.'.format(employee.salary) if employee.salary else ''],
        ['Испытательный срок:', '{} мес.'.format(employee.probation_months) if hasattr(employee, 'probation_months') and employee.probation_months else 'Без испытания'],
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
        ['работник ознакомлен:', '', '____________', hire_date],
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
