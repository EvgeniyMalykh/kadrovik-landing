"""
Генератор XML и PDF для отчёта ЕФС-1:
  - Подраздел 1.1 — Сведения о трудовой деятельности (приём, увольнение, перевод)
  - Подраздел 1.2 — Сведения о страховом стаже
"""
import io
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import date

from django.utils import timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT


EVENT_CODES = {
    'hire': 'ПРИЕМ',
    'dismiss': 'УВОЛЬНЕНИЕ',
    'transfer': 'ПЕРЕВОД',
}

EVENT_LABELS = {
    'hire': 'Приём',
    'dismiss': 'Увольнение',
    'transfer': 'Перевод',
}


# ──────────────────── helpers ────────────────────

def _register_fonts():
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


def _snils_formatted(snils_raw):
    digits = ''.join(filter(str.isdigit, snils_raw or ''))
    if len(digits) == 11:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]} {digits[9:11]}"
    return snils_raw or ''


def _format_date(d):
    if not d:
        return ''
    if isinstance(d, str):
        return d
    return d.strftime('%Y-%m-%d')


def _format_date_ru(d):
    if not d:
        return ''
    if isinstance(d, str):
        return d
    return d.strftime('%d.%m.%Y')


# ══════════════════════════════════════════════════
#  ПОДРАЗДЕЛ 1.1 — Сведения о трудовой деятельности
# ══════════════════════════════════════════════════

def generate_efs1_xml(company, employees_events, period_start=None, period_end=None):
    """Возвращает bytes XML для подраздела 1.1 (кадровые мероприятия)."""
    today = timezone.now().date()
    period_start = period_start or date(today.year, today.month, 1)
    period_end = period_end or today

    root = ET.Element('ЭДПФР')
    root.set('xmlns:xs', 'http://www.w3.org/2001/XMLSchema')
    root.set('ВерсФор686', '06.02')

    policyholder = ET.SubElement(root, 'СтрахователяСведения')
    ET.SubElement(policyholder, 'НаимОрганиз').text = company.name
    ET.SubElement(policyholder, 'ИННЮЛ').text = company.inn or ''
    ET.SubElement(policyholder, 'КПП').text = company.kpp or ''
    ET.SubElement(policyholder, 'РегНомерПФР').text = company.sfr_reg_number or ''
    ET.SubElement(policyholder, 'ОКВЭД').text = company.okved or ''
    ET.SubElement(policyholder, 'ДатаФормирования').text = _format_date(today)

    period = ET.SubElement(root, 'ОтчетныйПериод')
    ET.SubElement(period, 'НачалоПериода').text = _format_date(period_start)
    ET.SubElement(period, 'КонецПериода').text = _format_date(period_end)

    for ev in employees_events:
        emp = ev['employee']
        emp_block = ET.SubElement(root, 'СведенияОТрудДеятельности')

        person = ET.SubElement(emp_block, 'ЗастрахованноеЛицо')
        fio = ET.SubElement(person, 'ФИО')
        ET.SubElement(fio, 'Фамилия').text = emp.last_name or ''
        ET.SubElement(fio, 'Имя').text = emp.first_name or ''
        ET.SubElement(fio, 'Отчество').text = emp.middle_name or ''
        ET.SubElement(person, 'СНИЛС').text = _snils_formatted(emp.snils or '')
        ET.SubElement(person, 'ДатаРождения').text = _format_date(emp.birth_date)

        event = ET.SubElement(emp_block, 'КадровоеМероприятие')
        ET.SubElement(event, 'ВидМероприятия').text = EVENT_CODES.get(ev['event_type'], ev['event_type'])
        ET.SubElement(event, 'ДатаМероприятия').text = _format_date(ev.get('event_date'))
        ET.SubElement(event, 'Должность').text = ev.get('position') or ''

        if ev.get('order_number'):
            order = ET.SubElement(event, 'ОснованиеМероприятия')
            ET.SubElement(order, 'НомерДок').text = ev.get('order_number', '')
            ET.SubElement(order, 'ДатаДок').text = _format_date(ev.get('order_date'))

        if ev['event_type'] == 'dismiss' and ev.get('reason'):
            ET.SubElement(event, 'ОснованиеУвольнения').text = ev.get('reason', '')

    xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    pretty = minidom.parseString(xml_str).toprettyxml(indent='  ', encoding='utf-8')
    return pretty


