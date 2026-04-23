"""
Comprehensive billing tests for Kadrovik billing module.
Covers: models, middleware, decorator, services, Celery tasks, employee limits,
webhook handler, trial lifecycle, grace period, plan limits, reactivation,
annual billing, IP verification.
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, Client, override_settings
from django.utils import timezone
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.auth import get_user_model
from django.core import mail

from apps.billing.models import Subscription, Payment
from apps.billing.services import (
    activate_subscription,
    create_trial_subscription,
    get_subscription_context,
    PLANS,
    PLAN_PRICES,
)
from apps.billing.middleware import SubscriptionMiddleware
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, Department

User = get_user_model()


# helpers

def _create_user(email="test@example.com", password="testpass123"):
    return User.objects.create_user(
        username=email.split("@")[0],
        email=email,
        password=password,
    )


def _create_company_with_owner(user, name="Test LLC"):
    company = Company.objects.create(
        owner=user,
        name=name,
        inn="1234567890",
        legal_address="Test Address",
        director_name="Test Director",
    )
    CompanyMember.objects.create(company=company, user=user, role="owner")
    return company


def _create_subscription(company, **kwargs):
    defaults = dict(
        plan=Subscription.Plan.TRIAL,
        status=Subscription.Status.ACTIVE,
        started_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=7),
        max_employees=10,
    )
    defaults.update(kwargs)
    sub, _ = Subscription.objects.get_or_create(company=company, defaults=defaults)
    if not _:
        for k, v in defaults.items():
            setattr(sub, k, v)
        sub.save()
    return sub


def _add_session_and_messages(request):
    sm = SessionMiddleware(lambda r: None)
    sm.process_request(request)
    request.session.save()
    mm = MessageMiddleware(lambda r: None)
    mm.process_request(request)


# 2.1  Model tests

class TestSubscriptionModel(TestCase):

    def setUp(self):
        self.user = _create_user()
        self.company = _create_company_with_owner(self.user)

    def test_is_active_true(self):
        sub = _create_subscription(
            self.company,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.assertTrue(sub.is_active)

    def test_is_active_expired(self):
        sub = _create_subscription(
            self.company,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(sub.is_active)

    def test_is_active_cancelled_status(self):
        sub = _create_subscription(
            self.company,
            status=Subscription.Status.CANCELLED,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.assertFalse(sub.is_active)

    def test_is_active_expired_status(self):
        sub = _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.assertFalse(sub.is_active)

    def test_is_active_none_expires_at(self):
        sub = _create_subscription(
            self.company,
            status=Subscription.Status.ACTIVE,
            expires_at=None,
        )
        self.assertFalse(sub.is_active)

    def test_is_trial_true(self):
        sub = _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertEqual(sub.plan, Subscription.Plan.TRIAL)
        self.assertTrue(sub.is_active)

    def test_is_trial_expired(self):
        sub = _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(sub.plan, Subscription.Plan.TRIAL)
        self.assertFalse(sub.is_active)

    def test_data_deletion_fields(self):
        sub = _create_subscription(self.company)
        self.assertTrue(hasattr(sub, "data_deletion_scheduled_at"))
        self.assertTrue(hasattr(sub, "data_cleaned"))
        self.assertIsNone(sub.data_deletion_scheduled_at)
        self.assertFalse(sub.data_cleaned)

    def test_subscription_str(self):
        sub = _create_subscription(self.company, plan=Subscription.Plan.START)
        self.assertIn("Старт", str(sub))

    def test_payment_str(self):
        payment = Payment.objects.create(
            company=self.company, amount=790, plan='start',
            status=Payment.Status.PENDING,
        )
        self.assertIn("790", str(payment))


# 2.2  Middleware tests

@override_settings(ROOT_URLCONF="config.urls")
class TestSubscriptionMiddleware(TestCase):

    def setUp(self):
        self.user = _create_user(email="mw@example.com")
        self.user.set_password("testpass123")
        self.user.save()
        self.company = _create_company_with_owner(self.user, name="MW Corp")
        self.client = Client()
        self.client.login(email="mw@example.com", password="testpass123")

    def test_exempt_paths_not_blocked(self):
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        for path in ["/dashboard/login/", "/dashboard/subscription/"]:
            resp = self.client.get(path)
            if resp.status_code == 302:
                self.assertNotIn(
                    "/dashboard/subscription/", resp.url,
                ) if "subscription" not in path else None

    def test_employees_blocked_without_subscription(self):
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)

    def test_dashboard_accessible_with_active_subscription(self):
        _create_subscription(
            self.company,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
        )
        resp = self.client.get("/dashboard/employees/")
        if resp.status_code == 302:
            self.assertNotIn("/dashboard/subscription/", resp.url)

    def test_ajax_returns_402(self):
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        resp = self.client.get(
            "/dashboard/employees/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 402)
        data = resp.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "subscription_expired")

    def test_htmx_returns_402(self):
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        resp = self.client.get(
            "/dashboard/employees/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 402)

    def test_static_paths_not_blocked(self):
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        resp = self.client.get("/static/css/style.css")
        if resp.status_code == 302:
            self.assertNotIn("/dashboard/subscription/", resp.url)


# 2.3  subscription_required decorator tests

@override_settings(ROOT_URLCONF="config.urls")
class TestSubscriptionRequired(TestCase):

    def setUp(self):
        self.user = _create_user(email="dec@example.com")
        self.user.set_password("testpass123")
        self.user.save()
        self.company = _create_company_with_owner(self.user, name="Dec Corp")
        self.client = Client()
        self.client.login(email="dec@example.com", password="testpass123")

    def test_employee_add_blocked(self):
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        resp = self.client.post("/dashboard/employees/add/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)

    def test_employee_delete_blocked(self):
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        emp = Employee.objects.create(
            company=self.company, first_name="Test", last_name="User",
            position="Dev", hire_date=timezone.now().date(),
        )
        resp = self.client.post(f"/dashboard/employees/{emp.id}/delete/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)


# 2.4  Services tests

class TestBillingServices(TestCase):

    def setUp(self):
        self.user = _create_user(email="svc@example.com")
        self.company = _create_company_with_owner(self.user, name="Svc Corp")

    def test_activate_subscription_monthly(self):
        sub = activate_subscription(self.company, "start", billing_period="monthly")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.plan, "start")
        expected = timezone.now() + timedelta(days=30)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)

    def test_activate_subscription_annual(self):
        sub = activate_subscription(self.company, "business", billing_period="annual")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        expected = timezone.now() + timedelta(days=365)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)

    def test_activate_subscription_trial_gives_7_days(self):
        sub = activate_subscription(self.company, "trial")
        self.assertEqual(sub.plan, "trial")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        expected = timezone.now() + timedelta(days=7)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)
        self.assertEqual(sub.max_employees, 200)

    def test_activate_subscription_resets_grace_period(self):
        sub = _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
            data_deletion_scheduled_at=timezone.now() + timedelta(days=25),
            data_cleaned=False,
        )
        sub.data_cleaned = True
        sub.save()
        activated = activate_subscription(self.company, "start")
        self.assertIsNone(activated.data_deletion_scheduled_at)
        self.assertFalse(activated.data_cleaned)
        self.assertEqual(activated.status, Subscription.Status.ACTIVE)

    def test_activate_subscription_saves_payment_method(self):
        sub = activate_subscription(self.company, "start", payment_method_id="pm_test_123")
        self.assertEqual(sub.payment_method_id, "pm_test_123")
        self.assertTrue(sub.auto_renew)

    def test_activate_subscription_no_payment_method(self):
        sub = activate_subscription(self.company, "start")
        self.assertEqual(sub.payment_method_id, "")
        self.assertFalse(sub.auto_renew)

    def test_get_subscription_context_trial(self):
        _create_subscription(self.company, plan=Subscription.Plan.TRIAL, max_employees=200)
        ctx = get_subscription_context(self.company)
        self.assertEqual(ctx["plan_key"], "trial")
        self.assertEqual(ctx["max_employees"], 200)
        self.assertTrue(ctx["plan_features"]["documents"])
        self.assertTrue(ctx["plan_features"]["export_excel"])

    def test_get_subscription_context_paid(self):
        _create_subscription(self.company, plan=Subscription.Plan.BUSINESS, max_employees=50)
        ctx = get_subscription_context(self.company)
        self.assertEqual(ctx["plan_key"], "business")
        self.assertEqual(ctx["max_employees"], 50)

    def test_get_subscription_context_no_company(self):
        ctx = get_subscription_context(None)
        self.assertEqual(ctx["plan_key"], "start")
        self.assertEqual(ctx["max_employees"], 10)

    def test_create_trial_subscription(self):
        sub = create_trial_subscription(self.company)
        self.assertEqual(sub.plan, "trial")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.max_employees, 200)
        expected = timezone.now() + timedelta(days=7)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)

    def test_create_trial_subscription_idempotent(self):
        sub1 = create_trial_subscription(self.company)
        sub1.plan = "start"
        sub1.save()
        sub2 = create_trial_subscription(self.company)
        self.assertEqual(sub2.plan, "trial")
        self.assertEqual(sub1.id, sub2.id)

    def test_plans_dict_correctness(self):
        self.assertEqual(PLANS["trial"]["max_employees"], 200)
        self.assertEqual(PLANS["trial"]["price"], 0)
        self.assertEqual(PLANS["start"]["max_employees"], 10)
        self.assertEqual(PLANS["start"]["price"], 790)
        self.assertEqual(PLANS["business"]["max_employees"], 50)
        self.assertEqual(PLANS["business"]["price"], 1990)
        self.assertEqual(PLANS["pro"]["max_employees"], 200)
        self.assertEqual(PLANS["pro"]["price"], 4900)

    def test_plan_prices_annual(self):
        self.assertEqual(PLAN_PRICES["start"]["annual"], 7110)
        self.assertEqual(PLAN_PRICES["business"]["annual"], 17910)
        self.assertEqual(PLAN_PRICES["pro"]["annual"], 44100)

    def test_plan_features_trial_has_all(self):
        trial_features = PLANS["trial"]["features"]
        pro_features = PLANS["pro"]["features"]
        for key, val in pro_features.items():
            self.assertEqual(trial_features[key], val,
                             f"Trial feature '{key}' should match pro")

    def test_plan_features_start_limited(self):
        features = PLANS["start"]["features"]
        self.assertTrue(features["documents"])
        self.assertTrue(features["telegram"])
        self.assertTrue(features["timesheet"])
        self.assertFalse(features["email_notify"])
        self.assertFalse(features["multi_user"])
        self.assertFalse(features["export_excel"])

    def test_plan_features_business_intermediate(self):
        features = PLANS["business"]["features"]
        self.assertTrue(features["documents"])
        self.assertTrue(features["multi_user"])
        self.assertTrue(features["export_excel"])
        self.assertFalse(features["custom_templates"])
        self.assertFalse(features["priority_support"])


# 2.5  Celery task tests

class TestBillingTasks(TestCase):

    def setUp(self):
        self.user = _create_user(email="task@example.com")
        self.company = _create_company_with_owner(self.user, name="Task Corp")

    def test_check_expired_subscriptions_marks_paid_expired(self):
        from apps.billing.tasks import check_expired_subscriptions
        expires = timezone.now() - timedelta(days=2)
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.ACTIVE, expires_at=expires,
        )
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertIsNotNone(sub.data_deletion_scheduled_at)
        expected_deletion = expires + timedelta(days=30)
        self.assertAlmostEqual(
            sub.data_deletion_scheduled_at.timestamp(),
            expected_deletion.timestamp(), delta=5,
        )

    def test_check_expired_subscriptions_trial_no_deletion_date(self):
        from apps.billing.tasks import check_expired_subscriptions
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(days=1),
        )
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertIsNone(sub.data_deletion_scheduled_at)

    def test_check_expired_does_not_touch_already_expired(self):
        from apps.billing.tasks import check_expired_subscriptions
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=10),
            data_deletion_scheduled_at=timezone.now() + timedelta(days=20),
        )
        original_deletion = sub.data_deletion_scheduled_at
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertAlmostEqual(
            sub.data_deletion_scheduled_at.timestamp(),
            original_deletion.timestamp(), delta=5,
        )

    def test_check_expired_business_plan(self):
        from apps.billing.tasks import check_expired_subscriptions
        expires = timezone.now() - timedelta(days=1)
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.BUSINESS,
            status=Subscription.Status.ACTIVE, expires_at=expires,
        )
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertIsNotNone(sub.data_deletion_scheduled_at)

    def test_check_expired_pro_plan(self):
        from apps.billing.tasks import check_expired_subscriptions
        expires = timezone.now() - timedelta(days=1)
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.PRO,
            status=Subscription.Status.ACTIVE, expires_at=expires,
        )
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertIsNotNone(sub.data_deletion_scheduled_at)

    def test_cleanup_deletes_employee_data(self):
        from apps.billing.tasks import cleanup_expired_company_data
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=35),
            data_deletion_scheduled_at=timezone.now() - timedelta(days=1),
        )
        sub.data_cleaned = False
        sub.save()
        Employee.objects.create(
            company=self.company, first_name="Alice", last_name="Smith",
            position="Dev", hire_date=timezone.now().date(),
        )
        Employee.objects.create(
            company=self.company, first_name="Bob", last_name="Jones",
            position="QA", hire_date=timezone.now().date(),
        )
        self.assertEqual(Employee.objects.filter(company=self.company).count(), 2)
        cleanup_expired_company_data()
        self.assertEqual(Employee.objects.filter(company=self.company).count(), 0)
        self.assertTrue(Company.objects.filter(id=self.company.id).exists())
        self.assertTrue(User.objects.filter(id=self.user.id).exists())
        sub.refresh_from_db()
        self.assertTrue(sub.data_cleaned)

    def test_cleanup_skips_already_cleaned(self):
        from apps.billing.tasks import cleanup_expired_company_data
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=35),
            data_deletion_scheduled_at=timezone.now() - timedelta(days=1),
        )
        sub.data_cleaned = True
        sub.save()
        emp = Employee.objects.create(
            company=self.company, first_name="Alice", last_name="Smith",
            position="Dev", hire_date=timezone.now().date(),
        )
        cleanup_expired_company_data()
        self.assertTrue(Employee.objects.filter(id=emp.id).exists())

    def test_cleanup_does_not_delete_before_grace(self):
        from apps.billing.tasks import cleanup_expired_company_data
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
            data_deletion_scheduled_at=timezone.now() + timedelta(days=25),
        )
        sub.data_cleaned = False
        sub.save()
        dept = Department.objects.create(company=self.company, name="IT")
        cleanup_expired_company_data()
        self.assertTrue(Department.objects.filter(id=dept.id).exists())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_send_expiry_warnings_7days(self):
        from apps.billing.tasks import send_expiry_warnings
        self.user.email = "owner@example.com"
        self.user.save()
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
            data_deletion_scheduled_at=timezone.now() + timedelta(days=7),
        )
        sub.data_cleaned = False
        sub.save()
        mail.outbox = []
        send_expiry_warnings()
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("7", mail.outbox[0].subject)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_send_expiry_warnings_1day(self):
        from apps.billing.tasks import send_expiry_warnings
        self.user.email = "owner@example.com"
        self.user.save()
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=29),
            data_deletion_scheduled_at=timezone.now() + timedelta(days=1),
        )
        sub.data_cleaned = False
        sub.save()
        mail.outbox = []
        send_expiry_warnings()
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("1", mail.outbox[0].subject)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_send_expiry_warnings_no_email_for_cleaned(self):
        from apps.billing.tasks import send_expiry_warnings
        self.user.email = "owner@example.com"
        self.user.save()
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
            data_deletion_scheduled_at=timezone.now() + timedelta(days=7),
        )
        sub.data_cleaned = True
        sub.save()
        mail.outbox = []
        send_expiry_warnings()
        self.assertEqual(len(mail.outbox), 0)


# 2.6  Employee limit tests

class TestEmployeeLimits(TestCase):

    def setUp(self):
        self.user = _create_user(email="limit@example.com")
        self.company = _create_company_with_owner(self.user, name="Limit Corp")

    def test_cannot_add_employee_over_limit(self):
        _create_subscription(
            self.company, plan=Subscription.Plan.START,
            max_employees=2, status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
        )
        Employee.objects.create(
            company=self.company, first_name="A", last_name="One",
            position="Dev", hire_date=timezone.now().date(),
        )
        Employee.objects.create(
            company=self.company, first_name="B", last_name="Two",
            position="Dev", hire_date=timezone.now().date(),
        )
        ctx = get_subscription_context(self.company)
        self.assertFalse(ctx["can_add_employee"])
        self.assertEqual(ctx["employee_count"], 2)
        self.assertEqual(ctx["max_employees"], 2)

    def test_can_add_employee_within_limit(self):
        _create_subscription(
            self.company, plan=Subscription.Plan.BUSINESS,
            max_employees=50, status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
        )
        Employee.objects.create(
            company=self.company, first_name="C", last_name="Three",
            position="Dev", hire_date=timezone.now().date(),
        )
        ctx = get_subscription_context(self.company)
        self.assertTrue(ctx["can_add_employee"])
        self.assertEqual(ctx["employee_count"], 1)
        self.assertEqual(ctx["max_employees"], 50)

    def test_limit_per_plan(self):
        for plan_key, expected_limit in [("trial", 200), ("start", 10), ("business", 50), ("pro", 200)]:
            self.assertEqual(PLANS[plan_key]["max_employees"], expected_limit)

    def test_limit_exact_boundary(self):
        _create_subscription(
            self.company, plan=Subscription.Plan.START,
            max_employees=1, status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
        )
        Employee.objects.create(
            company=self.company, first_name="Only", last_name="One",
            position="Dev", hire_date=timezone.now().date(),
        )
        ctx = get_subscription_context(self.company)
        self.assertFalse(ctx["can_add_employee"])

    def test_limit_zero_employees(self):
        _create_subscription(
            self.company, plan=Subscription.Plan.START,
            max_employees=10, status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
        )
        ctx = get_subscription_context(self.company)
        self.assertTrue(ctx["can_add_employee"])
        self.assertEqual(ctx["employee_count"], 0)


# 2.7  Webhook handler tests

@override_settings(ROOT_URLCONF="config.urls")
class TestYukassaWebhook(TestCase):

    def setUp(self):
        self.user = _create_user(email="wh@example.com")
        self.company = _create_company_with_owner(self.user, name="WH Corp")
        self.client = Client()

    def _webhook_url(self):
        return "/dashboard/webhook/yukassa/"

    def _post_webhook(self, data, ip="185.71.76.1"):
        import json
        return self.client.post(
            self._webhook_url(),
            data=json.dumps(data),
            content_type="application/json",
            REMOTE_ADDR=ip,
        )

    def test_webhook_payment_succeeded_activates_subscription(self):
        payment = Payment.objects.create(
            company=self.company, amount=790, plan='start',
            status=Payment.Status.PENDING,
        )
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_test_123",
                "metadata": {
                    "payment_db_id": str(payment.id),
                    "plan": "start",
                    "company_id": str(self.company.id),
                    "billing_period": "monthly",
                },
                "payment_method": {"id": "pm_test_1", "saved": False, "type": "bank_card"},
            },
        }
        resp = self._post_webhook(data)
        self.assertEqual(resp.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        sub = Subscription.objects.get(company=self.company)
        self.assertEqual(sub.plan, "start")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.max_employees, 10)

    def test_webhook_payment_succeeded_annual(self):
        payment = Payment.objects.create(
            company=self.company, amount=7110, plan='start',
            status=Payment.Status.PENDING,
        )
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_test_annual",
                "metadata": {
                    "payment_db_id": str(payment.id),
                    "plan": "start",
                    "company_id": str(self.company.id),
                    "billing_period": "annual",
                },
                "payment_method": {"id": "pm_1", "saved": False},
            },
        }
        resp = self._post_webhook(data)
        self.assertEqual(resp.status_code, 200)
        sub = Subscription.objects.get(company=self.company)
        expected = timezone.now() + timedelta(days=365)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)

    def test_webhook_saves_payment_method(self):
        payment = Payment.objects.create(
            company=self.company, amount=790, plan='start',
            status=Payment.Status.PENDING,
        )
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_test_saved",
                "metadata": {
                    "payment_db_id": str(payment.id),
                    "plan": "start",
                    "company_id": str(self.company.id),
                    "billing_period": "monthly",
                },
                "payment_method": {
                    "id": "pm_saved_123", "saved": True,
                    "type": "bank_card",
                    "card": {"last4": "4242", "card_type": "Visa"},
                },
            },
        }
        resp = self._post_webhook(data)
        self.assertEqual(resp.status_code, 200)
        sub = Subscription.objects.get(company=self.company)
        self.assertEqual(sub.payment_method_id, "pm_saved_123")
        self.assertTrue(sub.auto_renew)
        self.assertEqual(sub.card_last4, "4242")
        self.assertEqual(sub.card_brand, "Visa")

    def test_webhook_payment_canceled(self):
        payment = Payment.objects.create(
            company=self.company, amount=790, plan='start',
            status=Payment.Status.PENDING,
        )
        data = {
            "event": "payment.canceled",
            "object": {
                "id": "yk_cancel_123",
                "metadata": {"payment_db_id": str(payment.id)},
                "cancellation_details": {"reason": "expired_on_confirmation", "party": "yoo_kassa"},
            },
        }
        resp = self._post_webhook(data)
        self.assertEqual(resp.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)

    def test_webhook_invalid_json(self):
        import json
        resp = self.client.post(
            self._webhook_url(), data="not json",
            content_type="application/json", REMOTE_ADDR="185.71.76.1",
        )
        self.assertIn(resp.status_code, [400, 403])

    def test_webhook_missing_metadata(self):
        data = {
            "event": "payment.succeeded",
            "object": {"id": "yk_no_meta", "metadata": {}, "payment_method": {}},
        }
        resp = self._post_webhook(data)
        self.assertEqual(resp.status_code, 400)

    def test_webhook_nonexistent_payment(self):
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_bad_id",
                "metadata": {"payment_db_id": "999999", "plan": "start"},
                "payment_method": {},
            },
        }
        resp = self._post_webhook(data)
        self.assertEqual(resp.status_code, 404)

    def test_webhook_untrusted_ip_blocked(self):
        data = {"event": "payment.succeeded", "object": {"id": "yk_test"}}
        resp = self._post_webhook(data, ip="1.2.3.4")
        self.assertEqual(resp.status_code, 403)

    def test_webhook_trusted_ip_allowed(self):
        payment = Payment.objects.create(
            company=self.company, amount=790, plan='start',
            status=Payment.Status.PENDING,
        )
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_trusted",
                "metadata": {
                    "payment_db_id": str(payment.id),
                    "plan": "start",
                    "company_id": str(self.company.id),
                    "billing_period": "monthly",
                },
                "payment_method": {"id": "pm_1", "saved": False},
            },
        }
        for ip in ["185.71.76.1", "77.75.153.1", "77.75.156.11"]:
            payment.status = Payment.Status.PENDING
            payment.save()
            resp = self._post_webhook(data, ip=ip)
            self.assertEqual(resp.status_code, 200, f"IP {ip} should be trusted")

    def test_webhook_reactivation_resets_grace_period(self):
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
            data_deletion_scheduled_at=timezone.now() + timedelta(days=25),
        )
        payment = Payment.objects.create(
            company=self.company, amount=1990, plan='business',
            status=Payment.Status.PENDING,
        )
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_reactivate",
                "metadata": {
                    "payment_db_id": str(payment.id),
                    "plan": "business",
                    "company_id": str(self.company.id),
                    "billing_period": "monthly",
                },
                "payment_method": {"id": "pm_1", "saved": False},
            },
        }
        resp = self._post_webhook(data)
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.plan, "business")
        self.assertIsNone(sub.data_deletion_scheduled_at)
        self.assertFalse(sub.data_cleaned)


# 2.8  Trial lifecycle tests

class TestTrialLifecycle(TestCase):

    def setUp(self):
        self.user = _create_user(email="trial@example.com")
        self.company = _create_company_with_owner(self.user, name="Trial Corp")

    def test_trial_full_lifecycle(self):
        from apps.billing.tasks import check_expired_subscriptions
        sub = create_trial_subscription(self.company)
        self.assertTrue(sub.is_active)
        self.assertEqual(sub.max_employees, 200)
        sub.expires_at = timezone.now() - timedelta(hours=1)
        sub.save()
        self.assertFalse(sub.is_active)
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertIsNone(sub.data_deletion_scheduled_at)

    def test_trial_has_all_features_like_pro(self):
        trial_features = PLANS["trial"]["features"]
        pro_features = PLANS["pro"]["features"]
        self.assertEqual(trial_features, pro_features)


# 2.9  Grace period full lifecycle tests

class TestGracePeriodLifecycle(TestCase):

    def setUp(self):
        self.user = _create_user(email="grace@example.com")
        self.user.email = "grace@example.com"
        self.user.save()
        self.company = _create_company_with_owner(self.user, name="Grace Corp")

    def test_paid_plan_full_grace_period_lifecycle(self):
        from apps.billing.tasks import check_expired_subscriptions, cleanup_expired_company_data
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.BUSINESS,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(hours=1),
            max_employees=50,
        )
        dept = Department.objects.create(company=self.company, name="Engineering")
        Employee.objects.create(
            company=self.company, first_name="Grace", last_name="Employee",
            position="Dev", hire_date=timezone.now().date(), department=dept,
        )
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertIsNotNone(sub.data_deletion_scheduled_at)
        self.assertFalse(sub.data_cleaned)
        cleanup_expired_company_data()
        self.assertEqual(Employee.objects.filter(company=self.company).count(), 1)
        sub.data_deletion_scheduled_at = timezone.now() - timedelta(hours=1)
        sub.save()
        cleanup_expired_company_data()
        self.assertEqual(Employee.objects.filter(company=self.company).count(), 0)
        self.assertEqual(Department.objects.filter(company=self.company).count(), 0)
        sub.refresh_from_db()
        self.assertTrue(sub.data_cleaned)

    def test_reactivation_during_grace_period(self):
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
            data_deletion_scheduled_at=timezone.now() + timedelta(days=25),
        )
        emp = Employee.objects.create(
            company=self.company, first_name="Saved", last_name="Employee",
            position="Dev", hire_date=timezone.now().date(),
        )
        activated = activate_subscription(self.company, "business")
        self.assertEqual(activated.status, Subscription.Status.ACTIVE)
        self.assertIsNone(activated.data_deletion_scheduled_at)
        self.assertFalse(activated.data_cleaned)
        self.assertTrue(Employee.objects.filter(id=emp.id).exists())

    def test_reactivation_after_cleanup(self):
        sub = _create_subscription(
            self.company, plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=35),
        )
        sub.data_cleaned = True
        sub.data_deletion_scheduled_at = None
        sub.save()
        activated = activate_subscription(self.company, "start")
        self.assertEqual(activated.status, Subscription.Status.ACTIVE)
        self.assertFalse(activated.data_cleaned)
        self.assertIsNone(activated.data_deletion_scheduled_at)
        self.assertEqual(Employee.objects.filter(company=self.company).count(), 0)


# 2.10  Annual billing tests

class TestAnnualBilling(TestCase):

    def setUp(self):
        self.user = _create_user(email="annual@example.com")
        self.company = _create_company_with_owner(self.user, name="Annual Corp")

    def test_annual_start_365_days(self):
        sub = activate_subscription(self.company, "start", billing_period="annual")
        expected = timezone.now() + timedelta(days=365)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)
        self.assertEqual(sub.billing_period, "annual")

    def test_annual_business_365_days(self):
        sub = activate_subscription(self.company, "business", billing_period="annual")
        expected = timezone.now() + timedelta(days=365)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)

    def test_annual_pro_365_days(self):
        sub = activate_subscription(self.company, "pro", billing_period="annual")
        expected = timezone.now() + timedelta(days=365)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)

    def test_monthly_start_30_days(self):
        sub = activate_subscription(self.company, "start", billing_period="monthly")
        expected = timezone.now() + timedelta(days=30)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)
        self.assertEqual(sub.billing_period, "monthly")


# 2.11  IP verification tests

class TestWebhookIPVerification(TestCase):

    def test_check_yukassa_ip_trusted(self):
        from apps.billing.views import _check_yukassa_ip
        factory = RequestFactory()
        for ip in ["185.71.76.1", "185.71.76.30", "77.75.153.1", "77.75.156.11", "77.75.156.35"]:
            request = factory.post("/", REMOTE_ADDR=ip)
            self.assertTrue(_check_yukassa_ip(request), f"IP {ip} should be trusted")

    def test_check_yukassa_ip_untrusted(self):
        from apps.billing.views import _check_yukassa_ip
        factory = RequestFactory()
        for ip in ["1.2.3.4", "192.168.1.1", "10.0.0.1", "8.8.8.8"]:
            request = factory.post("/", REMOTE_ADDR=ip)
            self.assertFalse(_check_yukassa_ip(request), f"IP {ip} should be untrusted")

    def test_check_yukassa_ip_via_x_forwarded_for(self):
        from apps.billing.views import _check_yukassa_ip
        factory = RequestFactory()
        request = factory.post("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="185.71.76.1, 10.0.0.1")
        self.assertTrue(_check_yukassa_ip(request))
        request = factory.post("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 10.0.0.1")
        self.assertFalse(_check_yukassa_ip(request))


# 2.12  Trial expiry warning tests

class TestTrialExpiryWarnings(TestCase):

    def setUp(self):
        self.user = _create_user(email="trialwarn@example.com")
        self.user.email = "trialwarn@example.com"
        self.user.save()
        self.company = _create_company_with_owner(self.user, name="TrialWarn Corp")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_trial_warning_3_days_before(self):
        from apps.billing.tasks import send_expiry_warnings
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=3),
            max_employees=200,
        )
        mail.outbox = []
        send_expiry_warnings()
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("3", mail.outbox[0].subject)
        self.assertIn("Пробный период", mail.outbox[0].subject)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_trial_warning_1_day_before(self):
        from apps.billing.tasks import send_expiry_warnings
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=1),
            max_employees=200,
        )
        mail.outbox = []
        send_expiry_warnings()
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("1", mail.outbox[0].subject)
        self.assertIn("Пробный период", mail.outbox[0].subject)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_no_warning_for_expired_trial(self):
        """Expired trial should not receive trial warnings (it's already expired)."""
        from apps.billing.tasks import send_expiry_warnings
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=1),
            max_employees=200,
        )
        mail.outbox = []
        send_expiry_warnings()
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_no_trial_warning_for_paid_plan(self):
        """Paid plans should not get trial expiry warnings."""
        from apps.billing.tasks import send_expiry_warnings
        _create_subscription(
            self.company,
            plan=Subscription.Plan.START,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=3),
            max_employees=10,
        )
        mail.outbox = []
        send_expiry_warnings()
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_no_warning_far_from_expiry(self):
        """Trial expiring in 6 days should not trigger any warning."""
        from apps.billing.tasks import send_expiry_warnings
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=6),
            max_employees=200,
        )
        mail.outbox = []
        send_expiry_warnings()
        self.assertEqual(len(mail.outbox), 0)


