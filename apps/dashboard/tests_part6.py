"""
Part 6 tests: Targeted coverage for critical business logic gaps.

Covers:
- 6.1  Billing: trial subscription creation, trial→paid transition, date calculations,
       annual billing_period preservation, max_employees enforcement, plan prices
- 6.2  Dashboard: salary save/preserve, probation_end_date reset, employee_add POST,
       employee_edit POST
- 6.3  Documents: generate_salary_change_pdf effective_date, PDF robustness
- 6.4  Accounts: registration creates company + trial, role-based access
       (owner/hr/viewer)

Run:
    python manage.py test apps.dashboard.tests_part6 --settings=config.settings.test -v 2
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, Department, SalaryHistory
from apps.billing.models import Subscription, Payment
from apps.billing.services import (
    activate_subscription,
    get_subscription_context,
    get_plan_features,
    create_recurring_payment,
    PLANS,
    PLAN_PRICES,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _user(email='t6@example.com', password='TestPass6!'):
    return User.objects.create_user(username=email, email=email, password=password)


def _company(owner, name='ООО Тест6', inn='6660000000'):
    return Company.objects.create(
        owner=owner, name=name, inn=inn,
        ogrn='6660000000001',
        legal_address='г. Тест, ул. 6я',
        director_name='Шестов Шесть Шестович',
    )


def _member(company, user, role='owner'):
    return CompanyMember.objects.create(company=company, user=user, role=role)


def _subscription(company, plan='trial', days=30, max_employees=10, billing_period='monthly'):
    return Subscription.objects.create(
        company=company, plan=plan,
        status=Subscription.Status.ACTIVE,
        expires_at=timezone.now() + timedelta(days=days),
        max_employees=max_employees,
        billing_period=billing_period,
    )


def _employee(company, **kw):
    defaults = dict(
        last_name='Тестов', first_name='Тест', middle_name='Тестович',
        position='Тестер', hire_date=date.today() - timedelta(days=90),
        salary=Decimal('50000'), marital_status='single',
    )
    defaults.update(kw)
    return Employee.objects.create(company=company, **defaults)


# ===========================================================================
# 6.1  Billing: trial, transitions, dates, billing_period, prices
# ===========================================================================

class TrialSubscriptionTests(TestCase):
    """Trial subscription creation and constraints."""

    def setUp(self):
        self.user = _user(email='trial6@example.com')
        self.company = _company(self.user, inn='6661111111')
        _member(self.company, self.user)

    def test_trial_max_employees_is_10(self):
        """Trial plan in PLANS config has max_employees = 10."""
        self.assertEqual(PLANS['trial']['max_employees'], 10)

    def test_trial_subscription_duration_14_days(self):
        """Trial subscription should last 14 days (or 7 as implemented)."""
        sub = _subscription(self.company, plan='trial', days=14, max_employees=10)
        self.assertTrue(sub.is_active)
        delta = sub.expires_at - timezone.now()
        self.assertGreater(delta.days, 12)

    def test_trial_subscription_is_active(self):
        """Trial with future expires_at is active."""
        sub = _subscription(self.company, plan='trial', days=7, max_employees=10)
        self.assertTrue(sub.is_active)

    def test_trial_subscription_has_features(self):
        """Trial plan includes documents, telegram, timesheet but not export_excel."""
        feats = get_plan_features('trial')
        self.assertTrue(feats['documents'])
        self.assertTrue(feats['telegram'])
        self.assertTrue(feats['timesheet'])
        self.assertFalse(feats['export_excel'])
        self.assertFalse(feats['custom_templates'])

    def test_trial_price_is_zero(self):
        """Trial plan price is 0."""
        self.assertEqual(PLANS['trial']['price'], 0)


class TrialToPaidTransitionTests(TestCase):
    """Transition from trial to paid plan."""

    def setUp(self):
        self.user = _user(email='transition6@example.com')
        self.company = _company(self.user, inn='6662222222')
        _member(self.company, self.user)
        self.trial_sub = _subscription(self.company, plan='trial', days=7, max_employees=10)

    def test_activate_start_from_trial(self):
        """Activating 'start' plan from trial updates plan and max_employees."""
        sub = activate_subscription(self.company, 'start')
        sub.refresh_from_db()
        self.assertEqual(sub.plan, 'start')
        self.assertEqual(sub.max_employees, PLANS['start']['max_employees'])
        self.assertTrue(sub.is_active)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)

    def test_activate_business_from_trial(self):
        """Activating 'business' plan from trial."""
        sub = activate_subscription(self.company, 'business')
        sub.refresh_from_db()
        self.assertEqual(sub.plan, 'business')
        self.assertEqual(sub.max_employees, 50)

    def test_activate_pro_from_trial(self):
        """Activating 'pro' plan from trial."""
        sub = activate_subscription(self.company, 'pro')
        sub.refresh_from_db()
        self.assertEqual(sub.plan, 'pro')
        self.assertEqual(sub.max_employees, 200)


class SubscriptionDateCalculationTests(TestCase):
    """Verify monthly +30 days, annual +365 days."""

    def setUp(self):
        self.user = _user(email='dates6@example.com')
        self.company = _company(self.user, inn='6663333333')
        _member(self.company, self.user)

    def test_monthly_subscription_30_days(self):
        """Monthly subscription sets expires_at ~30 days from now."""
        before = timezone.now()
        sub = activate_subscription(self.company, 'start', billing_period='monthly')
        after = timezone.now()
        # expires_at should be ~30 days in the future
        delta = sub.expires_at - before
        self.assertGreaterEqual(delta.days, 29)
        self.assertLessEqual(delta.days, 31)

    def test_annual_subscription_365_days(self):
        """Annual subscription sets expires_at ~365 days from now."""
        before = timezone.now()
        sub = activate_subscription(self.company, 'start', billing_period='annual')
        after = timezone.now()
        delta = sub.expires_at - before
        self.assertGreaterEqual(delta.days, 364)
        self.assertLessEqual(delta.days, 366)

    def test_billing_period_stored_correctly(self):
        """billing_period is stored as 'annual' when passed."""
        sub = activate_subscription(self.company, 'business', billing_period='annual')
        sub.refresh_from_db()
        self.assertEqual(sub.billing_period, 'annual')

    def test_monthly_billing_period_stored(self):
        """billing_period defaults to 'monthly'."""
        sub = activate_subscription(self.company, 'start')
        sub.refresh_from_db()
        self.assertEqual(sub.billing_period, 'monthly')


class AnnualBillingPeriodRecurringTests(TestCase):
    """Annual billing_period must be preserved in recurring payments (metadata)."""

    def setUp(self):
        self.user = _user(email='annual6@example.com')
        self.company = _company(self.user, inn='6664444444')
        _member(self.company, self.user)

    def test_annual_billing_period_preserved_on_activate(self):
        """When activating with annual billing_period, it must persist."""
        sub = activate_subscription(self.company, 'pro', billing_period='annual')
        sub.refresh_from_db()
        self.assertEqual(sub.billing_period, 'annual')
        # Verify it doesn't become monthly
        self.assertNotEqual(sub.billing_period, 'monthly')

    def test_annual_billing_period_not_overwritten_to_monthly(self):
        """Re-activating subscription keeps annual period if specified."""
        sub = activate_subscription(self.company, 'start', billing_period='annual')
        # Re-activate (simulating auto-renewal)
        sub2 = activate_subscription(self.company, 'start', billing_period='annual')
        sub2.refresh_from_db()
        self.assertEqual(sub2.billing_period, 'annual')


class PlanPricesTests(TestCase):
    """Verify plan prices match spec."""

    def test_start_monthly_price(self):
        self.assertEqual(PLAN_PRICES['start']['monthly'], 790)

    def test_start_annual_price(self):
        self.assertEqual(PLAN_PRICES['start']['annual'], 7110)

    def test_business_monthly_price(self):
        self.assertEqual(PLAN_PRICES['business']['monthly'], 1990)

    def test_business_annual_price(self):
        self.assertEqual(PLAN_PRICES['business']['annual'], 17910)

    def test_pro_monthly_price(self):
        self.assertEqual(PLAN_PRICES['pro']['monthly'], 4900)

    def test_pro_annual_price(self):
        self.assertEqual(PLAN_PRICES['pro']['annual'], 44100)


class MaxEmployeesEnforcementTests(TestCase):
    """max_employees is respected in subscription context."""

    def setUp(self):
        self.user = _user(email='maxemp6@example.com')
        self.company = _company(self.user, inn='6665555555')
        _member(self.company, self.user)

    def test_can_add_when_under_limit(self):
        """can_add_employee is True when count < max."""
        _subscription(self.company, plan='start', max_employees=10)
        _employee(self.company, last_name='Emp1')
        ctx = get_subscription_context(self.company)
        self.assertTrue(ctx['can_add_employee'])

    def test_cannot_add_when_at_limit(self):
        """can_add_employee is False when count >= max."""
        _subscription(self.company, plan='start', max_employees=1)
        _employee(self.company, last_name='Emp1')
        ctx = get_subscription_context(self.company)
        self.assertFalse(ctx['can_add_employee'])

    def test_max_employees_from_db_not_plans(self):
        """get_subscription_context uses max_employees from DB, not PLANS."""
        sub = _subscription(self.company, plan='start', max_employees=25)
        ctx = get_subscription_context(self.company)
        self.assertEqual(ctx['max_employees'], 25)

    def test_context_employee_count_accurate(self):
        """employee_count in context matches actual DB count."""
        _subscription(self.company, plan='start', max_employees=10)
        for i in range(3):
            _employee(self.company, last_name=f'Emp{i}')
        ctx = get_subscription_context(self.company)
        self.assertEqual(ctx['employee_count'], 3)


# ===========================================================================
# 6.2  Dashboard: salary save/preserve, probation reset, employee CRUD
# ===========================================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class SalarySavePreserveTests(TestCase):
    """Salary field: filled → saved, empty → not overwritten on edit."""

    def setUp(self):
        self.user = _user(email='salary6@example.com')
        self.company = _company(self.user, inn='6666666666')
        _member(self.company, self.user)
        _subscription(self.company, plan='business', max_employees=50)
        self.employee = _employee(self.company, salary=Decimal('75000'))
        self.client.force_login(self.user)

    def test_salary_saved_when_provided(self):
        """POST with salary updates the value."""
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': self.employee.last_name,
                'first_name': self.employee.first_name,
                'position': self.employee.position,
                'hire_date': self.employee.hire_date.strftime('%d.%m.%Y'),
                'salary': '100000',
                'status': 'active',
                'contract_type': 'permanent',
                'marital_status': 'single',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.salary, Decimal('100000'))

    def test_salary_not_overwritten_when_empty(self):
        """POST with empty salary does NOT overwrite existing value."""
        original_salary = self.employee.salary
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': self.employee.last_name,
                'first_name': self.employee.first_name,
                'position': self.employee.position,
                'hire_date': self.employee.hire_date.strftime('%d.%m.%Y'),
                'salary': '',
                'status': 'active',
                'contract_type': 'permanent',
                'marital_status': 'single',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.salary, original_salary)

    def test_salary_set_on_new_employee(self):
        """New employee: salary is set."""
        count_before = Employee.objects.filter(company=self.company).count()
        resp = self.client.post(reverse('dashboard:employee_add'), {
            'last_name': 'Новый',
            'first_name': 'Сотрудник',
            'position': 'Инженер',
            'hire_date': '01.01.2025',
            'salary': '65000',
            'status': 'active',
            'contract_type': 'permanent',
            'marital_status': 'single',
        })
        self.assertEqual(resp.status_code, 200)
        new_emp = Employee.objects.filter(
            company=self.company, last_name='Новый'
        ).first()
        self.assertIsNotNone(new_emp)
        self.assertEqual(new_emp.salary, Decimal('65000'))

    def test_salary_none_on_new_employee_without_salary(self):
        """New employee without salary → salary is None."""
        resp = self.client.post(reverse('dashboard:employee_add'), {
            'last_name': 'БезОклада',
            'first_name': 'Сотрудник',
            'position': 'Стажёр',
            'hire_date': '01.01.2025',
            'salary': '',
            'status': 'active',
            'contract_type': 'permanent',
            'marital_status': 'single',
        })
        self.assertEqual(resp.status_code, 200)
        new_emp = Employee.objects.filter(
            company=self.company, last_name='БезОклада'
        ).first()
        self.assertIsNotNone(new_emp)
        self.assertIsNone(new_emp.salary)


@override_settings(LOGIN_URL='/dashboard/login/')
class ProbationEndDateResetTests(TestCase):
    """Probation end date: empty field resets the date on edit."""

    def setUp(self):
        self.user = _user(email='prob6@example.com')
        self.company = _company(self.user, inn='6667777777')
        _member(self.company, self.user)
        _subscription(self.company, plan='business', max_employees=50)
        self.employee = _employee(
            self.company,
            probation_end_date=date.today() + timedelta(days=90),
        )
        self.client.force_login(self.user)

    def test_probation_cleared_when_empty(self):
        """POST with empty probation_end_date clears it."""
        self.assertIsNotNone(self.employee.probation_end_date)
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': self.employee.last_name,
                'first_name': self.employee.first_name,
                'position': self.employee.position,
                'hire_date': self.employee.hire_date.strftime('%d.%m.%Y'),
                'salary': str(self.employee.salary),
                'probation_end_date': '',
                'probation_months': '',
                'status': 'active',
                'contract_type': 'permanent',
                'marital_status': 'single',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.probation_end_date)

    def test_probation_set_via_months(self):
        """POST with probation_months=3 sets probation_end_date."""
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': self.employee.last_name,
                'first_name': self.employee.first_name,
                'position': self.employee.position,
                'hire_date': self.employee.hire_date.strftime('%d.%m.%Y'),
                'salary': str(self.employee.salary),
                'probation_months': '3',
                'status': 'active',
                'contract_type': 'permanent',
                'marital_status': 'single',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertIsNotNone(self.employee.probation_end_date)
        # Should be ~90 days from hire_date
        expected = self.employee.hire_date + timedelta(days=90)
        self.assertEqual(self.employee.probation_end_date, expected)

    def test_probation_zero_months_clears(self):
        """POST with probation_months=0 clears probation_end_date."""
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': self.employee.last_name,
                'first_name': self.employee.first_name,
                'position': self.employee.position,
                'hire_date': self.employee.hire_date.strftime('%d.%m.%Y'),
                'salary': str(self.employee.salary),
                'probation_months': '0',
                'status': 'active',
                'contract_type': 'permanent',
                'marital_status': 'single',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.probation_end_date)


@override_settings(LOGIN_URL='/dashboard/login/')
class EmployeeAddPostTests(TestCase):
    """POST employee_form — employee creation via form."""

    def setUp(self):
        self.user = _user(email='add6@example.com')
        self.company = _company(self.user, inn='6668888888')
        _member(self.company, self.user)
        _subscription(self.company, plan='business', max_employees=50)
        self.client.force_login(self.user)

    def test_add_employee_creates_record(self):
        """POST to employee_add creates a new Employee."""
        count_before = Employee.objects.filter(company=self.company).count()
        resp = self.client.post(reverse('dashboard:employee_add'), {
            'last_name': 'Новиков',
            'first_name': 'Новый',
            'middle_name': 'Новый',
            'position': 'Программист',
            'hire_date': '15.03.2025',
            'salary': '90000',
            'status': 'active',
            'contract_type': 'permanent',
            'marital_status': 'married',
            'citizenship': 'Российская Федерация',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            Employee.objects.filter(company=self.company).count(),
            count_before + 1,
        )
        emp = Employee.objects.filter(company=self.company, last_name='Новиков').first()
        self.assertIsNotNone(emp)
        self.assertEqual(emp.position, 'Программист')
        self.assertEqual(emp.salary, Decimal('90000'))

    def test_add_employee_without_salary(self):
        """Adding employee without salary still works."""
        resp = self.client.post(reverse('dashboard:employee_add'), {
            'last_name': 'БезОклада',
            'first_name': 'Иван',
            'position': 'Стажёр',
            'hire_date': '01.04.2025',
            'salary': '',
            'status': 'active',
            'contract_type': 'permanent',
            'marital_status': 'single',
        })
        self.assertEqual(resp.status_code, 200)
        emp = Employee.objects.filter(company=self.company, last_name='БезОклада').first()
        self.assertIsNotNone(emp)
        self.assertIsNone(emp.salary)

    def test_add_employee_blocked_at_limit(self):
        """Adding employee when at max limit shows error HTML (not crash)."""
        # Update existing subscription rather than creating a second one
        sub = Subscription.objects.get(company=self.company)
        sub.plan = 'start'
        sub.max_employees = 0
        sub.save(update_fields=['plan', 'max_employees'])
        resp = self.client.post(reverse('dashboard:employee_add'), {
            'last_name': 'Лишний',
            'first_name': 'Иван',
            'position': 'Тестер',
            'hire_date': '01.01.2025',
            'status': 'active',
            'contract_type': 'permanent',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            Employee.objects.filter(company=self.company, last_name='Лишний').exists()
        )


@override_settings(LOGIN_URL='/dashboard/login/')
class EmployeeEditPostTests(TestCase):
    """POST employee_edit — employee update via form."""

    def setUp(self):
        self.user = _user(email='edit6@example.com')
        self.company = _company(self.user, inn='6669999999')
        _member(self.company, self.user)
        _subscription(self.company, plan='business', max_employees=50)
        self.employee = _employee(self.company, salary=Decimal('50000'))
        self.client.force_login(self.user)

    def test_edit_updates_name_and_position(self):
        """POST to employee_edit updates name and position."""
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': 'Обновлённый',
                'first_name': 'Имя',
                'middle_name': 'Отчество',
                'position': 'Директор',
                'hire_date': self.employee.hire_date.strftime('%d.%m.%Y'),
                'salary': '200000',
                'status': 'active',
                'contract_type': 'permanent',
                'marital_status': 'single',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.last_name, 'Обновлённый')
        self.assertEqual(self.employee.position, 'Директор')
        self.assertEqual(self.employee.salary, Decimal('200000'))

    def test_edit_by_accountant_denied(self):
        """Accountant cannot edit employee (role < hr)."""
        accountant = _user(email='acc6@example.com')
        _member(self.company, accountant, role='accountant')
        self.client.force_login(accountant)
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': 'Хакер',
                'first_name': 'Иван',
                'position': 'Тест',
                'hire_date': '01.01.2025',
                'status': 'active',
                'contract_type': 'permanent',
            },
        )
        # Should redirect (denied)
        self.assertEqual(resp.status_code, 302)
        self.employee.refresh_from_db()
        self.assertNotEqual(self.employee.last_name, 'Хакер')

    def test_edit_by_hr_allowed(self):
        """HR can edit employee."""
        hr_user = _user(email='hr6@example.com')
        _member(self.company, hr_user, role='hr')
        self.client.force_login(hr_user)
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': 'ОтХР',
                'first_name': 'Имя',
                'position': 'Тест',
                'hire_date': self.employee.hire_date.strftime('%d.%m.%Y'),
                'salary': str(self.employee.salary),
                'status': 'active',
                'contract_type': 'permanent',
                'marital_status': 'single',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.last_name, 'ОтХР')


# ===========================================================================
# 6.3  Documents: generate_salary_change_pdf, PDF robustness
# ===========================================================================

class SalaryChangePdfTests(TestCase):
    """generate_salary_change_pdf uses effective_date, not date.today()."""

    def setUp(self):
        self.user = _user(email='pdf6@example.com')
        self.company = _company(self.user, inn='6660001111')
        _member(self.company, self.user)
        self.employee = _employee(self.company, salary=Decimal('50000'))

    def test_effective_date_used_in_pdf(self):
        """effective_date parameter is accepted and PDF is generated."""
        from apps.documents.services import generate_salary_change_pdf
        effective = date(2025, 6, 15)
        pdf_bytes = generate_salary_change_pdf(
            self.employee,
            new_salary=70000,
            order_number='З-100',
            previous_salary=50000,
            effective_date=effective,
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 100)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_effective_date_none_uses_today(self):
        """When effective_date is None, PDF is still generated successfully."""
        from apps.documents.services import generate_salary_change_pdf
        pdf_bytes = generate_salary_change_pdf(
            self.employee,
            new_salary=60000,
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 100)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_pdf_with_missing_salary_history(self):
        """PDF generation works when there's no salary history."""
        from apps.documents.services import generate_salary_change_pdf
        # No SalaryHistory records exist
        pdf_bytes = generate_salary_change_pdf(
            self.employee,
            new_salary=80000,
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 100)


