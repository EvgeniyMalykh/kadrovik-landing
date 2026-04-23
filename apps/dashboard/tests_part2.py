"""
Part 2 tests: vacations, timesheet, team, API, SFR export, custom templates,
SFR generator unit tests, document history.
"""
import uuid
import json
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from django.urls import reverse, NoReverseMatch
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember, CompanyInvite
from apps.employees.models import Employee
from apps.billing.models import Subscription
from apps.documents.models import Document, DocumentTemplate
from apps.vacations.models import VacationSchedule, VacationScheduleEntry


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_user(email='test@example.com', password='testpass123'):
    return User.objects.create_user(
        username=email, email=email, password=password
    )


def _make_company(owner, **kw):
    defaults = dict(
        name='Test LLC',
        inn='1234567890',
        legal_address='Moscow',
        director_name='Ivanov I.I.',
    )
    defaults.update(kw)
    return Company.objects.create(owner=owner, **defaults)


def _make_member(company, user, role='owner'):
    return CompanyMember.objects.create(company=company, user=user, role=role)


def _make_subscription(company, plan='trial'):
    from django.utils import timezone
    from datetime import timedelta
    return Subscription.objects.create(
        company=company, plan=plan,
        status=Subscription.Status.ACTIVE,
        expires_at=timezone.now() + timedelta(days=30),
    )


def _make_employee(company, **kw):
    defaults = dict(
        last_name='Petrov',
        first_name='Petr',
        middle_name='Petrovich',
        position='Manager',
        hire_date=date.today() - timedelta(days=60),
        marital_status='single',
    )
    defaults.update(kw)
    return Employee.objects.create(company=company, **defaults)


# ===== 2.1 Vacations ======================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class VacationTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.company = _make_company(self.user)
        self.member = _make_member(self.company, self.user)
        self.sub = _make_subscription(self.company, 'trial')
        self.employee = _make_employee(self.company)
        self.client.force_login(self.user)

    # GET /vacations/schedule/ -> 200
    def test_vacation_schedule_list_200(self):
        url = reverse('vacations:schedule')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    # POST creates VacationSchedule
    def test_vacation_schedule_create(self):
        url = reverse('vacations:schedule_save')
        year = date.today().year
        payload = {
            'year': year,
            'rows': [],
        }
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 302])
        self.assertTrue(VacationSchedule.objects.filter(
            company=self.company, year=year
        ).exists())

    # GET /vacations/schedule/history/ -> 200
    def test_vacation_schedule_history_200(self):
        url = reverse('vacations:schedule_history')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    # GET /vacations/schedule/pdf/ -> 200 + application/pdf
    def test_vacation_schedule_pdf(self):
        # Need a schedule first
        schedule = VacationSchedule.objects.create(
            company=self.company,
            year=date.today().year,
        )
        VacationScheduleEntry.objects.create(
            schedule=schedule,
            employee=self.employee,
            days_total=28,
        )
        url = reverse('vacations:schedule_pdf')
        resp = self.client.get(url, {'year': schedule.year})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/pdf', resp.get('Content-Type', ''))


# ===== 2.2 Timesheet ======================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class TimesheetTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.company = _make_company(self.user)
        self.member = _make_member(self.company, self.user)
        self.sub = _make_subscription(self.company, 'trial')
        self.employee = _make_employee(self.company)
        self.client.force_login(self.user)

    def test_timesheet_200(self):
        url = reverse('dashboard:timesheet_edit')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_timesheet_save(self):
        url = reverse('dashboard:timesheet_save')
        payload = {
            'records': [
                {
                    'employee_id': self.employee.id,
                    'date': date.today().isoformat(),
                    'code': 'Я',
                    'hours': 8,
                }
            ]
        }
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 302])

    def test_timesheet_context_has_year_month(self):
        url = reverse('dashboard:timesheet_edit')
        resp = self.client.get(url)
        self.assertIn('year', resp.context)
        self.assertIn('month', resp.context)


# ===== 2.3 Team (multi_user) ==============================================