# 2.13  Middleware trial-specific tests

@override_settings(ROOT_URLCONF="config.urls")
class TestTrialMiddlewareBlocking(TestCase):

    def setUp(self):
        self.user = _create_user(email="trialmw@example.com")
        self.user.set_password("testpass123")
        self.user.save()
        self.company = _create_company_with_owner(self.user, name="TrialMW Corp")
        self.client = Client()
        self.client.login(email="trialmw@example.com", password="testpass123")

    def test_active_trial_allows_access(self):
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=5),
            max_employees=200,
        )
        resp = self.client.get("/dashboard/employees/")
        if resp.status_code == 302:
            self.assertNotIn("/dashboard/subscription/", resp.url)

    def test_expired_trial_blocks_dashboard(self):
        """Trial with expires_at in the past should block access even if status=active."""
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(hours=1),
            max_employees=200,
        )
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)

    def test_expired_trial_status_blocks_dashboard(self):
        """Trial with status=expired should block access."""
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=1),
            max_employees=200,
        )
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)

    def test_expired_trial_subscription_page_accessible(self):
        """Subscription page should be accessible even with expired trial."""
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=1),
            max_employees=200,
        )
        resp = self.client.get("/dashboard/subscription/")
        self.assertNotEqual(resp.status_code, 302)

    def test_expired_trial_checkout_accessible(self):
        """Checkout paths should be accessible with expired trial."""
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=1),
            max_employees=200,
        )
        resp = self.client.get("/dashboard/checkout/start/")
        # Should redirect to YooKassa or subscription, but not be blocked by middleware
        if resp.status_code == 302:
            self.assertNotIn("/dashboard/subscription/", resp.url)


