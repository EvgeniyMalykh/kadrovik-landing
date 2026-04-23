"""
Part 7 tests: registration, email verification, auto-create hire document,
_next_doc_number, register_view edge cases.
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
from apps.employees.models import Employee, Department
from apps.billing.models import Subscription
from apps.documents.models import Document


# ---------------------------------------------------------------------------
#  helpers
# ---------------------------------------------------------------------------

def _create_user(email="test7@example.com", password="TestPass123!"):
    return User.objects.create_user(
        username=email, email=email, password=password,
    )


def _create_company(owner, name="ООО Тест7", inn="1234567890"):
    return Company.objects.create(
        owner=owner, name=name, inn=inn,
        ogrn="1234567890123",
        legal_address="г. Москва, ул. Тестовая, д.7",
        director_name="Директоров Д.Д.",
    )


def _create_membership(user, company, role="owner"):
    return CompanyMember.objects.create(company=company, user=user, role=role)


def _create_subscription(company, plan="trial"):
    return Subscription.objects.create(
        company=company, plan=plan,
        status=Subscription.Status.ACTIVE,
        expires_at=timezone.now() + timedelta(days=30),
        max_employees=50,
    )


def _create_employee(company, last_name="Тестов", first_name="Тест",
                     position="Тестировщик"):
    return Employee.objects.create(
        company=company, last_name=last_name, first_name=first_name,
        middle_name="Тестович", position=position,
        hire_date=date.today(), salary=Decimal("50000"),
    )


# ===========================================================================
# 1. register_view
# ===========================================================================

@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class RegisterViewTests(TestCase):

    def setUp(self):
        self.client = Client()

    def test_register_get(self):
        """GET /dashboard/register/ returns 200."""
        resp = self.client.get(reverse("dashboard:register"))
        self.assertEqual(resp.status_code, 200)

    def test_register_post_valid(self):
        """POST with valid data → saves to Redis, sends email, shows email_sent page."""
        mock_redis = MagicMock()
        with patch("redis.from_url", return_value=mock_redis), \
             patch("apps.accounts.tasks.send_verification_email_pending.delay"):
            resp = self.client.post(reverse("dashboard:register"), {
                "email": "new@example.com",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "company_name": "ООО Новая",
                "telegram": "@new_user",
                "employee_count": "5",
            })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "new@example.com")
        # Redis setex was called
        mock_redis.setex.assert_called_once()
        key, ttl, data_str = mock_redis.setex.call_args[0]
        self.assertTrue(key.startswith("pending_registration:"))
        self.assertEqual(ttl, 86400)
        data = json.loads(data_str)
        self.assertEqual(data["email"], "new@example.com")
        self.assertEqual(data["company_name"], "ООО Новая")
        self.assertEqual(data["employee_count"], 5)

    def test_register_post_password_mismatch(self):
        """POST with mismatched passwords → error message."""
        resp = self.client.post(reverse("dashboard:register"), {
            "email": "new@example.com",
            "password": "StrongPass123!",
            "password2": "DifferentPass!",
            "company_name": "ООО Новая",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Пароли не совпадают")

    def test_register_post_existing_email(self):
        """POST with existing email → error message."""
        _create_user(email="existing@example.com")
        resp = self.client.post(reverse("dashboard:register"), {
            "email": "existing@example.com",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
            "company_name": "ООО Дубль",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Email уже зарегистрирован")

    def test_register_post_empty_fields(self):
        """POST with empty required fields → error message."""
        resp = self.client.post(reverse("dashboard:register"), {
            "email": "",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
            "company_name": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Заполните все поля")

    def test_register_post_saves_employee_count_in_redis(self):
        """POST saves employee_count in Redis pending data."""
        mock_redis = MagicMock()
        with patch("redis.from_url", return_value=mock_redis), \
             patch("apps.accounts.tasks.send_verification_email_pending.delay"):
            self.client.post(reverse("dashboard:register"), {
                "email": "count@example.com",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "company_name": "ООО Счёт",
                "employee_count": "25",
            })
        data_str = mock_redis.setex.call_args[0][2]
        data = json.loads(data_str)
        self.assertEqual(data["employee_count"], 25)

    def test_register_authenticated_redirects(self):
        """Authenticated user → redirect to employees."""
        user = _create_user()
        company = _create_company(user)
        _create_membership(user, company)
        _create_subscription(company)
        self.client.login(email="test7@example.com", password="TestPass123!")
        resp = self.client.get(reverse("dashboard:register"))
        self.assertEqual(resp.status_code, 302)


# ===========================================================================
# 2. verify_email_view
# ===========================================================================

@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class VerifyEmailViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        import uuid
        self.test_uuid = str(uuid.uuid4())

    def _mock_redis_with_data(self, data):
        """Returns a mock Redis with pipeline that returns data atomically."""
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [json.dumps(data).encode(), 1]
        mock_redis.pipeline.return_value = mock_pipe
        return mock_redis

    def _mock_redis_empty(self):
        """Returns a mock Redis with pipeline that returns no data."""
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [None, 0]
        mock_redis.pipeline.return_value = mock_pipe
        return mock_redis

    @patch("apps.accounts.tasks.notify_new_registration.delay")
    def test_valid_token_creates_user(self, mock_notify):
        """Valid token → creates user, company, subscription, logs in."""
        from django.contrib.auth.hashers import make_password
        data = {
            "email": "verified@example.com",
            "password_hash": make_password("TestPass123!"),
            "company_name": "ООО Верифицировано",
            "telegram": "@verified",
            "employee_count": 10,
            "expires_at": (timezone.now() + timedelta(hours=24)).isoformat(),
        }
        mock_redis = self._mock_redis_with_data(data)
        with patch("redis.from_url", return_value=mock_redis):
            resp = self.client.get(f"/dashboard/verify-email/{self.test_uuid}/")
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(email="verified@example.com")
        self.assertTrue(user.email_verified)
        self.assertTrue(Company.objects.filter(owner=user).exists())
        self.assertTrue(CompanyMember.objects.filter(user=user, role="owner").exists())
        sub = Subscription.objects.get(company__owner=user)
        self.assertEqual(sub.plan, Subscription.Plan.TRIAL)

    def test_invalid_token_shows_error(self):
        """Invalid/expired token → error message."""
        mock_redis = self._mock_redis_empty()
        with patch("redis.from_url", return_value=mock_redis):
            resp = self.client.get(f"/dashboard/verify-email/{self.test_uuid}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "недействительна")

    @patch("apps.accounts.tasks.notify_new_registration.delay")
    def test_duplicate_email_rejected(self, mock_notify):
        """If email already registered → error, no duplicate user."""
        _create_user(email="dup@example.com")
        data = {
            "email": "dup@example.com",
            "password_hash": "fakehash",
            "company_name": "DupCo",
            "expires_at": (timezone.now() + timedelta(hours=24)).isoformat(),
        }
        mock_redis = self._mock_redis_with_data(data)
        with patch("redis.from_url", return_value=mock_redis):
            resp = self.client.get(f"/dashboard/verify-email/{self.test_uuid}/")
        self.assertContains(resp, "Email уже зарегистрирован")
        self.assertEqual(User.objects.filter(email="dup@example.com").count(), 1)


# ===========================================================================
# 3. Auto-create T-1 hire document
# ===========================================================================

@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class AutoCreateHireDocumentTests(TestCase):

    def setUp(self):
        self.user = _create_user("hire@example.com")
        self.company = _create_company(self.user, name="ООО Приказ")
        self.member = _create_membership(self.user, self.company)
        _create_subscription(self.company)
        self.client_inst = Client()
        self.client_inst.login(email="hire@example.com", password="TestPass123!")

    def test_employee_add_auto_creates_hire_document(self):
        """Adding employee auto-creates T-1 hire document."""
        emp = _create_employee(self.company)
        from apps.dashboard.views import _auto_create_hire_document
        doc = _auto_create_hire_document(self.member, emp)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.doc_type, 'hire')
        self.assertEqual(doc.employee, emp)
        self.assertTrue(doc.number.startswith('П-'))

    def test_hire_document_has_correct_number(self):
        """Sequential numbering: П-001, П-002..."""
        emp1 = _create_employee(self.company, last_name="Первый")
        emp2 = _create_employee(self.company, last_name="Второй")
        from apps.dashboard.views import _auto_create_hire_document
        doc1 = _auto_create_hire_document(self.member, emp1)
        doc2 = _auto_create_hire_document(self.member, emp2)
        self.assertEqual(doc1.number, "П-001")
        self.assertEqual(doc2.number, "П-002")

    def test_no_duplicate_on_edit(self):
        """Editing employee does NOT create second hire document."""
        emp = _create_employee(self.company)
        from apps.dashboard.views import _auto_create_hire_document
        doc1 = _auto_create_hire_document(self.member, emp)
        doc2 = _auto_create_hire_document(self.member, emp)
        # get_or_create → same document returned, only 1 in DB
        self.assertEqual(doc1.id, doc2.id)
        self.assertEqual(
            Document.objects.filter(employee=emp, doc_type='hire').count(), 1,
        )


# ===========================================================================
# 4. _next_doc_number
# ===========================================================================

class NextDocNumberTests(TestCase):

    def setUp(self):
        self.user = _create_user("num@example.com")
        self.company = _create_company(self.user, name="ООО Нумерация")
        _create_membership(self.user, self.company)
        _create_subscription(self.company)

    def test_first_number(self):
        """No existing docs → returns prefix-1."""
        from apps.dashboard.views import _next_doc_number
        num = _next_doc_number(self.company, "vacation")
        self.assertEqual(num, "О-1")

    def test_sequential_numbering(self):
        """Existing docs → increments max number."""
        emp = _create_employee(self.company)
        Document.objects.create(
            company=self.company, employee=emp, doc_type='vacation',
            number='О-3', date=date.today(),
        )
        Document.objects.create(
            company=self.company, employee=emp, doc_type='vacation',
            number='О-1', date=date.today(),
        )
        from apps.dashboard.views import _next_doc_number
        num = _next_doc_number(self.company, "vacation")
        self.assertEqual(num, "О-4")

    def test_prefixes(self):
        """Different doc types use correct prefixes."""
        from apps.dashboard.views import _next_doc_number
        self.assertTrue(_next_doc_number(self.company, "gph_contract").startswith("ГПХ-"))
        self.assertTrue(_next_doc_number(self.company, "transfer").startswith("ПР-"))
        self.assertTrue(_next_doc_number(self.company, "bonus").startswith("П-"))
        self.assertTrue(_next_doc_number(self.company, "disciplinary").startswith("ДВ-"))

    def test_unknown_doc_type(self):
        """Unknown doc type → default prefix Д-."""
        from apps.dashboard.views import _next_doc_number
        num = _next_doc_number(self.company, "unknown_type")
        self.assertEqual(num, "Д-1")


# ===========================================================================
# 5. Middleware AJAX/API handling for expired subscription
# ===========================================================================

@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class MiddlewareAjaxTests(TestCase):

    def setUp(self):
        self.user = _create_user("mw@example.com")
        self.company = _create_company(self.user, name="ООО Middleware")
        _create_membership(self.user, self.company)
        self.sub = Subscription.objects.create(
            company=self.company,
            plan=Subscription.Plan.TRIAL,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(days=1),  # expired
            max_employees=50,
        )
        self.client_inst = Client()
        self.client_inst.login(email="mw@example.com", password="TestPass123!")

    def test_expired_sub_redirects_html(self):
        """Expired subscription + regular HTML request → redirect to subscription page."""
        resp = self.client_inst.get("/dashboard/employees/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("subscription", resp.url)

    def test_expired_sub_returns_json_for_ajax(self):
        """Expired subscription + AJAX request → JSON 402 response."""
        resp = self.client_inst.get(
            "/dashboard/employees/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 402)
        data = resp.json()
        self.assertEqual(data["error"], "subscription_expired")

    def test_expired_sub_returns_json_for_htmx(self):
        """Expired subscription + HTMX request → JSON 402 response."""
        resp = self.client_inst.get(
            "/dashboard/employees/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 402)
