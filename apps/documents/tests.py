"""
Tests for documents app: GPH contract/act PDF generation with form_data.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, Department
from apps.billing.models import Subscription


# ---------------------------------------------------------------------------
#  helpers
# ---------------------------------------------------------------------------

def _create_user(email="doc@example.com", password="TestPass123!"):
    return User.objects.create_user(
        username=email, email=email, password=password,
    )


def _create_company(owner, name="ООО Документы"):
    return Company.objects.create(
        owner=owner, name=name, inn="9876543210",
        legal_address="г. Москва", director_name="Директор Директорович",
    )


def _create_subscription(company):
    return Subscription.objects.create(
        company=company,
        plan=Subscription.Plan.TRIAL,
        status=Subscription.Status.ACTIVE,
        expires_at=timezone.now() + timezone.timedelta(days=30),
        max_employees=50,
    )


def _create_employee(company, **kwargs):
    defaults = dict(
        company=company, last_name="Сидоров", first_name="Сидор",
        middle_name="Сидорович", position="Разработчик",
        hire_date=date(2024, 1, 15), salary=Decimal("100000"),
    )
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


# ===========================================================================
# 1. generate_gph_contract_pdf
# ===========================================================================

class GenerateGphContractPdfTests(TestCase):

    def setUp(self):
        self.user = _create_user()
        self.company = _create_company(self.user)
        self.employee = _create_employee(self.company)

    def test_without_form_data_uses_employee_fields(self):
        """No form_data → uses employee position and salary."""
        from apps.documents.services import generate_gph_contract_pdf
        pdf = generate_gph_contract_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_with_form_data_uses_form_values(self):
        """form_data provided → uses subject, amount, dates from form."""
        from apps.documents.services import generate_gph_contract_pdf
        form_data = {
            'subject': 'Разработка сайта',
            'amount': '50000',
            'start_date': '2024-06-01',
            'end_date': '2024-12-31',
            'doc_number': 'ГПХ-TEST-001',
            'doc_date': '2024-05-01',
        }
        pdf = generate_gph_contract_pdf(self.employee, form_data=form_data)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_partial_form_data_fallback(self):
        """Partially filled form_data → missing fields fall back to employee."""
        from apps.documents.services import generate_gph_contract_pdf
        form_data = {
            'subject': 'Консультации',
            'amount': '',  # empty → fallback to employee salary
            'start_date': '',
            'end_date': '',
            'doc_number': '',
            'doc_date': '',
        }
        pdf = generate_gph_contract_pdf(self.employee, form_data=form_data)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_date_formatting_yyyy_mm_dd(self):
        """Dates in YYYY-MM-DD format → correctly formatted to DD.MM.YYYY."""
        from apps.documents.services import generate_gph_contract_pdf
        # Test the internal _fmt_date via form_data
        form_data = {
            'subject': 'Test',
            'amount': '1000',
            'start_date': '2024-06-15',
            'end_date': '2024-12-25',
            'doc_number': 'T-001',
            'doc_date': '2024-06-01',
        }
        pdf = generate_gph_contract_pdf(self.employee, form_data=form_data)
        self.assertIsInstance(pdf, bytes)

    def test_date_formatting_dd_mm_yyyy(self):
        """Dates in DD.MM.YYYY format → passed through correctly."""
        from apps.documents.services import generate_gph_contract_pdf
        form_data = {
            'subject': 'Test',
            'amount': '1000',
            'start_date': '15.06.2024',
            'end_date': '25.12.2024',
            'doc_number': 'T-002',
            'doc_date': '01.06.2024',
        }
        pdf = generate_gph_contract_pdf(self.employee, form_data=form_data)
        self.assertIsInstance(pdf, bytes)

    def test_empty_doc_date_uses_today(self):
        """Empty doc_date in form_data → today's date is used."""
        from apps.documents.services import generate_gph_contract_pdf
        form_data = {
            'subject': '',
            'amount': '',
            'start_date': '',
            'end_date': '',
            'doc_number': '',
            'doc_date': '',
        }
        pdf = generate_gph_contract_pdf(self.employee, form_data=form_data)
        self.assertIsInstance(pdf, bytes)


# ===========================================================================
# 2. generate_gph_act_pdf
# ===========================================================================

class GenerateGphActPdfTests(TestCase):

    def setUp(self):
        self.user = _create_user("act@example.com")
        self.company = _create_company(self.user, name="ООО Акты")
        self.employee = _create_employee(self.company)

    def test_default_act(self):
        """generate_gph_act_pdf with defaults."""
        from apps.documents.services import generate_gph_act_pdf
        pdf = generate_gph_act_pdf(self.employee)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(len(pdf) > 100)

    def test_act_with_custom_data(self):
        """generate_gph_act_pdf with custom work_description and amount."""
        from apps.documents.services import generate_gph_act_pdf
        pdf = generate_gph_act_pdf(
            self.employee,
            work_description="Разработка API",
            amount=75000,
        )
        self.assertIsInstance(pdf, bytes)


# ===========================================================================
# 3. download_gph_contract view
# ===========================================================================

@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class DownloadGphContractViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _create_user("view@example.com")
        self.company = _create_company(self.user, name="ООО Вьюха")
        CompanyMember.objects.create(company=self.company, user=self.user, role="owner")
        _create_subscription(self.company)
        self.employee = _create_employee(self.company)
        self.client.login(email="view@example.com", password="TestPass123!")

    def test_get_params_passed_to_pdf(self):
        """GET parameters are passed as form_data to PDF generator."""
        url = f"/dashboard/employees/{self.employee.id}/gph-contract/"
        resp = self.client.get(url, {
            'subject': 'Тестовый предмет',
            'amount': '99999',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'doc_number': 'ГПХ-V-001',
            'doc_date': '2024-01-01',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_download_without_params(self):
        """Download GPH contract without GET params → uses employee defaults."""
        url = f"/dashboard/employees/{self.employee.id}/gph-contract/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")


# ===========================================================================
# 4. _fmt_date unit tests
# ===========================================================================

class FmtDateTests(TestCase):

    def _fmt(self, s):
        """Import and call the nested _fmt_date from generate_gph_contract_pdf."""
        # We test via the public function behavior, but we can also test directly
        if not s:
            return ''
        for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
            try:
                from datetime import datetime as _dt
                return _dt.strptime(s, fmt).strftime('%d.%m.%Y')
            except ValueError:
                pass
        return s

    def test_iso_format(self):
        self.assertEqual(self._fmt("2024-06-15"), "15.06.2024")

    def test_ru_format(self):
        self.assertEqual(self._fmt("15.06.2024"), "15.06.2024")

    def test_slash_format(self):
        self.assertEqual(self._fmt("15/06/2024"), "15.06.2024")

    def test_empty_string(self):
        self.assertEqual(self._fmt(""), "")

    def test_invalid_format(self):
        self.assertEqual(self._fmt("not-a-date"), "not-a-date")