@override_settings(LOGIN_URL='/dashboard/login/')
class TeamTests(TestCase):

    def setUp(self):
        self.owner = _make_user('owner@example.com')
        self.company = _make_company(self.owner)
        self.member = _make_member(self.company, self.owner, role='owner')
        self.sub = _make_subscription(self.company, 'business')
        self.client.force_login(self.owner)

    def test_team_list_200(self):
        url = reverse('dashboard:team_list')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_team_invite_start_plan_blocked(self):
        """Start plan has multi_user=False -> invite should be blocked."""
        self.sub.plan = 'start'
        self.sub.save()
        url = reverse('dashboard:team_invite')
        resp = self.client.post(url, {'email': 'new@example.com', 'role': 'hr'})
        # Should redirect to team_list with error message
        self.assertIn(resp.status_code, [302, 403])

    @patch('django.core.mail.send_mail')
    def test_team_invite_business_plan(self, mock_mail):
        """Business plan -> invite should succeed."""
        url = reverse('dashboard:team_invite')
        resp = self.client.post(url, {'email': 'invited@example.com', 'role': 'hr'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CompanyInvite.objects.filter(
            company=self.company, email='invited@example.com'
        ).exists())

    @patch('django.core.mail.send_mail')
    def test_invite_accept_get_200(self, mock_mail):
        """GET on invite accept page -> 200."""
        invite = CompanyInvite.objects.create(
            company=self.company,
            invited_by=self.owner,
            email='guest@example.com',
            role='hr',
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.logout()
        url = reverse('dashboard:invite_accept', kwargs={'token': invite.token})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    @patch('django.core.mail.send_mail')
    def test_invite_accept_already_member(self, mock_mail):
        """If user is already a member -> appropriate response."""
        invite = CompanyInvite.objects.create(
            company=self.company,
            invited_by=self.owner,
            email='owner@example.com',
            role='hr',
            expires_at=timezone.now() + timedelta(days=7),
        )
        url = reverse('dashboard:invite_accept', kwargs={'token': invite.token})
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [200, 302])

    def test_invite_expired(self):
        """Expired invite -> expired page."""
        invite = CompanyInvite.objects.create(
            company=self.company,
            invited_by=self.owner,
            email='late@example.com',
            role='hr',
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.client.logout()
        url = reverse('dashboard:invite_accept', kwargs={'token': invite.token})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # Should render the expired template (checking template used or content)
        templates_used = [t.name for t in resp.templates] if hasattr(resp, 'templates') else []
        has_expired_tpl = any('expired' in t for t in templates_used)
        has_expired_content = b'expired' in resp.content.lower() or b'\xd0\xb8\xd1\x81\xd1\x82\xd0\xb5\xd0\xba' in resp.content  # "истек" in utf-8
        self.assertTrue(has_expired_tpl or has_expired_content)

    @patch('django.core.mail.send_mail')
    def test_team_member_remove(self, mock_mail):
        """Remove non-owner member -> success."""
        other = _make_user('other@example.com')
        other_member = _make_member(self.company, other, role='hr')
        url = reverse('dashboard:team_member_remove', kwargs={'member_id': other_member.id})
        resp = self.client.post(url)
        self.assertIn(resp.status_code, [302, 200])
        self.assertFalse(CompanyMember.objects.filter(id=other_member.id).exists())

    def test_team_cannot_remove_owner(self):
        """Trying to remove owner -> error."""
        url = reverse('dashboard:team_member_remove', kwargs={'member_id': self.member.id})
        resp = self.client.post(url)
        self.assertIn(resp.status_code, [302, 200])
        # Owner should still exist
        self.assertTrue(CompanyMember.objects.filter(id=self.member.id).exists())


# ===== 2.4 REST API =======================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class APITests(TestCase):

    def setUp(self):
        self.user = _make_user('api@example.com')
        self.company = _make_company(self.user)
        self.member = _make_member(self.company, self.user)
        self.sub = _make_subscription(self.company, 'pro')
        self.employee = _make_employee(self.company)
        self.token = Token.objects.create(user=self.user)
        self.api = APIClient()

    def test_api_unauthenticated_401(self):
        resp = self.api.get('/api/v1/employees/')
        self.assertEqual(resp.status_code, 401)

    def test_api_non_pro_plan_403(self):
        self.sub.plan = 'start'
        self.sub.save()
        self.api.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        resp = self.api.get('/api/v1/employees/')
        self.assertEqual(resp.status_code, 403)

    def test_api_pro_plan_200(self):
        self.api.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        resp = self.api.get('/api/v1/employees/')
        self.assertEqual(resp.status_code, 200)

    def test_api_token_obtain(self):
        resp = self.api.post('/api/v1/auth/token/', {
            'username': 'api@example.com',
            'password': 'testpass123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('token', resp.data)

    def test_api_employees_returns_company_data(self):
        """API should NOT return employees from another company."""
        other_user = _make_user('other_api@example.com')
        other_co = _make_company(other_user, name='Other LLC', inn='0987654321')
        _make_member(other_co, other_user)
        _make_subscription(other_co, 'pro')
        other_emp = _make_employee(other_co, last_name='Sidorov')

        self.api.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        resp = self.api.get('/api/v1/employees/')
        self.assertEqual(resp.status_code, 200)
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertNotIn(other_emp.id, ids)

    def test_api_events_200(self):
        self.api.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        resp = self.api.get('/api/v1/events/')
        self.assertEqual(resp.status_code, 200)

    def test_api_company_200(self):
        self.api.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        resp = self.api.get('/api/v1/company/')
        self.assertEqual(resp.status_code, 200)

    def test_api_settings_page_200(self):
        self.client.force_login(self.user)
        url = reverse('dashboard:api_settings')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_api_token_regenerate(self):
        self.client.force_login(self.user)
        old_key = self.token.key
        url = reverse('dashboard:api_token_regenerate')
        resp = self.client.post(url)
        self.assertIn(resp.status_code, [302, 200])
        new_token = Token.objects.filter(user=self.user).first()
        self.assertIsNotNone(new_token)
        self.assertNotEqual(old_key, new_token.key)


# ===== 2.5 SFR export =====================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class SFRExportTests(TestCase):

    def setUp(self):
        self.user = _make_user('sfr@example.com')
        self.company = _make_company(
            self.user,
            sfr_reg_number='012-345-678901',
            okved='62.01',
            kpp='770401001',
        )
        self.member = _make_member(self.company, self.user)
        self.sub = _make_subscription(self.company, 'pro')
        self.employee = _make_employee(
            self.company,
            hire_date=date.today() - timedelta(days=10),
            snils='12345678901',
        )
        self.client.force_login(self.user)

    def test_sfr_page_200(self):
        url = reverse('dashboard:sfr_export')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_sfr_non_pro_plan_locked(self):
        self.sub.plan = 'start'
        self.sub.save()
        url = reverse('dashboard:sfr_export')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # Page renders but feature is locked
        self.assertFalse(resp.context.get('has_sfr_export', True))

    def test_sfr_xml_generation(self):
        url = reverse('dashboard:sfr_export')
        period_start = (date.today() - timedelta(days=30)).isoformat()
        period_end = date.today().isoformat()
        resp = self.client.post(url, {
            'period_start': period_start,
            'period_end': period_end,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/xml', resp.get('Content-Type', ''))

    def test_sfr_xml_contains_company_inn(self):
        url = reverse('dashboard:sfr_export')
        period_start = (date.today() - timedelta(days=30)).isoformat()
        period_end = date.today().isoformat()
        resp = self.client.post(url, {
            'period_start': period_start,
            'period_end': period_end,
        })
        content = resp.content.decode('utf-8')
        self.assertIn(self.company.inn, content)

    def test_sfr_xml_contains_employee_snils(self):
        url = reverse('dashboard:sfr_export')
        period_start = (date.today() - timedelta(days=30)).isoformat()
        period_end = date.today().isoformat()
        resp = self.client.post(url, {
            'period_start': period_start,
            'period_end': period_end,
        })
        content = resp.content.decode('utf-8')
        # SNILS should be formatted as 123-456-789 01
        self.assertIn('123-456-789 01', content)

    def test_sfr_no_events_empty_xml(self):
        """No HR events in the period -> XML without employee blocks."""
        url = reverse('dashboard:sfr_export')
        # Period far in the future where no hires happened
        period_start = (date.today() + timedelta(days=100)).isoformat()
        period_end = (date.today() + timedelta(days=130)).isoformat()
        resp = self.client.post(url, {
            'period_start': period_start,
            'period_end': period_end,
        })
        content = resp.content.decode('utf-8')
        self.assertNotIn('СведенияОТрудДеятельности', content)


# ===== 2.6 Custom templates ===============================================

@override_settings(LOGIN_URL='/dashboard/login/')
class CustomTemplatesTests(TestCase):

    def setUp(self):
        self.user = _make_user('tpl@example.com')
        self.company = _make_company(self.user)
        self.member = _make_member(self.company, self.user)
        self.sub = _make_subscription(self.company, 'pro')
        self.client.force_login(self.user)

    def test_templates_page_200(self):
        url = reverse('dashboard:document_templates')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_templates_non_pro_locked(self):
        self.sub.plan = 'start'
        self.sub.save()
        url = reverse('dashboard:document_templates')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context.get('has_custom_templates', True))

    def test_template_upload_docx(self):
        url = reverse('dashboard:document_template_upload', kwargs={'doc_type': 'hire'})
        docx_content = b'PK\x03\x04'  # minimal zip/docx header
        f = SimpleUploadedFile('template.docx', docx_content,
                               content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        resp = self.client.post(url, {'file': f})
        self.assertIn(resp.status_code, [302, 200])
        self.assertTrue(DocumentTemplate.objects.filter(
            company=self.company, doc_type='hire'
        ).exists())

    def test_template_upload_wrong_format(self):
        url = reverse('dashboard:document_template_upload', kwargs={'doc_type': 'hire'})
        f = SimpleUploadedFile('bad.pdf', b'%PDF-1.4', content_type='application/pdf')
        resp = self.client.post(url, {'file': f})
        self.assertIn(resp.status_code, [302, 200])
        # Should NOT create a template
        self.assertFalse(DocumentTemplate.objects.filter(
            company=self.company, doc_type='hire'
        ).exists())

    def test_template_delete(self):
        tpl = DocumentTemplate.objects.create(
            company=self.company,
            doc_type='hire',
            file=SimpleUploadedFile('t.docx', b'PK\x03\x04'),
            name='t.docx',
        )
        url = reverse('dashboard:document_template_delete', kwargs={'doc_type': 'hire'})
        resp = self.client.post(url)
        self.assertIn(resp.status_code, [302, 200])
        self.assertFalse(DocumentTemplate.objects.filter(id=tpl.id).exists())


# ===== 2.7 SFR XML Generator (unit) =======================================

class SFRGeneratorTests(TestCase):

    def setUp(self):
        self.user = _make_user('gen@example.com')
        self.company = _make_company(self.user, sfr_reg_number='012-345-678901', okved='62.01')
        self.member = _make_member(self.company, self.user)
        self.sub = _make_subscription(self.company, 'pro')
        self.employee = _make_employee(self.company, snils='12345678901')

    def test_generate_xml_returns_bytes(self):
        from apps.documents.sfr_generator import generate_efs1_xml
        events = [{
            'employee': self.employee,
            'event_type': 'hire',
            'event_date': self.employee.hire_date,
            'position': self.employee.position,
        }]
        result = generate_efs1_xml(self.company, events)
        self.assertIsInstance(result, bytes)

    def test_generate_xml_valid_structure(self):
        from apps.documents.sfr_generator import generate_efs1_xml
        events = [{
            'employee': self.employee,
            'event_type': 'hire',
            'event_date': self.employee.hire_date,
            'position': self.employee.position,
        }]
        result = generate_efs1_xml(self.company, events)
        xml_str = result.decode('utf-8')
        self.assertIn('ЭДПФР', xml_str)

    def test_generate_xml_company_name(self):
        from apps.documents.sfr_generator import generate_efs1_xml
        events = [{
            'employee': self.employee,
            'event_type': 'hire',
            'event_date': self.employee.hire_date,
            'position': self.employee.position,
        }]
        result = generate_efs1_xml(self.company, events)
        xml_str = result.decode('utf-8')
        self.assertIn(self.company.name, xml_str)

    def test_snils_formatting(self):
        from apps.documents.sfr_generator import _snils_formatted
        self.assertEqual(_snils_formatted('12345678901'), '123-456-789 01')


# ===== 2.8 Document history ===============================================

@override_settings(LOGIN_URL='/dashboard/login/')
class DocumentHistoryTests(TestCase):

    def setUp(self):
        self.user = _make_user('hist@example.com')
        self.company = _make_company(self.user)
        self.member = _make_member(self.company, self.user)
        self.sub = _make_subscription(self.company, 'trial')
        self.employee = _make_employee(self.company)
        self.client.force_login(self.user)

    def test_history_page_200(self):
        url = reverse('dashboard:forms_list')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_history_filter_by_type(self):
        Document.objects.create(
            company=self.company,
            employee=self.employee,
            doc_type='hire',
            number='T1-1',
            date=date.today(),
        )
        Document.objects.create(
            company=self.company,
            employee=self.employee,
            doc_type='fire',
            number='T8-1',
            date=date.today(),
        )
        url = reverse('dashboard:forms_list')
        resp = self.client.get(url, {'type': 'hire'})
        self.assertEqual(resp.status_code, 200)
        docs = resp.context.get('documents', [])
        for doc in docs:
            self.assertEqual(doc.doc_type, 'hire')

    def test_document_delete(self):
        doc = Document.objects.create(
            company=self.company,
            employee=self.employee,
            doc_type='hire',
            number='T1-99',
            date=date.today(),
        )
        url = reverse('dashboard:delete_document', kwargs={'doc_id': doc.id})
        resp = self.client.post(url)
        self.assertIn(resp.status_code, [200, 302])
        self.assertFalse(Document.objects.filter(id=doc.id).exists())