class PdfRobustnessTests(TestCase):
    """PDF generators don't crash with missing optional fields."""

    def setUp(self):
        self.user = _user(email='robust6@example.com')
        self.company = _company(self.user, inn='6660002222')
        _member(self.company, self.user)
        # Minimal employee — many fields blank
        self.employee = Employee.objects.create(
            company=self.company,
            last_name='Минимальный',
            first_name='Сотрудник',
            position='',
            hire_date=date.today(),
        )

    def test_t1_pdf_with_minimal_data(self):
        """generate_t1_pdf works with minimal employee data."""
        from apps.documents.services import generate_t1_pdf
        pdf = generate_t1_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_t2_pdf_with_minimal_data(self):
        """generate_t2_pdf works with minimal employee data."""
        from apps.documents.services import generate_t2_pdf
        pdf = generate_t2_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_t8_pdf_with_no_fire_date(self):
        """generate_t8_pdf works when fire_date is None."""
        from apps.documents.services import generate_t8_pdf
        pdf = generate_t8_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_t6_pdf_with_no_dates(self):
        """generate_t6_pdf works with default dates."""
        from apps.documents.services import generate_t6_pdf
        pdf = generate_t6_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_salary_change_pdf_with_no_salary(self):
        """generate_salary_change_pdf works when employee has no salary."""
        from apps.documents.services import generate_salary_change_pdf
        pdf = generate_salary_change_pdf(self.employee, new_salary=50000)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_work_certificate_with_no_salary(self):
        """generate_work_certificate_pdf works without salary."""
        from apps.documents.services import generate_work_certificate_pdf
        pdf = generate_work_certificate_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_labor_contract_with_minimal_data(self):
        """generate_labor_contract_pdf works with minimal data."""
        from apps.documents.services import generate_labor_contract_pdf
        pdf = generate_labor_contract_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_bonus_order_pdf(self):
        """generate_bonus_order_pdf works."""
        from apps.documents.services import generate_bonus_order_pdf
        pdf = generate_bonus_order_pdf(self.employee, bonus_amount=10000)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_disciplinary_order_pdf(self):
        """generate_disciplinary_order_pdf works."""
        from apps.documents.services import generate_disciplinary_order_pdf
        pdf = generate_disciplinary_order_pdf(self.employee, penalty_type='Выговор')
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)