def generate_efs1_11_pdf(company, employees_events, period_start=None, period_end=None):
    """Возвращает bytes PDF для подраздела 1.1 (кадровые мероприятия)."""
    today = timezone.now().date()
    period_start = period_start or date(today.year, today.month, 1)
    period_end = period_end or today

    font_name = _register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )

    title_style = ParagraphStyle(
        'Title', fontName=font_name, fontSize=12, leading=16, alignment=TA_CENTER, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER, spaceAfter=8,
    )
    normal = ParagraphStyle(
        'Normal', fontName=font_name, fontSize=8, leading=10,
    )
    cell_style = ParagraphStyle(
        'Cell', fontName=font_name, fontSize=7.5, leading=10,
    )

    elements = []

    elements.append(Paragraph('ЕФС-1 Подраздел 1.1', title_style))
    elements.append(Paragraph('Сведения о трудовой (иной) деятельности', subtitle_style))
    elements.append(Spacer(1, 4 * mm))

    # Реквизиты страхователя
    info_lines = [
        'Страхователь: ' + (company.name or ''),
        'ИНН: ' + (company.inn or '') + '    КПП: ' + (company.kpp or ''),
        'Рег. номер СФР: ' + (company.sfr_reg_number or ''),
        'Период: ' + _format_date_ru(period_start) + ' \u2014 ' + _format_date_ru(period_end),
        'Дата формирования: ' + _format_date_ru(today),
    ]
    for line in info_lines:
        elements.append(Paragraph(line, normal))
    elements.append(Spacer(1, 6 * mm))

    # Таблица мероприятий
    header = [
        Paragraph('<b>№</b>', cell_style),
        Paragraph('<b>Фамилия</b>', cell_style),
        Paragraph('<b>Имя</b>', cell_style),
        Paragraph('<b>Отчество</b>', cell_style),
        Paragraph('<b>СНИЛС</b>', cell_style),
        Paragraph('<b>Мероприятие</b>', cell_style),
        Paragraph('<b>Дата</b>', cell_style),
        Paragraph('<b>Должность</b>', cell_style),
    ]
    data = [header]

    for idx, ev in enumerate(employees_events, 1):
        emp = ev['employee']
        data.append([
            Paragraph(str(idx), cell_style),
            Paragraph(emp.last_name or '', cell_style),
            Paragraph(emp.first_name or '', cell_style),
            Paragraph(emp.middle_name or '', cell_style),
            Paragraph(_snils_formatted(emp.snils or ''), cell_style),
            Paragraph(EVENT_LABELS.get(ev['event_type'], ev['event_type']), cell_style),
            Paragraph(_format_date_ru(ev.get('event_date')), cell_style),
            Paragraph(ev.get('position') or '', cell_style),
        ])

    col_widths = [8 * mm, 30 * mm, 25 * mm, 28 * mm, 28 * mm, 22 * mm, 20 * mm, 30 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8 * mm))

    total_text = 'Всего мероприятий: ' + str(len(employees_events))
    elements.append(Paragraph(total_text, normal))

    doc.build(elements)
    return buf.getvalue()


# ══════════════════════════════════════════════════
#  ПОДРАЗДЕЛ 1.2 — Сведения о страховом стаже
# ══════════════════════════════════════════════════

def _build_stazh_records(company, year):
    """Собирает данные о стаже сотрудников за год."""
    from apps.employees.models import Employee

    employees = Employee.objects.filter(company=company).exclude(
        status='fired', fire_date__lt=date(year, 1, 1)
    ).order_by('last_name', 'first_name')

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    records = []
    for emp in employees:
        period_start = emp.hire_date if emp.hire_date and emp.hire_date > year_start else year_start
        if emp.fire_date and emp.fire_date <= year_end:
            period_end = emp.fire_date
        else:
            period_end = year_end

        if period_start > year_end:
            continue

        records.append({
            'employee': emp,
            'period_start': period_start,
            'period_end': period_end,
        })
    return records


