"""Рендеринг кастомных .docx шаблонов через docxtpl."""
from docxtpl import DocxTemplate
from io import BytesIO
from django.utils import timezone


def get_employee_context(employee):
    """Контекст для подстановки данных сотрудника."""
    return {
        'employee_last_name': employee.last_name or '',
        'employee_first_name': employee.first_name or '',
        'employee_middle_name': employee.middle_name or '',
        'employee_full_name': employee.full_name,
        'employee_short_name': employee.short_name,
        'employee_position': employee.position or '',
        'employee_department': str(employee.department) if employee.department else '',
        'employee_department_name': employee.department.name if employee.department else '',
        'employee_personnel_number': employee.personnel_number or '',
        'employee_hire_date': employee.hire_date.strftime('%d.%m.%Y') if employee.hire_date else '',
        'employee_fire_date': employee.fire_date.strftime('%d.%m.%Y') if employee.fire_date else '',
        'employee_salary': str(employee.salary or ''),
        'employee_phone': employee.phone or '',
        'employee_email': employee.email or '',
        'employee_inn': employee.inn or '',
        'employee_snils': employee.snils or '',
        'employee_passport_series': employee.passport_series or '',
        'employee_passport_number': employee.passport_number or '',
        'employee_passport_issued_by': employee.passport_issued_by or '',
        'employee_passport_issued_date': employee.passport_issued_date.strftime('%d.%m.%Y') if employee.passport_issued_date else '',
        'employee_passport_registration': employee.passport_registration or '',
        'employee_birth_date': employee.birth_date.strftime('%d.%m.%Y') if employee.birth_date else '',
        'employee_birth_place': employee.birth_place or '',
        'employee_education': employee.get_education_display() if employee.education else '',
        'employee_marital_status': employee.get_marital_status_display() if employee.marital_status else '',
        'employee_citizenship': employee.citizenship or '',
        'employee_contract_type': employee.get_contract_type_display() if employee.contract_type else '',
        'employee_contract_end_date': employee.contract_end_date.strftime('%d.%m.%Y') if employee.contract_end_date else '',
        'employee_probation_end_date': employee.probation_end_date.strftime('%d.%m.%Y') if employee.probation_end_date else '',
        'employee_status': employee.get_status_display() if employee.status else '',
    }


def get_company_context(company):
    """Контекст для подстановки данных компании."""
    return {
        'company_name': company.name or '',
        'company_inn': company.inn or '',
        'company_ogrn': company.ogrn or '',
        'company_kpp': company.kpp or '',
        'company_okpo': company.okpo or '',
        'company_legal_address': company.legal_address or '',
        'company_actual_address': company.actual_address or '',
        'company_director_name': company.director_name or '',
        'company_director_position': company.director_position or 'Директор',
        'company_phone': company.phone or '',
        'company_email': company.email or '',
    }


def render_template_to_bytes(template_file_path, extra_context=None):
    """
    Рендерит .docx шаблон и возвращает байты файла.

    Переменные в шаблоне: {{ employee_full_name }}, {{ company_name }}, {{ today }} и т.д.
    """
    tpl = DocxTemplate(template_file_path)
    context = {
        'today': timezone.now().strftime('%d.%m.%Y'),
        'today_year': timezone.now().strftime('%Y'),
        'today_month': timezone.now().strftime('%m'),
        'today_day': timezone.now().strftime('%d'),
    }
    if extra_context:
        context.update(extra_context)
    tpl.render(context)
    buffer = BytesIO()
    tpl.save(buffer)
    buffer.seek(0)
    return buffer.read()
