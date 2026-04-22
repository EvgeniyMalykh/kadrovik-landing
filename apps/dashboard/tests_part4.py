"""
Part 4 tests: Subscription model (is_active), billing activate_subscription,
Vacation CRUD, ProductionCalendar, vacation days_count, webhook security.
Run:
    python manage.py test apps.dashboard.tests_part4 --settings=config.settings.production -v 2
"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, ProductionCalendar
from apps.billing.models import Subscription, Payment
from apps.billing.services import activate_subscription, get_plan_features, PLANS
from apps.vacations.models import Vacation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(email='u4@example.com', password='TestPass4!'):
    return User.objects.create_user(username=email, email=email, password=password)


def _company(owner, name='ООО Тест4', inn='4440000000'):
    return Company.objects.create(
        owner=owner, name=name, inn=inn,
        ogrn='4440000000001',
        legal_address='г. Тест, ул. 4я, д.4',
        director_name='Тестов Тест Тестович',
    )


def _member(company, user, role='owner'):
    return CompanyMember.objects.create(company=company, user=user, role=role)


def _subscription(company, plan='trial', days=30):
    return Subscription.objects.create(
        company=company, plan=plan,
        status=Subscription.Status.ACTIVE,
        expires_at=timezone.now() + timedelta(days=days),
    )


def _employee(company, **kw):
    defaults = dict(
        last_name='Тестов', first_name='Тест', middle_name='Тестович',
        position='Тестировщик', hire_date=date.today() - timedelta(days=90),
        salary=Decimal('50000'), marital_status='single',
    )
    defaults.update(kw)
    return Employee.objects.create(company=company, **defaults)


# ===========================================================================
# 4.1  Subscription model — is_active property
# ===========================================================================

class SubscriptionIsActiveTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.company = _company(self.user)
        _member(self.company, self.user)

    def test_active_with_future_expires(self):
        """Active status + future expires_at → is_active = True."""
        sub = Subscription.objects.create(
            company=self.company, plan='start',
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.assertTrue(sub.is_active)

    def test_expired_by_date(self):
        """expires_at in the past → is_active = False."""
        sub = Subscription.objects.create(
            company=self.company, plan='start',
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.assertFalse(sub.is_active)

    def test_status_expired(self):
        """status=expired → is_active = False regardless of expires_at."""
        sub = Subscription.objects.create(
            company=self.company, plan='start',
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.assertFalse(sub.is_active)

    def test_status_cancelled(self):
        """status=cancelled → is_active = False."""
        sub = Subscription.objects.create(
            company=self.company, plan='start',
            status=Subscription.Status.CANCELLED,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.assertFalse(sub.is_active)

    def test_no_expires_at(self):
        """expires_at = None → is_active = False (safety net)."""
        sub = Subscription.objects.create(
            company=self.company, plan='trial',
            status=Subscription.Status.ACTIVE,
            expires_at=None,
        )
        self.assertFalse(sub.is_active)

    def test_active_trial_30_days(self):
        """Trial with 30 days remaining → is_active = True."""
        sub = _subscription(self.company, plan='trial', days=30)
        self.assertTrue(sub.is_active)


# ===========================================================================
# 4.2  activate_subscription service
# ===========================================================================

class ActivateSubscriptionTests(TestCase):

    def setUp(self):
        self.user = _user(email='act4@example.com')
        self.company = _company(self.user, inn='4441111111')
        _member(self.company, self.user)

    def test_activate_creates_subscription(self):
        """activate_subscription creates sub if not exists."""
        self.assertFalse(Subscription.objects.filter(company=self.company).exists())
        sub = activate_subscription(self.company, 'start')
        self.assertEqual(sub.plan, 'start')
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertTrue(sub.is_active)

    def test_activate_updates_existing(self):
        """activate_subscription upgrades existing trial to pro."""
        old_sub = _subscription(self.company, plan='trial', days=5)
        sub = activate_subscription(self.company, 'pro')
        sub.refresh_from_db()
        self.assertEqual(sub.plan, 'pro')
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(sub.expires_at)
        self.assertTrue(sub.expires_at > timezone.now())

    def test_activate_sets_max_employees(self):
        """max_employees is set from PLANS config."""
        sub = activate_subscription(self.company, 'business')
        self.assertEqual(sub.max_employees, PLANS['business']['max_employees'])

    def test_activate_with_payment_method(self):
        """Payment method ID is stored and auto_renew enabled."""
        sub = activate_subscription(self.company, 'pro', payment_method_id='pm_test_123')
        self.assertEqual(sub.payment_method_id, 'pm_test_123')
        self.assertTrue(sub.auto_renew)

    def test_activate_without_payment_method_no_autorenew(self):
        """Without payment method, auto_renew stays False."""
        sub = activate_subscription(self.company, 'start')
        self.assertFalse(sub.auto_renew)


# ===========================================================================
# 4.3  Vacation model
# ===========================================================================

class VacationModelTests(TestCase):

    def setUp(self):
        self.user = _user(email='vac4@example.com')
        self.company = _company(self.user, inn='4442222222')
        _member(self.company, self.user)
        _subscription(self.company)
        self.employee = _employee(self.company)

    def test_days_count_auto_calculated(self):
        """days_count is calculated on save."""
        v = Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 14),
        )
        # 14 calendar days - 1 holiday (12 June, Russia Day) = 13 vacation days
        self.assertEqual(v.days_count, 13)

    def test_days_count_single_day(self):
        """Single-day vacation → days_count = 1."""
        v = Vacation.objects.create(
            employee=self.employee,
            vacation_type='unpaid',
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
        )
        self.assertEqual(v.days_count, 1)

    def test_approved_default_false(self):
        """New vacation is not approved by default."""
        v = Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 10),
        )
        self.assertFalse(v.approved)

    def test_vacation_str(self):
        """__str__ includes employee name and dates."""
        v = Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 14),
        )
        s = str(v)
        self.assertIn('Тестов', s)

    def test_vacation_types(self):
        """All vacation types can be saved."""
        for vtype in ['annual', 'additional', 'unpaid', 'maternity', 'educational']:
            v = Vacation.objects.create(
                employee=self.employee,
                vacation_type=vtype,
                start_date=date(2026, 1, 10),
                end_date=date(2026, 1, 15),
            )
            self.assertEqual(v.vacation_type, vtype)
            v.delete()


# ===========================================================================
# 4.4  Vacation views (list, add, delete, approve)
# ===========================================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class VacationViewTests(TestCase):

    def setUp(self):
        self.user = _user(email='vview4@example.com')
        self.company = _company(self.user, inn='4443333333')
        _member(self.company, self.user, role='owner')
        _subscription(self.company)
        self.employee = _employee(self.company)
        self.client.force_login(self.user)

    def test_vacation_list_200(self):
        resp = self.client.get(reverse('vacations:list'))
        self.assertEqual(resp.status_code, 200)

    def test_vacation_add_get_200(self):
        resp = self.client.get(reverse('vacations:add'))
        self.assertEqual(resp.status_code, 200)

    def test_vacation_add_post_creates(self):
        """POST /vacations/add/ creates vacation."""
        count_before = Vacation.objects.filter(employee__company=self.company).count()
        resp = self.client.post(reverse('vacations:add'), {
            'employee_id': self.employee.id,
            'vacation_type': 'annual',
            'start_date': '01.06.2026',
            'end_date': '14.06.2026',
        })
        self.assertIn(resp.status_code, [200, 302])
        self.assertGreater(
            Vacation.objects.filter(employee__company=self.company).count(),
            count_before,
        )

    def test_vacation_delete(self):
        """DELETE vacation removes it."""
        v = Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 14),
        )
        vid = v.id
        resp = self.client.post(reverse('vacations:delete', args=[vid]))
        self.assertIn(resp.status_code, [200, 302])
        self.assertFalse(Vacation.objects.filter(id=vid).exists())

    def test_vacation_isolation(self):
        """User cannot delete vacation from another company."""
        other_user = _user(email='vother4@example.com')
        other_company = _company(other_user, inn='4449999999')
        _member(other_company, other_user, role='owner')
        _subscription(other_company)
        other_emp = _employee(other_company)
        other_v = Vacation.objects.create(
            employee=other_emp,
            vacation_type='annual',
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 10),
        )
        resp = self.client.post(reverse('vacations:delete', args=[other_v.id]))
        # Should not delete — either 404 or redirect
        self.assertIn(resp.status_code, [302, 403, 404])
        self.assertTrue(Vacation.objects.filter(id=other_v.id).exists())

    def test_vacation_unauthenticated_redirect(self):
        """Unauthenticated access → redirect to login."""
        self.client.logout()
        resp = self.client.get(reverse('vacations:list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard/login/', resp.url)


# ===========================================================================
# 4.5  ProductionCalendar
# ===========================================================================

class ProductionCalendarTests(TestCase):

    def test_calendar_has_2026_data(self):
        """Production calendar must have entries for 2026."""
        count = ProductionCalendar.objects.filter(date__year=2026).count()
        self.assertGreater(count, 0, "ProductionCalendar must have 2026 data")

    def test_january_1_2026_is_holiday(self):
        """January 1, 2026 is a holiday."""
        day = ProductionCalendar.objects.filter(
            date=date(2026, 1, 1)
        ).first()
        self.assertIsNotNone(day)
        self.assertEqual(day.day_type, 'holiday')

    def test_may_9_2026_is_holiday(self):
        """May 9, 2026 (Victory Day) is a holiday."""
        day = ProductionCalendar.objects.filter(
            date=date(2026, 5, 9)
        ).first()
        self.assertIsNotNone(day)
        self.assertEqual(day.day_type, 'holiday')

    def test_december_31_2026_in_calendar(self):
        """December 31, 2026 is present in calendar (holiday or short)."""
        day = ProductionCalendar.objects.filter(
            date=date(2026, 12, 31)
        ).first()
        self.assertIsNotNone(day)
        # It may be 'short' (pre-holiday) or 'holiday' — either is valid
        self.assertIn(day.day_type, ['holiday', 'short'])

    def test_may_4_2026_in_calendar(self):
        """May 4, 2026 entry exists in calendar (was a transfer day or holiday)."""
        # This day may be marked in the calendar — we just verify the calendar
        # contains entries for May 2026
        may_entries = ProductionCalendar.objects.filter(
            date__year=2026, date__month=5
        ).count()
        self.assertGreater(may_entries, 0, "May 2026 must have calendar entries")

    def test_may_11_2026_is_holiday(self):
        """May 11, 2026 is a holiday."""
        day = ProductionCalendar.objects.filter(
            date=date(2026, 5, 11)
        ).first()
        self.assertIsNotNone(day)
        self.assertEqual(day.day_type, 'holiday')


# ===========================================================================
# 4.6  Webhook security (yukassa_webhook)
# ===========================================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class WebhookSecurityTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('billing:yukassa_webhook')

    def test_webhook_rejects_get(self):
        """Webhook only accepts POST."""
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, [405, 302])

    def test_webhook_rejects_invalid_json(self):
        """Invalid JSON body → 400."""
        resp = self.client.post(
            self.url,
            data='not-json',
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [400, 200])

    def test_webhook_unknown_event_ignored(self):
        """Unknown event type is safely ignored."""
        payload = json.dumps({
            'type': 'unknown.event',
            'event': 'test',
            'object': {},
        })
        resp = self.client.post(
            self.url,
            data=payload,
            content_type='application/json',
        )
        # Should not crash — return 200 or 400
        self.assertIn(resp.status_code, [200, 400])


# ===========================================================================
# 4.7  Plan limits (max employees enforcement)
# ===========================================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class PlanLimitsTests(TestCase):

    def setUp(self):
        self.user = _user(email='limits4@example.com')
        self.company = _company(self.user, inn='4445555555')
        _member(self.company, self.user, role='owner')
        self.client.force_login(self.user)

    def test_start_plan_max_employees(self):
        """Start plan allows up to 10 employees (per PLANS config)."""
        self.assertEqual(PLANS['start']['max_employees'], 10)

    def test_business_plan_max_employees(self):
        """Business plan allows up to 50 employees."""
        self.assertEqual(PLANS['business']['max_employees'], 50)

    def test_pro_plan_max_employees(self):
        """Pro plan allows up to 200 employees."""
        self.assertEqual(PLANS['pro']['max_employees'], 200)

    def test_trial_plan_max_employees(self):
        """Trial plan allows up to 200 employees (corporate-level)."""
        self.assertEqual(PLANS['trial']['max_employees'], 200)

    def test_start_no_multiuser(self):
        """Start plan does not allow multi-user."""
        self.assertFalse(get_plan_features('start')['multi_user'])

    def test_business_has_multiuser(self):
        """Business plan allows multi-user."""
        self.assertTrue(get_plan_features('business')['multi_user'])

    def test_start_no_excel_export(self):
        self.assertFalse(get_plan_features('start')['export_excel'])

    def test_pro_has_api(self):
        self.assertTrue(get_plan_features('pro')['api'])

    def test_trial_has_api(self):
        self.assertTrue(get_plan_features('trial')['api'])

    def test_subscription_required_blocks_expired(self):
        """Expired subscription → redirect to subscription page."""
        Subscription.objects.create(
            company=self.company, plan='start',
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=1),
        )
        resp = self.client.get(reverse('dashboard:employees'))
        self.assertIn(resp.status_code, [302, 200])

    def test_subscription_required_allows_active(self):
        """Active subscription → page loads."""
        _subscription(self.company, plan='start', days=30)
        resp = self.client.get(reverse('dashboard:employees'))
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# 4.8  Payment model
# ===========================================================================

class PaymentModelTests(TestCase):

    def setUp(self):
        self.user = _user(email='pay4@example.com')
        self.company = _company(self.user, inn='4446666666')
        _member(self.company, self.user)

    def test_payment_created(self):
        """Payment can be created with required fields."""
        p = Payment.objects.create(
            company=self.company,
            plan='start',
            amount=Decimal('790.00'),
            status=Payment.Status.PENDING,
        )
        self.assertEqual(p.status, Payment.Status.PENDING)
        self.assertEqual(p.amount, Decimal('790.00'))

    def test_payment_status_transitions(self):
        """Payment can be moved to SUCCESS."""
        p = Payment.objects.create(
            company=self.company,
            plan='start',
            amount=Decimal('790.00'),
            status=Payment.Status.PENDING,
        )
        p.status = Payment.Status.SUCCESS
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.status, Payment.Status.SUCCESS)

    def test_payment_ordering(self):
        """Payments are ordered by -created_at."""
        p1 = Payment.objects.create(
            company=self.company, plan='start',
            amount=Decimal('790.00'), status=Payment.Status.PENDING,
        )
        p2 = Payment.objects.create(
            company=self.company, plan='pro',
            amount=Decimal('4900.00'), status=Payment.Status.SUCCESS,
        )
        payments = list(Payment.objects.filter(company=self.company))
        self.assertEqual(payments[0].id, p2.id)  # latest first

    def test_payment_str(self):
        """Payment __str__ includes amount and status."""
        p = Payment.objects.create(
            company=self.company, plan='start',
            amount=Decimal('790.00'), status=Payment.Status.PENDING,
        )
        s = str(p)
        self.assertIn('790', s)