# 2.14  Full trial-to-paid upgrade flow

class TestTrialToPaidUpgrade(TestCase):

    def setUp(self):
        self.user = _create_user(email="upgrade@example.com")
        self.company = _create_company_with_owner(self.user, name="Upgrade Corp")

    def test_trial_to_start_upgrade(self):
        sub = create_trial_subscription(self.company)
        self.assertEqual(sub.plan, "trial")
        self.assertEqual(sub.max_employees, 200)

        # Upgrade to start
        sub = activate_subscription(self.company, "start")
        self.assertEqual(sub.plan, "start")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.max_employees, 10)
        expected = timezone.now() + timedelta(days=30)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)

    def test_trial_to_business_upgrade(self):
        sub = create_trial_subscription(self.company)
        sub = activate_subscription(self.company, "business")
        self.assertEqual(sub.plan, "business")
        self.assertEqual(sub.max_employees, 50)

    def test_trial_to_pro_upgrade(self):
        sub = create_trial_subscription(self.company)
        sub = activate_subscription(self.company, "pro")
        self.assertEqual(sub.plan, "pro")
        self.assertEqual(sub.max_employees, 200)

    def test_expired_trial_to_paid(self):
        """Expired trial can be upgraded to paid plan."""
        sub = create_trial_subscription(self.company)
        sub.status = Subscription.Status.EXPIRED
        sub.expires_at = timezone.now() - timedelta(days=1)
        sub.save()

        sub = activate_subscription(self.company, "business")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.plan, "business")
        self.assertTrue(sub.is_active)

    def test_trial_to_annual_upgrade(self):
        sub = create_trial_subscription(self.company)
        sub = activate_subscription(self.company, "start", billing_period="annual")
        self.assertEqual(sub.billing_period, "annual")
        expected = timezone.now() + timedelta(days=365)
        self.assertAlmostEqual(sub.expires_at.timestamp(), expected.timestamp(), delta=5)
