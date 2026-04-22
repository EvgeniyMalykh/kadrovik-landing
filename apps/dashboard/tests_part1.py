"""
Part 1 tests: auth, employees, billing, company profile, documents, export_excel.
Run:
    python manage.py test apps.dashboard.tests_part1 --settings=config.settings.production -v 2
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, Department
from apps.billing.models import Subscription
from apps.billing.services import get_plan_features, PLANS


# ---------------------------------------------------------------------------
#  helpers
# ---------------------------------------------------------------------------

def _create_user(email="test@example.com", password="TestPass123!"):
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
    )
    return user


def _create_company(owner, name="ООО Тест", inn="1234567890"):
    return Company.objects.create(
        owner=owner,
        name=name,
        inn=inn,
        ogrn="1234567890123",
        legal_address="г. Москва, ул. Тестовая, д.1",
        director_name="Иванов Иван Иванович",
    )


def _create_membership(user, company, role="owner"):
    return CompanyMember.objects.create(
        company=company, user=user, role=role,
    )


def _create_subscription(company, plan="trial"):
    return Subscription.objects.create(
        company=company,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        expires_at=timezone.now() + timedelta(days=30),
        max_employees=50,
    )


def _create_employee(company, last_name="Петров", first_name="Пётр", position="Инженер"):
    return Employee.objects.create(
        company=company,
        last_name=last_name,
        first_name=first_name,
        middle_name="Петрович",
        position=position,
        hire_date=date.today(),
        salary=Decimal("50000.00"),
        marital_status="single",
    )


# ===========================================================================
# 1.1  Authentication
# ===========================================================================

class AuthTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.password = "TestPass123!"
        self.user = _create_user(password=self.password)
        self.company = _create_company(self.user)
        _create_membership(self.user, self.company, role="owner")
        _create_subscription(self.company, plan="trial")

    # -- login ---------------------------------------------------------------

    def test_login_valid(self):
        """Valid email + password → redirect to employees list."""
        resp = self.client.post(
            reverse("dashboard:login"),
            {"email": self.user.email, "password": self.password},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/employees/", resp.url)

    def test_login_invalid(self):
        """Wrong password → 200 with error message in context."""
        resp = self.client.post(
            reverse("dashboard:login"),
            {"email": self.user.email, "password": "WrongPassword!"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Неверный email или пароль")

    # -- login_required ------------------------------------------------------

    def test_login_required(self):
        """Anonymous access to /dashboard/employees/ → redirect to login."""
        resp = self.client.get(reverse("dashboard:employees"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/login/", resp.url)

    # -- register (uses Redis, so we test the GET only) ----------------------

    def test_register_page_200(self):
        """GET /dashboard/register/ → 200."""
        resp = self.client.get(reverse("dashboard:register"))
        self.assertEqual(resp.status_code, 200)

    # -- logout --------------------------------------------------------------

    def test_logout(self):
        """Logout → redirect to login page."""
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard:logout"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/login/", resp.url)

    def test_login_redirect_when_authenticated(self):
        """Already authenticated user accessing login → redirect to employees."""
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard:login"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/employees/", resp.url)


# ===========================================================================
# 1.2  Employees CRUD
# ===========================================================================

class EmployeeTests(TestCase):

    def setUp(self):
        self.password = "TestPass123!"
        self.user = _create_user(password=self.password)
        self.company = _create_company(self.user)
        _create_membership(self.user, self.company, role="owner")
        _create_subscription(self.company, plan="trial")
        self.employee = _create_employee(self.company)
        self.client.force_login(self.user)

    def test_employee_list_200(self):
        resp = self.client.get(reverse("dashboard:employees"))
        self.assertEqual(resp.status_code, 200)

    def test_employee_add_get_200(self):
        resp = self.client.get(reverse("dashboard:employee_add"))
        self.assertEqual(resp.status_code, 200)

    def test_employee_add_post_creates(self):
        count_before = Employee.objects.filter(company=self.company).count()
        resp = self.client.post(reverse("dashboard:employee_add"), {
            "last_name": "Сидоров",
            "first_name": "Сидор",
            "middle_name": "Сидорович",
            "position": "Менеджер",
            "hire_date": "01.01.2024",
            "salary": "60000",
            "status": "active",
            "contract_type": "permanent",
            "marital_status": "single",
            "citizenship": "Российская Федерация",
        })
        self.assertEqual(resp.status_code, 200)  # returns partial HTML
        self.assertEqual(
            Employee.objects.filter(company=self.company).count(),
            count_before + 1,
        )

    def test_employee_edit_get_200(self):
        resp = self.client.get(
            reverse("dashboard:employee_edit", args=[self.employee.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)

    def test_employee_edit_post_updates(self):
        resp = self.client.post(
            reverse("dashboard:employee_edit", args=[self.employee.id]),
            {
                "last_name": "Обновлённый",
                "first_name": "Имя",
                "middle_name": "",
                "position": "Директор",
                "hire_date": "15.06.2023",
                "salary": "120000",
                "status": "active",
                "contract_type": "permanent",
                "marital_status": "single",
                "citizenship": "Российская Федерация",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.last_name, "Обновлённый")
        self.assertEqual(self.employee.position, "Директор")
        self.assertEqual(self.employee.salary, Decimal("120000"))

    def test_employee_delete(self):
        emp_id = self.employee.id
        resp = self.client.post(
            reverse("dashboard:employee_delete", args=[emp_id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Employee.objects.filter(id=emp_id).exists())

    def test_employee_isolation(self):
        """User of another company must NOT see employees of this company."""
        other_user = _create_user(email="other@example.com")
        other_company = _create_company(other_user, name="ООО Другая", inn="9876543210")
        _create_membership(other_user, other_company, role="owner")
        _create_subscription(other_company, plan="trial")
        other_emp = _create_employee(other_company, last_name="Чужойсотрудник")

        self.client.force_login(other_user)
        resp = self.client.get(reverse("dashboard:employees"))
        self.assertEqual(resp.status_code, 200)
        # Other user should see their own employee
        self.assertContains(resp, "Чужойсотрудник")
        # The queryset should only return employees belonging to other_company
        from apps.employees.models import Employee
        visible_employees = Employee.objects.filter(company=other_company)
        self.assertEqual(visible_employees.count(), 1)
        self.assertEqual(visible_employees.first().last_name, "Чужойсотрудник")
        # Our employee should NOT be in other_company's employees
        self.assertFalse(
            Employee.objects.filter(company=other_company, last_name="Петров").exists()
        )


# ===========================================================================
# 1.3  Export Excel
# ===========================================================================

class ExportExcelTests(TestCase):

    def setUp(self):
        self.user = _create_user()
        self.company = _create_company(self.user)
        _create_membership(self.user, self.company)
        _create_employee(self.company)
        self.client.force_login(self.user)

    def _set_plan(self, plan):
        Subscription.objects.filter(company=self.company).delete()
        _create_subscription(self.company, plan=plan)

    # employees excel --------------------------------------------------------

    def test_export_employees_excel_business_plan(self):
        self._set_plan("business")
        resp = self.client.get(reverse("dashboard:export_employees_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "spreadsheet",
            resp["Content-Type"],
        )

    def test_export_employees_excel_start_plan(self):
        self._set_plan("start")
        resp = self.client.get(reverse("dashboard:export_employees_excel"))
        self.assertEqual(resp.status_code, 403)

    def test_export_employees_excel_trial_plan(self):
        """Trial plan has export_excel=True (corporate-level features)."""
        self._set_plan("trial")
        resp = self.client.get(reverse("dashboard:export_employees_excel"))
        self.assertEqual(resp.status_code, 200)

    # timesheet excel --------------------------------------------------------

    def test_export_timesheet_excel_pro_plan(self):
        self._set_plan("pro")
        resp = self.client.get(reverse("dashboard:export_timesheet_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "spreadsheet",
            resp["Content-Type"],
        )

    def test_export_timesheet_excel_start_plan(self):
        self._set_plan("start")
        resp = self.client.get(reverse("dashboard:export_timesheet_excel"))
        self.assertEqual(resp.status_code, 403)

    # unauthenticated --------------------------------------------------------

    def test_export_employees_excel_unauthenticated(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard:export_employees_excel"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/login/", resp.url)


# ===========================================================================
# 1.4  Billing
# ===========================================================================

class BillingTests(TestCase):

    def setUp(self):
        self.user = _create_user()
        self.company = _create_company(self.user)
        _create_membership(self.user, self.company)
        _create_subscription(self.company, plan="trial")
        self.client.force_login(self.user)

    def test_subscription_page_200(self):
        resp = self.client.get(reverse("dashboard:subscription"))
        self.assertEqual(resp.status_code, 200)

    # plan features ----------------------------------------------------------

    def test_plan_features_trial(self):
        feats = get_plan_features("trial")
        self.assertTrue(feats["documents"])
        self.assertTrue(feats["export_excel"])
        self.assertTrue(feats["multi_user"])

    def test_plan_features_start(self):
        feats = get_plan_features("start")
        self.assertFalse(feats["export_excel"])
        self.assertFalse(feats["multi_user"])

    def test_plan_features_business(self):
        feats = get_plan_features("business")
        self.assertTrue(feats["email_notify"])
        self.assertTrue(feats["multi_user"])
        self.assertTrue(feats["export_excel"])

    def test_plan_features_pro(self):
        feats = get_plan_features("pro")
        for key, val in feats.items():
            self.assertTrue(val, f"pro plan feature '{key}' should be True")

    # context processor ------------------------------------------------------

    def test_context_processor_injects_plan_features(self):
        """plan_features must be present in the template context of any page."""
        resp = self.client.get(reverse("dashboard:employees"))
        self.assertIn("plan_features", resp.context)


# ===========================================================================
# 1.5  Company Profile
# ===========================================================================

class CompanyProfileTests(TestCase):

    def setUp(self):
        self.user = _create_user()
        self.company = _create_company(self.user)
        _create_membership(self.user, self.company)
        _create_subscription(self.company)
        self.client.force_login(self.user)

    def test_company_profile_200(self):
        resp = self.client.get(reverse("dashboard:company"))
        self.assertEqual(resp.status_code, 200)

    def test_company_profile_post_updates(self):
        resp = self.client.post(reverse("dashboard:company"), {
            "name": "ООО Новое Имя",
            "inn": "0000000000",
            "director_name": "Новый Директор",
            "legal_address": "ул. Обновлённая",
        })
        self.assertEqual(resp.status_code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "ООО Новое Имя")
        self.assertEqual(self.company.inn, "0000000000")
        self.assertEqual(self.company.director_name, "Новый Директор")

    def test_company_sfr_fields_saved(self):
        resp = self.client.post(reverse("dashboard:company"), {
            "name": self.company.name,
            "inn": self.company.inn,
            "legal_address": self.company.legal_address,
            "director_name": self.company.director_name,
            "sfr_reg_number": "123-456-789012",
            "okved": "62.01",
        })
        self.assertEqual(resp.status_code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.sfr_reg_number, "123-456-789012")
        self.assertEqual(self.company.okved, "62.01")


# ===========================================================================
# 1.6  Documents
# ===========================================================================

class DocumentTests(TestCase):

    def setUp(self):
        self.user = _create_user()
        self.company = _create_company(self.user)
        _create_membership(self.user, self.company)
        _create_subscription(self.company, plan="trial")
        self.employee = _create_employee(self.company)
        self.client.force_login(self.user)

    # forms_list & form_editor -----------------------------------------------

    def test_forms_list_200(self):
        resp = self.client.get(reverse("dashboard:forms_list"))
        self.assertEqual(resp.status_code, 200)

    def test_form_editor_vacation_200(self):
        resp = self.client.get(reverse("dashboard:form_editor", args=["vacation"]))
        self.assertEqual(resp.status_code, 200)

    def test_form_editor_dismissal_200(self):
        resp = self.client.get(reverse("dashboard:form_editor", args=["dismissal"]))
        self.assertEqual(resp.status_code, 200)

    def test_form_save_creates_document(self):
        from apps.documents.models import Document
        count_before = Document.objects.count()
        resp = self.client.post(
            reverse("dashboard:form_save", args=["vacation"]),
            {
                "employee_id": self.employee.id,
                "doc_number": "О-001",
                "doc_date": "17.04.2026",
                "vacation_start": "01.05.2026",
                "vacation_end": "14.05.2026",
                "vacation_type": "annual",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Document.objects.count(), count_before + 1)
        doc = Document.objects.latest("id")
        self.assertEqual(doc.doc_type, "vacation")
        self.assertEqual(doc.employee, self.employee)

    # PDF downloads ----------------------------------------------------------

    def test_download_t1_pdf(self):
        resp = self.client.get(
            reverse("dashboard:download_t1", args=[self.employee.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_download_t8_pdf(self):
        resp = self.client.get(
            reverse("dashboard:download_t8", args=[self.employee.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_download_t6_pdf(self):
        resp = self.client.get(
            reverse("dashboard:download_t6", args=[self.employee.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_download_work_certificate(self):
        resp = self.client.get(
            reverse("dashboard:download_certificate", args=[self.employee.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