def generate_efs1_12_xml(company, year):
    """Возвращает bytes XML для подраздела 1.2 (сведения о страховом стаже)."""
    today = timezone.now().date()
    records = _build_stazh_records(company, year)

    root = ET.Element('ЭДПФР')
    root.set('xmlns:xs', 'http://www.w3.org/2001/XMLSchema')
    root.set('ВерсФор686', '06.02')

    policyholder = ET.SubElement(root, 'СтрахователяСведения')
    ET.SubElement(policyholder, 'НаимОрганиз').text = company.name
    ET.SubElement(policyholder, 'ИННЮЛ').text = company.inn or ''
    ET.SubElement(policyholder, 'КПП').text = company.kpp or ''
    ET.SubElement(policyholder, 'РегНомерПФР').text = company.sfr_reg_number or ''
    ET.SubElement(policyholder, 'ОКВЭД').text = company.okved or ''
    ET.SubElement(policyholder, 'ДатаФормирования').text = _format_date(today)

    period = ET.SubElement(root, 'ОтчетныйПериод')
    ET.SubElement(period, 'Год').text = str(year)

    for rec in records:
        emp = rec['employee']
        emp_block = ET.SubElement(root, 'СведенияОСтаже')

        person = ET.SubElement(emp_block, 'ЗастрахованноеЛицо')
        fio = ET.SubElement(person, 'ФИО')
        ET.SubElement(fio, 'Фамилия').text = emp.last_name or ''
        ET.SubElement(fio, 'Имя').text = emp.first_name or ''
        ET.SubElement(fio, 'Отчество').text = emp.middle_name or ''
        ET.SubElement(person, 'СНИЛС').text = _snils_formatted(emp.snils or '')
        ET.SubElement(person, 'ДатаРождения').text = _format_date(emp.birth_date)

        periods = ET.SubElement(emp_block, 'Периоды')
        p = ET.SubElement(periods, 'Период')
        ET.SubElement(p, 'ДатаНач').text = _format_date(rec['period_start'])
        ET.SubElement(p, 'ДатаКон').text = _format_date(rec['period_end'])
        ET.SubElement(p, 'КодУсловийТруда').text = 'ОБЫЧНЫЕ'

    xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    pretty = minidom.parseString(xml_str).toprettyxml(indent='  ', encoding='utf-8')
    return pretty


def generate_efs1_12_pdf(company, year):
    """Возвращает bytes PDF для подраздела 1.2 (сведения о страховом стаже)."""
    today = timezone.now().date()
    records = _build_stazh_records(company, year)

    font_name = _register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )

    title_style = ParagraphStyle(
        'Title', fontName=font_name, fontSize=12, leading=16, alignment=TA_CENTER, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER, spaceAfter=8,
    )
    normal = ParagraphStyle(
        'Normal', fontName=font_name, fontSize=8, leading=10,
    )
    cell_style = ParagraphStyle(
        'Cell', fontName=font_name, fontSize=7.5, leading=10,
    )

    elements = []

    elements.append(Paragraph('ЕФС-1 Подраздел 1.2', title_style))
    elements.append(Paragraph('Сведения о страховом стаже', subtitle_style))
    elements.append(Spacer(1, 4 * mm))

    info_lines = [
        'Страхователь: ' + (company.name or ''),
        'ИНН: ' + (company.inn or '') + '    КПП: ' + (company.kpp or ''),
        'Рег. номер СФР: ' + (company.sfr_reg_number or ''),
        'Отчётный год: ' + str(year),
        'Дата формирования: ' + _format_date_ru(today),
    ]
    for line in info_lines:
        elements.append(Paragraph(line, normal))
    elements.append(Spacer(1, 6 * mm))

    header = [
        Paragraph('<b>№</b>', cell_style),
        Paragraph('<b>Фамилия</b>', cell_style),
        Paragraph('<b>Имя</b>', cell_style),
        Paragraph('<b>Отчество</b>', cell_style),
        Paragraph('<b>СНИЛС</b>', cell_style),
        Paragraph('<b>Начало периода</b>', cell_style),
        Paragraph('<b>Конец периода</b>', cell_style),
        Paragraph('<b>Условия труда</b>', cell_style),
    ]
    data = [header]

    for idx, rec in enumerate(records, 1):
        emp = rec['employee']
        data.append([
            Paragraph(str(idx), cell_style),
            Paragraph(emp.last_name or '', cell_style),
            Paragraph(emp.first_name or '', cell_style),
            Paragraph(emp.middle_name or '', cell_style),
            Paragraph(_snils_formatted(emp.snils or ''), cell_style),
            Paragraph(_format_date_ru(rec['period_start']), cell_style),
            Paragraph(_format_date_ru(rec['period_end']), cell_style),
            Paragraph('Обычные', cell_style),
        ])

    col_widths = [8 * mm, 30 * mm, 25 * mm, 28 * mm, 28 * mm, 22 * mm, 22 * mm, 28 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8 * mm))

    total_text = 'Всего застрахованных лиц: ' + str(len(records))
    elements.append(Paragraph(total_text, normal))

    doc.build(elements)
    return buf.getvalue()