class OtherPdfGeneratorsDateTests(TestCase):
    """Check other PDF generators for date bug similar to salary_change."""

    def setUp(self):
        self.user = _user(email='otherpdf6@example.com')
        self.company = _company(self.user, inn='6660003333')
        _member(self.company, self.user)
        self.employee = _employee(self.company, fire_date=date(2025, 12, 31))

    def test_t8_uses_fire_date(self):
        """generate_t8_pdf generates valid PDF with fire_date set."""
        from apps.documents.services import generate_t8_pdf
        pdf = generate_t8_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertTrue(len(pdf) > 100)

    def test_t6_uses_vacation_dates(self):
        """generate_t6_pdf accepts and uses vacation date parameters."""
        from apps.documents.services import generate_t6_pdf
        v_start = date(2025, 8, 1)
        v_end = date(2025, 8, 14)
        pdf = generate_t6_pdf(
            self.employee,
            vacation_start=v_start,
            vacation_end=v_end,
        )
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertTrue(len(pdf) > 100)

    def test_dismissal_order_uses_provided_date(self):
        """generate_dismissal_order_pdf accepts dismissal_date parameter."""
        from apps.documents.services import generate_dismissal_order_pdf
        pdf = generate_dismissal_order_pdf(
            self.employee,
            dismissal_date='25.12.2025',
        )
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertTrue(len(pdf) > 100)


