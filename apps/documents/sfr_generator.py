"""
Генератор XML для отчёта ЕФС-1 подраздел 1.1 (бывший СЗВ-ТД).
Кадровые мероприятия: приём, увольнение, перевод.
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import date
from django.utils import timezone


EVENT_CODES = {
    'hire': 'ПРИЕМ',
    'dismiss': 'УВОЛЬНЕНИЕ',
    'transfer': 'ПЕРЕВОД',
}


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


def generate_efs1_xml(company, employees_events, period_start=None, period_end=None):
    today = timezone.now().date()
    period_start = period_start or date(today.year, today.month, 1)
    period_end = period_end or today

    root = ET.Element('ЭДПФР')
    root.set('xmlns:xs', 'http://www.w3.org/2001/XMLSchema')
    root.set('ВерсФор686', '06.02')

    # Страхователь
    policyholder = ET.SubElement(root, 'СтрахователяСведения')
    ET.SubElement(policyholder, 'НаимОрганиз').text = company.name
    ET.SubElement(policyholder, 'ИННЮЛ').text = company.inn or ''
    ET.SubElement(policyholder, 'КПП').text = company.kpp or ''
    ET.SubElement(policyholder, 'РегНомерПФР').text = company.sfr_reg_number or ''
    ET.SubElement(policyholder, 'ОКВЭД').text = company.okved or ''
    ET.SubElement(policyholder, 'ДатаФормирования').text = _format_date(today)

    # Отчётный период
    period = ET.SubElement(root, 'ОтчетныйПериод')
    ET.SubElement(period, 'НачалоПериода').text = _format_date(period_start)
    ET.SubElement(period, 'КонецПериода').text = _format_date(period_end)

    # Сведения по каждому мероприятию
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
