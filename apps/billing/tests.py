"""
Comprehensive billing tests for Kadrovik billing module.
Covers: models, middleware, decorator, services, Celery tasks, employee limits.
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
    get_subscription_context,
    PLANS,
)
from apps.billing.middleware import SubscriptionMiddleware
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, Department

User = get_user_model()


# ─── helpers ────────────────────────────────────────────────────────────────

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
        expires_at=timezone.now() + timedelta(days=14),
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
    """Attach session and messages middleware to a RequestFactory request."""
    sm = SessionMiddleware(lambda r: None)
    sm.process_request(request)
    request.session.save()
    mm = MessageMiddleware(lambda r: None)
    mm.process_request(request)


# ═══════════════════════════════════════════════════════════════════════════
# 2.1  Model tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSubscriptionModel(TestCase):

    def setUp(self):
        self.user = _create_user()
        self.company = _create_company_with_owner(self.user)

    # ── is_active ──────────────────────────────────────────────────────────

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

    # ── is_trial helpers (plan-based) ──────────────────────────────────────

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

    # ── data_deletion fields exist ─────────────────────────────────────────

    def test_data_deletion_fields(self):
        sub = _create_subscription(self.company)
        self.assertTrue(
            hasattr(sub, "data_deletion_scheduled_at"),
            "Subscription must have data_deletion_scheduled_at field",
        )
        self.assertTrue(
            hasattr(sub, "data_cleaned"),
            "Subscription must have data_cleaned field",
        )
        self.assertIsNone(sub.data_deletion_scheduled_at)
        self.assertFalse(sub.data_cleaned)


# ═══════════════════════════════════════════════════════════════════════════
# 2.2  Middleware tests
# ═══════════════════════════════════════════════════════════════════════════

@override_settings(ROOT_URLCONF="config.urls")
class TestSubscriptionMiddleware(TestCase):

    def setUp(self):
        self.user = _create_user(email="mw@example.com")
        self.user.set_password("testpass123")
        self.user.save()
        self.company = _create_company_with_owner(self.user, name="MW Corp")
        self.client = Client()
        self.client.login(email="mw@example.com", password="testpass123")

    # ── exempt paths ───────────────────────────────────────────────────────

    def test_exempt_paths_not_blocked(self):
        """Billing and login pages must NOT redirect to /dashboard/subscription/."""
        # Make subscription expired
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        for path in ["/dashboard/login/", "/dashboard/subscription/"]:
            resp = self.client.get(path)
            # These exempt paths may redirect (e.g. login redirects logged-in user)
            # but they must NEVER redirect to /dashboard/subscription/ due to expired sub
            if resp.status_code == 302:
                self.assertNotIn(
                    "/dashboard/subscription/",
                    resp.url,
                    f"{path} should not redirect to subscription page",
                ) if "subscription" not in path else None

    def test_employees_blocked_without_subscription(self):
        """/dashboard/employees/ must redirect to subscription page when expired."""
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)

    def test_dashboard_accessible_with_active_subscription(self):
        """/dashboard/ should not redirect to subscription when subscription is active."""
        _create_subscription(
            self.company,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
        )
        resp = self.client.get("/dashboard/employees/")
        # Should be 200 or redirect to something OTHER than /subscription/
        if resp.status_code == 302:
            self.assertNotIn("/dashboard/subscription/", resp.url)

    def test_ajax_returns_402(self):
        """AJAX request to a protected path returns 402 JSON when subscription expired."""
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


# ═══════════════════════════════════════════════════════════════════════════
# 2.3  subscription_required decorator tests
# ═══════════════════════════════════════════════════════════════════════════

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
        """POST /dashboard/employees/add/ should redirect when subscription expired."""
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        resp = self.client.post("/dashboard/employees/add/")
        # subscription_required redirects to subscription page
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)

    def test_employee_delete_blocked(self):
        """POST /dashboard/employees/<id>/delete/ should redirect when subscription expired."""
        _create_subscription(
            self.company,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=5),
        )
        # Create an employee to have a valid ID
        emp = Employee.objects.create(
            company=self.company,
            first_name="Test",
            last_name="User",
            position="Dev",
            hire_date=timezone.now().date(),
        )
        resp = self.client.post(f"/dashboard/employees/{emp.id}/delete/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)


# ═══════════════════════════════════════════════════════════════════════════
# 2.4  Services tests
# ═══════════════════════════════════════════════════════════════════════════

class TestBillingServices(TestCase):

    def setUp(self):
        self.user = _create_user(email="svc@example.com")
        self.company = _create_company_with_owner(self.user, name="Svc Corp")

    def test_activate_subscription_monthly(self):
        """activate_subscription with monthly start plan sets +30 days, status=active."""
        sub = activate_subscription(self.company, "start", billing_period="monthly")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.plan, "start")
        # Monthly "start" plan has months=1, so +30 days
        expected = timezone.now() + timedelta(days=30)
        self.assertAlmostEqual(
            sub.expires_at.timestamp(),
            expected.timestamp(),
            delta=5,
        )

    def test_activate_subscription_annual(self):
        """activate_subscription with annual sets +365 days."""
        sub = activate_subscription(self.company, "business", billing_period="annual")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        expected = timezone.now() + timedelta(days=365)
        self.assertAlmostEqual(
            sub.expires_at.timestamp(),
            expected.timestamp(),
            delta=5,
        )

    def test_activate_subscription_resets_grace_period(self):
        """Reactivating subscription must reset data_deletion_scheduled_at and data_cleaned."""
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

    def test_get_subscription_context_trial(self):
        """Context for trial plan should have correct limits and features."""
        _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            max_employees=200,
        )
        ctx = get_subscription_context(self.company)
        self.assertEqual(ctx["plan_key"], "trial")
        self.assertEqual(ctx["max_employees"], 200)
        self.assertTrue(ctx["plan_features"]["documents"])
        self.assertTrue(ctx["plan_features"]["telegram"])
        self.assertTrue(ctx["plan_features"]["export_excel"])

    def test_get_subscription_context_paid(self):
        """Context for paid (business) plan should have correct max_employees."""
        _create_subscription(
            self.company,
            plan=Subscription.Plan.BUSINESS,
            max_employees=50,
        )
        ctx = get_subscription_context(self.company)
        self.assertEqual(ctx["plan_key"], "business")
        self.assertEqual(ctx["max_employees"], 50)
        self.assertTrue(ctx["plan_features"]["export_excel"])


# ═══════════════════════════════════════════════════════════════════════════
# 2.5  Celery task tests
# ═══════════════════════════════════════════════════════════════════════════

class TestBillingTasks(TestCase):

    def setUp(self):
        self.user = _create_user(email="task@example.com")
        self.company = _create_company_with_owner(self.user, name="Task Corp")

    def test_check_expired_subscriptions_marks_paid_expired(self):
        """Paid subscription past expires_at is marked expired with grace period +30 days."""
        from apps.billing.tasks import check_expired_subscriptions

        expires = timezone.now() - timedelta(days=2)
        sub = _create_subscription(
            self.company,
            plan=Subscription.Plan.START,
            status=Subscription.Status.ACTIVE,
            expires_at=expires,
        )
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertIsNotNone(sub.data_deletion_scheduled_at)
        expected_deletion = expires + timedelta(days=30)
        self.assertAlmostEqual(
            sub.data_deletion_scheduled_at.timestamp(),
            expected_deletion.timestamp(),
            delta=5,
        )

    def test_check_expired_subscriptions_trial_no_deletion_date(self):
        """Trial subscription on expiry must NOT get data_deletion_scheduled_at."""
        from apps.billing.tasks import check_expired_subscriptions

        sub = _create_subscription(
            self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(days=1),
        )
        check_expired_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertIsNone(sub.data_deletion_scheduled_at)

    def test_cleanup_deletes_employee_data(self):
        """After grace period, employees are deleted but Company and User remain."""
        from apps.billing.tasks import cleanup_expired_company_data

        sub = _create_subscription(
            self.company,
            plan=Subscription.Plan.START,
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=35),
            data_deletion_scheduled_at=timezone.now() - timedelta(days=1),
        )
        sub.data_cleaned = False
        sub.save()

        # Create employees to be deleted
        Employee.objects.create(
            company=self.company,
            first_name="Alice",
            last_name="Smith",
            position="Dev",
            hire_date=timezone.now().date(),
        )
        Employee.objects.create(
            company=self.company,
            first_name="Bob",
            last_name="Jones",
            position="QA",
            hire_date=timezone.now().date(),
        )
        self.assertEqual(Employee.objects.filter(company=self.company).count(), 2)

        cleanup_expired_company_data()

        # Employees should be deleted
        self.assertEqual(Employee.objects.filter(company=self.company).count(), 0)
        # Company and User must remain
        self.assertTrue(Company.objects.filter(id=self.company.id).exists())
        self.assertTrue(User.objects.filter(id=self.user.id).exists())
        # data_cleaned should be True
        sub.refresh_from_db()
        self.assertTrue(sub.data_cleaned)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_send_expiry_warnings_7days(self):
        """Email is sent when data deletion is ~7 days away."""
        from apps.billing.tasks import send_expiry_warnings

        self.user.email = "owner@example.com"
        self.user.save()

        sub = _create_subscription(
            self.company,
            plan=Subscription.Plan.START,
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
        """Email is sent when data deletion is ~1 day away."""
        from apps.billing.tasks import send_expiry_warnings

        self.user.email = "owner@example.com"
        self.user.save()

        sub = _create_subscription(
            self.company,
            plan=Subscription.Plan.START,
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


# ═══════════════════════════════════════════════════════════════════════════
# 2.6  Employee limit tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEmployeeLimits(TestCase):

    def setUp(self):
        self.user = _create_user(email="limit@example.com")
        self.company = _create_company_with_owner(self.user, name="Limit Corp")

    def test_cannot_add_employee_over_limit(self):
        """When max_employees is reached, can_add_employee must be False."""
        _create_subscription(
            self.company,
            plan=Subscription.Plan.START,
            max_employees=2,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
        )
        Employee.objects.create(
            company=self.company,
            first_name="A",
            last_name="One",
            position="Dev",
            hire_date=timezone.now().date(),
        )
        Employee.objects.create(
            company=self.company,
            first_name="B",
            last_name="Two",
            position="Dev",
            hire_date=timezone.now().date(),
        )
        ctx = get_subscription_context(self.company)
        self.assertFalse(ctx["can_add_employee"])
        self.assertEqual(ctx["employee_count"], 2)
        self.assertEqual(ctx["max_employees"], 2)

    def test_can_add_employee_within_limit(self):
        """Adding is allowed when employee count is below max_employees."""
        _create_subscription(
            self.company,
            plan=Subscription.Plan.BUSINESS,
            max_employees=50,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
        )
        Employee.objects.create(
            company=self.company,
            first_name="C",
            last_name="Three",
            position="Dev",
            hire_date=timezone.now().date(),
        )
        ctx = get_subscription_context(self.company)
        self.assertTrue(ctx["can_add_employee"])
        self.assertEqual(ctx["employee_count"], 1)
        self.assertEqual(ctx["max_employees"], 50)
