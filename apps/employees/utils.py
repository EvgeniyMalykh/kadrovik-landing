"""Утилиты расчёта рабочего времени по производственному календарю РФ."""
import calendar
from datetime import date


def get_norm_hours(year: int, month: int) -> tuple[int, int]:
    """
    Возвращает (норма_дней, норма_часов) для месяца
    по производственному календарю РФ.

    - Праздничные дни не считаются рабочими
    - Предпраздничные сокращённые дни = 7 часов (вместо 8)
    - Суббота/воскресенье не считаются рабочими
    """
    from apps.employees.models import ProductionCalendar

    holidays = set(
        ProductionCalendar.objects.filter(
            date__year=year, date__month=month, day_type='holiday'
        ).values_list('date', flat=True)
    )
    short_days = set(
        ProductionCalendar.objects.filter(
            date__year=year, date__month=month, day_type='short'
        ).values_list('date', flat=True)
    )

    work_days = 0
    total_hours = 0

    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        d = date(year, month, day)
        if d.weekday() >= 5:  # суббота/воскресенье
            continue
        if d in holidays:
            continue
        work_days += 1
        if d in short_days:
            total_hours += 7
        else:
            total_hours += 8

    return work_days, total_hours


def get_holidays_and_short_days(year: int, month: int = None) -> tuple[set, set]:
    """
    Возвращает (holidays, short_days) как множества дат.
    Если month указан — фильтрует по месяцу.
    """
    from apps.employees.models import ProductionCalendar

    qs = ProductionCalendar.objects.filter(date__year=year)
    if month:
        qs = qs.filter(date__month=month)

    holidays = set()
    short_days = set()
    for entry in qs.only('date', 'day_type'):
        if entry.day_type == 'holiday':
            holidays.add(entry.date)
        elif entry.day_type == 'short':
            short_days.add(entry.date)

    return holidays, short_days
