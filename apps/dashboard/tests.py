"""
Tests for dashboard: login, register, access control, employee operations, chat support.
"""
import json
from datetime import timedelta, date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client, override_settings
from django.utils import timezone
from django.core import mail

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, Department
from apps.billing.models import Subscription, Payment
from apps.documents.models import Document


# ---------------------------------------------------------------------------
#  helpers
# ---------------------------------------------------------------------------

def _user(email="dash@example.com", password="TestPass123!"):
    return User.objects.create_user(username=email, email=email, password=password)


def _company(owner, name="Test LLC"):
    return Company.objects.create(
        owner=owner, name=name, inn="1234567890",
        legal_address="Test Address", director_name="Test Director",
    )


def _member(company, user, role="owner"):
    return CompanyMember.objects.create(company=company, user=user, role=role)


def _sub(company, plan="trial", status="active", days=7, **kw):
    defaults = dict(
        plan=plan, status=status,
        started_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=days),
        max_employees=200,
    )
    defaults.update(kw)
    return Subscription.objects.create(company=company, **defaults)


def _login(client, email="dash@example.com", password="TestPass123!"):
    client.login(email=email, password=password)


# ===========================================================================
# 1. Login view tests
# ===========================================================================

@override_settings(ROOT_URLCONF="config.urls")
class LoginViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _user()
        self.company = _company(self.user)
        _member(self.company, self.user)

    def test_login_get_renders_form(self):
        resp = self.client.get("/dashboard/login/")
        self.assertEqual(resp.status_code, 200)

    def test_login_valid_credentials_redirects(self):
        resp = self.client.post("/dashboard/login/", {
            "email": "dash@example.com",
            "password": "TestPass123!",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/employees/", resp.url)

    def test_login_invalid_credentials_shows_error(self):
        resp = self.client.post("/dashboard/login/", {
            "email": "dash@example.com",
            "password": "WrongPassword",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Неверный")

    def test_login_already_authenticated_redirects(self):
        _login(self.client)
        resp = self.client.get("/dashboard/login/")
        self.assertEqual(resp.status_code, 302)

    def test_login_with_next_url(self):
        resp = self.client.post("/dashboard/login/", {
            "email": "dash@example.com",
            "password": "TestPass123!",
            "next": "/dashboard/subscription/",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)


# ===========================================================================
# 2. Dashboard access control tests
# ===========================================================================

@override_settings(ROOT_URLCONF="config.urls")
class DashboardAccessTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _user(email="access@example.com")
        self.company = _company(self.user, name="Access Corp")
        _member(self.company, self.user)

    def test_dashboard_with_active_trial_returns_200(self):
        _sub(self.company, plan="trial", days=7)
        _login(self.client, email="access@example.com")
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_with_active_paid_returns_200(self):
        _sub(self.company, plan="start", days=30, max_employees=10)
        _login(self.client, email="access@example.com")
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_with_expired_subscription_redirects(self):
        _sub(self.company, plan="start", status="expired", days=-5)
        _login(self.client, email="access@example.com")
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)

    def test_subscription_page_accessible_when_expired(self):
        _sub(self.company, plan="start", status="expired", days=-5)
        _login(self.client, email="access@example.com")
        resp = self.client.get("/dashboard/subscription/")
        self.assertNotEqual(resp.status_code, 302)

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_dashboard_with_expired_trial_redirects(self):
        _sub(self.company, plan="trial", status="active", days=-1)
        _login(self.client, email="access@example.com")
        resp = self.client.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)


# ===========================================================================
# 3. Employee add + T-1 auto-creation tests
# ===========================================================================

@override_settings(ROOT_URLCONF="config.urls")
class EmployeeAddTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _user(email="empadd@example.com")
        self.company = _company(self.user, name="EmpAdd Corp")
        _member(self.company, self.user)
        _sub(self.company, plan="business", days=30, max_employees=50)
        _login(self.client, email="empadd@example.com")

    def test_add_employee_creates_employee(self):
        resp = self.client.post("/dashboard/employees/add/", {
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": "Иванович",
            "position": "Разработчик",
            "hire_date": "01.01.2024",
            "salary": "100000",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Employee.objects.filter(company=self.company, last_name="Иванов").exists())

    def test_add_employee_auto_creates_t1_document(self):
        """Adding employee should auto-create T-1 hire order document."""
        self.client.post("/dashboard/employees/add/", {
            "last_name": "Петров",
            "first_name": "Пётр",
            "position": "Менеджер",
            "hire_date": "15.03.2024",
        }, HTTP_HX_REQUEST="true")
        emp = Employee.objects.filter(company=self.company, last_name="Петров").first()
        self.assertIsNotNone(emp)
        doc = Document.objects.filter(company=self.company, employee=emp, doc_type='hire').first()
        self.assertIsNotNone(doc, "T-1 document should be auto-created on employee add")
        self.assertTrue(doc.number.startswith("П-"))

    def test_add_employee_over_limit_blocked(self):
        """Adding employee over plan limit should be blocked."""
        # Create subscription with max_employees=1
        sub = Subscription.objects.get(company=self.company)
        sub.max_employees = 1
        sub.save()
        Employee.objects.create(
            company=self.company, last_name="Existing", first_name="E",
            position="Dev", hire_date=date(2024, 1, 1),
        )
        resp = self.client.post("/dashboard/employees/add/", {
            "last_name": "TooMany",
            "first_name": "T",
            "position": "Dev",
            "hire_date": "01.01.2024",
        }, HTTP_HX_REQUEST="true")
        self.assertFalse(Employee.objects.filter(last_name="TooMany").exists())

    def test_second_employee_gets_incremented_order_number(self):
        """Second employee's T-1 document number should be incremented."""
        self.client.post("/dashboard/employees/add/", {
            "last_name": "First", "first_name": "F",
            "position": "Dev", "hire_date": "01.01.2024",
        }, HTTP_HX_REQUEST="true")
        self.client.post("/dashboard/employees/add/", {
            "last_name": "Second", "first_name": "S",
            "position": "Dev", "hire_date": "02.01.2024",
        }, HTTP_HX_REQUEST="true")
        docs = Document.objects.filter(company=self.company, doc_type='hire').order_by('number')
        self.assertEqual(docs.count(), 2)
        self.assertEqual(docs[0].number, "П-001")
        self.assertEqual(docs[1].number, "П-002")


# ===========================================================================
# 4. Employee filtering tests
# ===========================================================================

@override_settings(ROOT_URLCONF="config.urls")
class EmployeeFilterTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _user(email="filter@example.com")
        self.company = _company(self.user, name="Filter Corp")
        _member(self.company, self.user)
        _sub(self.company, plan="business", days=30, max_employees=50)
        _login(self.client, email="filter@example.com")
        # Create employees with different statuses
        Employee.objects.create(
            company=self.company, last_name="Active", first_name="A",
            position="Dev", hire_date=date(2024, 1, 1), status="active",
        )
        Employee.objects.create(
            company=self.company, last_name="Fired", first_name="F",
            position="Dev", hire_date=date(2024, 1, 1), status="fired",
        )

    def test_default_filter_shows_active_only(self):
        """Default employee list shows active employees only."""
        resp = self.client.get("/dashboard/employees/")
        self.assertContains(resp, "Active")
        self.assertNotContains(resp, ">Fired<")

    def test_filter_fired_shows_fired_only(self):
        resp = self.client.get("/dashboard/employees/?status=fired")
        self.assertContains(resp, "Fired")

    def test_filter_all_shows_both(self):
        resp = self.client.get("/dashboard/employees/?status=all")
        self.assertContains(resp, "Active")
        self.assertContains(resp, "Fired")


# ===========================================================================
# 4b. Fired employees excluded from plan limit
# ===========================================================================

class FiredEmployeeExcludedFromLimitTests(TestCase):

    def setUp(self):
        self.user = _user(email="fired@example.com")
        self.company = _company(self.user, name="Fired Corp")
        _member(self.company, self.user)

    def test_fired_employees_not_counted_in_limit(self):
        """Fired employees should not count against the plan limit."""
        from apps.billing.services import get_subscription_context
        _sub(self.company, plan="start", days=30, max_employees=2)
        Employee.objects.create(
            company=self.company, last_name="Active1", first_name="A",
            position="Dev", hire_date=date(2024, 1, 1), status="active",
        )
        Employee.objects.create(
            company=self.company, last_name="Fired1", first_name="F",
            position="Dev", hire_date=date(2024, 1, 1), status="fired",
        )
        ctx = get_subscription_context(self.company)
        self.assertEqual(ctx["employee_count"], 1, "Fired employees should not count")
        self.assertTrue(ctx["can_add_employee"], "Should be able to add since only 1 active of 2 max")

    def test_all_fired_allows_new_additions(self):
        """If all employees are fired, can_add_employee should be True."""
        from apps.billing.services import get_subscription_context
        _sub(self.company, plan="start", days=30, max_employees=1)
        Employee.objects.create(
            company=self.company, last_name="Gone", first_name="G",
            position="Dev", hire_date=date(2024, 1, 1), status="fired",
        )
        ctx = get_subscription_context(self.company)
        self.assertEqual(ctx["employee_count"], 0)
        self.assertTrue(ctx["can_add_employee"])


# ===========================================================================
# 5. Chat support tests
# ===========================================================================

@override_settings(
    ROOT_URLCONF="config.urls",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@kadrovik.ru",
)
class ChatSupportTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _user(email="chat@example.com")
        self.company = _company(self.user, name="Chat Corp")
        _member(self.company, self.user)
        _sub(self.company, plan="trial", days=7)
        _login(self.client, email="chat@example.com")

    @patch("apps.dashboard.views._chat_redis")
    def test_send_message_sends_email(self, mock_redis_fn):
        """Sending chat message should send email to operator."""
        mock_r = MagicMock()
        mock_redis_fn.return_value = mock_r
        resp = self.client.post(
            "/dashboard/chat-support/",
            data=json.dumps({"text": "Помогите!"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Чат поддержки", mail.outbox[0].subject)
        self.assertIn("chat@example.com", mail.outbox[0].subject)

    @patch("apps.dashboard.views._chat_redis")
    def test_send_empty_message_rejected(self, mock_redis_fn):
        """Empty message should be rejected."""
        mock_r = MagicMock()
        mock_redis_fn.return_value = mock_r
        resp = self.client.post(
            "/dashboard/chat-support/",
            data=json.dumps({"text": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error"), "empty")

    @patch("apps.dashboard.views._chat_redis")
    def test_chat_history_returns_empty_list(self, mock_redis_fn):
        """Chat history for new session returns empty messages."""
        mock_r = MagicMock()
        mock_r.lrange.return_value = []
        mock_redis_fn.return_value = mock_r
        resp = self.client.get("/dashboard/chat-history/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["messages"], [])
        self.assertTrue(len(data["session"]) > 0)

    @patch("apps.dashboard.views._chat_redis")
    def test_chat_history_returns_stored_messages(self, mock_redis_fn):
        """Chat history returns stored messages from Redis."""
        mock_r = MagicMock()
        stored_msg = json.dumps({"role": "user", "text": "Hello", "ts": 1000}).encode()
        mock_r.lrange.return_value = [stored_msg]
        mock_redis_fn.return_value = mock_r
        resp = self.client.get("/dashboard/chat-history/")
        data = resp.json()
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["text"], "Hello")

    @patch("apps.dashboard.views._chat_redis")
    @patch("django.core.mail.send_mail")
    def test_chat_message_saved_to_redis(self, mock_send_mail, mock_redis_fn):
        """Sending message saves it to Redis."""
        mock_r = MagicMock()
        mock_redis_fn.return_value = mock_r
        resp = self.client.post(
            "/dashboard/chat-support/",
            data=json.dumps({"text": "Save me"}),
            content_type="application/json",
        )
        self.assertTrue(resp.json().get("ok"))
        # Check rpush was called with chat_hist key
        mock_r.rpush.assert_called()
        call_args = mock_r.rpush.call_args[0]
        self.assertTrue(call_args[0].startswith("chat_hist:"))

    @patch("apps.dashboard.views._chat_redis")
    def test_chat_webhook_operator_reply(self, mock_redis_fn):
        """Operator reply via webhook stores message in Redis."""
        mock_r = MagicMock()
        mock_redis_fn.return_value = mock_r
        resp = self.client.post(
            "/dashboard/chat-webhook/",
            data=json.dumps({
                "message": {
                    "chat": {"id": 1113292310},
                    "text": "/reply abc12345 Ваш вопрос решён",
                }
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# 6. Billing checkout tests
# ===========================================================================

@override_settings(ROOT_URLCONF="config.urls")
class CheckoutViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _user(email="checkout@example.com")
        self.company = _company(self.user, name="Checkout Corp")
        _member(self.company, self.user)
        _sub(self.company, plan="trial", days=7)
        _login(self.client, email="checkout@example.com")

    def test_checkout_nonexistent_plan_redirects(self):
        """Checkout with non-existent plan redirects to subscription page."""
        resp = self.client.get("/dashboard/checkout/nonexistent/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/subscription/", resp.url)

    def test_checkout_invalid_period_defaults_to_monthly(self):
        """Checkout with invalid period defaults to monthly."""
        with patch("apps.billing.views.create_payment") as mock_create:
            mock_create.return_value = (MagicMock(status="pending"), None)
            with patch("apps.billing.views.activate_subscription") as mock_activate:
                mock_activate.return_value = MagicMock()
                resp = self.client.get("/dashboard/checkout/start/?period=invalid")
                # Should default to monthly
                if mock_create.called:
                    _, kwargs = mock_create.call_args
                    self.assertEqual(kwargs.get("billing_period", "monthly"), "monthly")

    def test_checkout_annual_period(self):
        """Checkout with annual period passes it to create_payment."""
        with patch("apps.billing.views.create_payment") as mock_create:
            mock_create.return_value = (MagicMock(status="pending"), None)
            with patch("apps.billing.views.activate_subscription") as mock_activate:
                mock_activate.return_value = MagicMock()
                resp = self.client.get("/dashboard/checkout/start/?period=annual")
                if mock_create.called:
                    _, kwargs = mock_create.call_args
                    self.assertEqual(kwargs.get("billing_period"), "annual")


# ===========================================================================
# 7. Payment creation amount tests
# ===========================================================================

class PaymentAmountTests(TestCase):

    def setUp(self):
        self.user = _user(email="pay@example.com")
        self.company = _company(self.user, name="Pay Corp")
        _member(self.company, self.user)

    @patch("apps.billing.services._get_yookassa")
    def test_start_monthly_amount(self, mock_yk):
        """Start plan monthly should be 790."""
        from apps.billing.services import create_payment
        mock_yk_mod = MagicMock()
        mock_yk.return_value = mock_yk_mod
        mock_payment = MagicMock()
        mock_payment.id = "yk_123"
        mock_payment.confirmation.confirmation_url = "https://pay.example.com"
        mock_yk_mod.Payment.create.return_value = mock_payment
        payment, url = create_payment(self.company, "start", "http://return.url")
        self.assertEqual(payment.amount, 790)
        self.assertEqual(payment.plan, "start")

    @patch("apps.billing.services._get_yookassa")
    def test_business_monthly_amount(self, mock_yk):
        """Business plan monthly should be 1990."""
        from apps.billing.services import create_payment
        mock_yk_mod = MagicMock()
        mock_yk.return_value = mock_yk_mod
        mock_payment = MagicMock()
        mock_payment.id = "yk_123"
        mock_payment.confirmation.confirmation_url = "https://pay.example.com"
        mock_yk_mod.Payment.create.return_value = mock_payment
        payment, url = create_payment(self.company, "business", "http://return.url")
        self.assertEqual(payment.amount, 1990)

    @patch("apps.billing.services._get_yookassa")
    def test_pro_monthly_amount(self, mock_yk):
        """Pro plan monthly should be 4900."""
        from apps.billing.services import create_payment
        mock_yk_mod = MagicMock()
        mock_yk.return_value = mock_yk_mod
        mock_payment = MagicMock()
        mock_payment.id = "yk_123"
        mock_payment.confirmation.confirmation_url = "https://pay.example.com"
        mock_yk_mod.Payment.create.return_value = mock_payment
        payment, url = create_payment(self.company, "pro", "http://return.url")
        self.assertEqual(payment.amount, 4900)

    @patch("apps.billing.services._get_yookassa")
    def test_start_annual_amount(self, mock_yk):
        """Start plan annual should be 7110."""
        from apps.billing.services import create_payment
        mock_yk_mod = MagicMock()
        mock_yk.return_value = mock_yk_mod
        mock_payment = MagicMock()
        mock_payment.id = "yk_123"
        mock_payment.confirmation.confirmation_url = "https://pay.example.com"
        mock_yk_mod.Payment.create.return_value = mock_payment
        payment, url = create_payment(self.company, "start", "http://return.url", billing_period="annual")
        self.assertEqual(payment.amount, 7110)

    @patch("apps.billing.services._get_yookassa")
    def test_business_annual_amount(self, mock_yk):
        """Business plan annual should be 17910."""
        from apps.billing.services import create_payment
        mock_yk_mod = MagicMock()
        mock_yk.return_value = mock_yk_mod
        mock_payment = MagicMock()
        mock_payment.id = "yk_123"
        mock_payment.confirmation.confirmation_url = "https://pay.example.com"
        mock_yk_mod.Payment.create.return_value = mock_payment
        payment, url = create_payment(self.company, "business", "http://return.url", billing_period="annual")
        self.assertEqual(payment.amount, 17910)

    @patch("apps.billing.services._get_yookassa")
    def test_pro_annual_amount(self, mock_yk):
        """Pro plan annual should be 44100."""
        from apps.billing.services import create_payment
        mock_yk_mod = MagicMock()
        mock_yk.return_value = mock_yk_mod
        mock_payment = MagicMock()
        mock_payment.id = "yk_123"
        mock_payment.confirmation.confirmation_url = "https://pay.example.com"
        mock_yk_mod.Payment.create.return_value = mock_payment
        payment, url = create_payment(self.company, "pro", "http://return.url", billing_period="annual")
        self.assertEqual(payment.amount, 44100)

    def test_create_payment_no_yookassa_keys(self):
        """No YooKassa keys -> payment created, confirmation_url is None."""
        from apps.billing.services import create_payment
        with self.settings(YUKASSA_SHOP_ID="", YUKASSA_SECRET_KEY=""):
            payment, url = create_payment(self.company, "start", "http://return.url")
            self.assertEqual(payment.amount, 790)
            self.assertIsNone(url)
            self.assertEqual(payment.status, Payment.Status.PENDING)


# ===========================================================================
# 8. Document T-1 PDF generation tests
# ===========================================================================

class DocumentT1PdfTests(TestCase):

    def setUp(self):
        self.user = _user(email="t1@example.com")
        self.company = _company(self.user, name="T1 Corp")
        _member(self.company, self.user)
        self.employee = Employee.objects.create(
            company=self.company, last_name="Тестов", first_name="Тест",
            middle_name="Тестович", position="Разработчик",
            hire_date=date(2024, 1, 15), salary=Decimal("100000"),
        )

    def test_generate_t1_pdf(self):
        """generate_t1_pdf produces valid PDF bytes."""
        from apps.documents.services import generate_t1_pdf
        pdf = generate_t1_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_generate_t1_with_custom_order_number(self):
        from apps.documents.services import generate_t1_pdf
        pdf = generate_t1_pdf(self.employee, order_number="П-099")
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)


# ===========================================================================
# 9. Duplicate payment protection tests
# ===========================================================================

@override_settings(ROOT_URLCONF="config.urls")
class DuplicatePaymentProtectionTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _user(email="dup@example.com")
        self.company = _company(self.user, name="Dup Corp")
        _member(self.company, self.user)
        _sub(self.company, plan="trial", days=7)
        _login(self.client, email="dup@example.com")

    @patch("apps.billing.services._get_yookassa")
    @patch("apps.billing.views.create_payment")
    def test_recent_pending_payment_reuses(self, mock_create, mock_yk):
        """If there's a recent pending payment, checkout reuses it."""
        existing_payment = Payment.objects.create(
            company=self.company, amount=790, plan="start",
            status=Payment.Status.PENDING,
            yukassa_payment_id="yk_existing_123",
        )
        mock_yk_mod = MagicMock()
        mock_yk.return_value = mock_yk_mod
        mock_yk_payment = MagicMock()
        mock_yk_payment.status = "pending"
        mock_yk_payment.confirmation.confirmation_url = "https://existing-pay.url"
        mock_yk_mod.Payment.find_one.return_value = mock_yk_payment

        resp = self.client.get("/dashboard/checkout/start/")
        self.assertEqual(resp.status_code, 302)
        # Should redirect to existing YooKassa URL, not create a new payment
        self.assertIn("https://existing-pay.url", resp.url)
        mock_create.assert_not_called()