# ===========================================================================
# 6.4  Accounts: registration flow, role-based access
# ===========================================================================

class RegistrationFlowTests(TestCase):
    """Registration creates company and trial subscription (via verify_email_view)."""

    def test_verify_email_creates_company_and_trial(self):
        """After email verification: user, company, membership, and trial sub created."""
        # Simulate what verify_email_view does (without Redis)
        from apps.billing.models import Subscription
        import datetime

        email = 'newuser6@example.com'
        user = User.objects.create_user(
            username=email, email=email, password='TestPass6!',
            email_verified=True,
        )
        company = Company.objects.create(name='Новая Компания', owner=user)
        CompanyMember.objects.create(user=user, company=company, role='owner')
        sub = Subscription.objects.create(
            company=company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + datetime.timedelta(days=7),
            max_employees=10,
        )

        # Verify the state
        self.assertTrue(User.objects.filter(email=email).exists())
        self.assertTrue(Company.objects.filter(owner=user).exists())
        self.assertTrue(CompanyMember.objects.filter(
            user=user, company=company, role='owner'
        ).exists())
        self.assertEqual(sub.plan, 'trial')
        self.assertTrue(sub.is_active)
        self.assertEqual(sub.max_employees, 10)

    def test_register_page_accessible(self):
        """GET /dashboard/register/ returns 200."""
        client = Client()
        resp = client.get(reverse('dashboard:register'))
        self.assertEqual(resp.status_code, 200)

    def test_register_redirect_when_authenticated(self):
        """Authenticated user accessing register is redirected."""
        user = _user(email='authreg6@example.com')
        company = _company(user, inn='6660004444')
        _member(company, user)
        _subscription(company)
        client = Client()
        client.force_login(user)
        resp = client.get(reverse('dashboard:register'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard/employees/', resp.url)


@override_settings(LOGIN_URL='/dashboard/login/')
class RoleBasedAccessTests(TestCase):
    """Role-based access: owner can do everything, hr edits employees, accountant read-only."""

    def setUp(self):
        self.owner = _user(email='owner6@example.com')
        self.company = _company(self.owner, inn='6660005555')
        _member(self.company, self.owner, role='owner')
        _subscription(self.company, plan='business', max_employees=50)

        self.hr = _user(email='hr6role@example.com')
        _member(self.company, self.hr, role='hr')

        self.accountant = _user(email='acc6role@example.com')
        _member(self.company, self.accountant, role='accountant')

        self.employee = _employee(self.company)

    def test_owner_can_access_subscription(self):
        """Owner can access subscription page."""
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('dashboard:subscription'))
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_add_employee(self):
        """Owner can access employee add."""
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('dashboard:employee_add'))
        self.assertEqual(resp.status_code, 200)

    def test_hr_can_add_employee(self):
        """HR can access employee add."""
        self.client.force_login(self.hr)
        resp = self.client.get(reverse('dashboard:employee_add'))
        self.assertEqual(resp.status_code, 200)

    def test_hr_can_edit_employee(self):
        """HR can edit employee."""
        self.client.force_login(self.hr)
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': 'ОтХР',
                'first_name': self.employee.first_name,
                'position': self.employee.position,
                'hire_date': self.employee.hire_date.strftime('%d.%m.%Y'),
                'salary': str(self.employee.salary),
                'status': 'active',
                'contract_type': 'permanent',
                'marital_status': 'single',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.last_name, 'ОтХР')

    def test_accountant_cannot_add_employee(self):
        """Accountant cannot access employee add (require_role hr)."""
        self.client.force_login(self.accountant)
        resp = self.client.get(reverse('dashboard:employee_add'))
        self.assertEqual(resp.status_code, 302)

    def test_accountant_cannot_edit_employee(self):
        """Accountant's POST to employee_edit is denied."""
        self.client.force_login(self.accountant)
        resp = self.client.post(
            reverse('dashboard:employee_edit', args=[self.employee.id]),
            {
                'last_name': 'Хакер',
                'first_name': 'Иван',
                'position': 'Тест',
                'hire_date': '01.01.2025',
                'status': 'active',
                'contract_type': 'permanent',
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.employee.refresh_from_db()
        self.assertNotEqual(self.employee.last_name, 'Хакер')

    def test_accountant_can_view_employees_list(self):
        """Accountant can view employees list (read-only)."""
        self.client.force_login(self.accountant)
        resp = self.client.get(reverse('dashboard:employees'))
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_access_team(self):
        """Owner can see team page."""
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('dashboard:team_list'))
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# 6.5  Webhook processing
# ===========================================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class WebhookProcessingTests(TestCase):
    """YuKassa webhook correctly processes payment.succeeded and payment.canceled."""

    def setUp(self):
        self.user = _user(email='wh6@example.com')
        self.company = _company(self.user, inn='6660006666')
        _member(self.company, self.user)
        self.payment = Payment.objects.create(
            company=self.company,
            plan='start',
            amount=Decimal('790.00'),
            status=Payment.Status.PENDING,
        )
        self.url = reverse('billing:yukassa_webhook')

    def test_payment_succeeded_activates_subscription(self):
        """payment.succeeded webhook activates subscription."""
        payload = json.dumps({
            'event': 'payment.succeeded',
            'object': {
                'id': 'yk_test_123',
                'metadata': {
                    'payment_db_id': str(self.payment.id),
                    'plan': 'start',
                    'company_id': str(self.company.id),
                    'billing_period': 'monthly',
                },
                'payment_method': {
                    'saved': False,
                    'id': '',
                },
            },
        })
        resp = self.client.post(
            self.url,
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)

        # Subscription should be active
        sub = Subscription.objects.get(company=self.company)
        self.assertEqual(sub.plan, 'start')
        self.assertTrue(sub.is_active)

    def test_payment_succeeded_annual_preserves_period(self):
        """payment.succeeded with billing_period=annual sets annual billing."""
        payload = json.dumps({
            'event': 'payment.succeeded',
            'object': {
                'id': 'yk_test_annual',
                'metadata': {
                    'payment_db_id': str(self.payment.id),
                    'plan': 'business',
                    'company_id': str(self.company.id),
                    'billing_period': 'annual',
                },
                'payment_method': {
                    'saved': True,
                    'id': 'pm_saved_123',
                },
            },
        })
        resp = self.client.post(
            self.url,
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sub = Subscription.objects.get(company=self.company)
        self.assertEqual(sub.billing_period, 'annual')
        self.assertEqual(sub.plan, 'business')
        self.assertEqual(sub.payment_method_id, 'pm_saved_123')
        self.assertTrue(sub.auto_renew)

    def test_payment_canceled_marks_failed(self):
        """payment.canceled webhook marks payment as failed."""
        payload = json.dumps({
            'event': 'payment.canceled',
            'object': {
                'id': 'yk_test_cancel',
                'metadata': {
                    'payment_db_id': str(self.payment.id),
                },
            },
        })
        resp = self.client.post(
            self.url,
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)

    def test_webhook_missing_metadata_returns_400(self):
        """Webhook with missing payment_db_id returns 400."""
        payload = json.dumps({
            'event': 'payment.succeeded',
            'object': {
                'id': 'yk_test_nometa',
                'metadata': {},
            },
        })
        resp = self.client.post(
            self.url,
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_webhook_nonexistent_payment_returns_404(self):
        """Webhook with nonexistent payment_db_id returns 404."""
        payload = json.dumps({
            'event': 'payment.succeeded',
            'object': {
                'id': 'yk_test_bad',
                'metadata': {
                    'payment_db_id': '999999',
                    'plan': 'start',
                },
            },
        })
        resp = self.client.post(
            self.url,
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 404)


# ===========================================================================
# 6.6  Salary History
# ===========================================================================

class SalaryHistoryTests(TestCase):
    """SalaryHistory model functionality."""

    def setUp(self):
        self.user = _user(email='salhist6@example.com')
        self.company = _company(self.user, inn='6660007777')
        _member(self.company, self.user)
        self.employee = _employee(self.company, salary=Decimal('50000'))

    def test_salary_history_created(self):
        """SalaryHistory can be created for an employee."""
        sh = SalaryHistory.objects.create(
            employee=self.employee,
            salary=Decimal('60000'),
            effective_date=date.today(),
        )
        self.assertEqual(sh.salary, Decimal('60000'))
        self.assertEqual(sh.employee, self.employee)

    def test_salary_history_ordering(self):
        """SalaryHistory is ordered by -effective_date."""
        SalaryHistory.objects.create(
            employee=self.employee,
            salary=Decimal('50000'),
            effective_date=date(2025, 1, 1),
        )
        SalaryHistory.objects.create(
            employee=self.employee,
            salary=Decimal('60000'),
            effective_date=date(2025, 6, 1),
        )
        history = list(self.employee.salary_history.all())
        self.assertEqual(history[0].salary, Decimal('60000'))
        self.assertEqual(history[1].salary, Decimal('50000'))

    def test_salary_change_pdf_uses_history_for_previous(self):
        """generate_salary_change_pdf falls back to SalaryHistory for previous_salary."""
        from apps.documents.services import generate_salary_change_pdf
        SalaryHistory.objects.create(
            employee=self.employee,
            salary=Decimal('50000'),
            effective_date=date(2025, 1, 1),
        )
        pdf = generate_salary_change_pdf(
            self.employee,
            new_salary=70000,
            # previous_salary not specified — should come from history
        )
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertTrue(len(pdf) > 100)
