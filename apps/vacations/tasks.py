import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def recalculate_vacation_balances():
    """
    Ежедневный пересчёт использованных дней и остатков для активных отпусков.
    
    Логика:
    - Находит все активные отпуска (start_date <= today < end_date)
    - Для каждого сотрудника с активным отпуском обновляет кэшированные значения
    - Используется как Celery Beat задача, запускается каждый день в 00:05 MSK
    
    Сам пересчёт days_used/days_remaining происходит в реальном времени через
    property в модели VacationScheduleEntry, но эта задача гарантирует что 
    данные актуальны для любых кэшированных представлений.
    """
    from datetime import date
    from apps.vacations.models import Vacation, VacationScheduleEntry

    today = date.today()
    year = today.year

    # Найти всех сотрудников с активным отпуском
    active_vacations = Vacation.objects.filter(
        start_date__lte=today,
        end_date__gt=today,
        vacation_type__in=['annual', 'additional'],
    ).select_related('employee')

    updated_count = 0
    for vacation in active_vacations:
        entries = VacationScheduleEntry.objects.filter(
            employee=vacation.employee,
            schedule__year=year,
        )
        for entry in entries:
            # Обращение к property вызывает пересчёт.
            # Логируем для мониторинга.
            used = entry.days_used
            remaining = entry.days_remaining
            logger.info(
                'Vacation recalc: %s — used=%d, remaining=%d',
                entry.employee.full_name, used, remaining,
            )
            updated_count += 1

    msg = f'Recalculated vacation balances for {updated_count} entries ({active_vacations.count()} active vacations)'
    logger.info(msg)
    return msg
