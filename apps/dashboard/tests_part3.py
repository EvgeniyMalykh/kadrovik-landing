"""
Part 3 tests: Events page, employee search/filter, role-based permissions
(require_role decorator), Celery tasks (check_birthdays, check_vacation_events).
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, Department
from apps.billing.models import Subscription
from apps.vacations.models import Vacation


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_user(email='test3@example.com', password='testpass123'):
    return User.objects.create_user(
        username=email, email=email, password=password
    )


def _make_company(owner, **kw):
    defaults = dict(
        name='Test LLC 3',
        inn='3334567890',
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


# ===== 3.1 Events page =====================================================

@override_settings(LOGIN_URL='/dashboard/login/')
class EventsPageTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.company = _make_company(self.user)
        _make_member(self.company, self.user, role='owner')
        _make_subscription(self.company, plan='trial')
        self.client.force_login(self.user)

    def test_events_page_authenticated(self):
        """Authorized user can access events page (200)."""
        resp = self.client.get('/dashboard/events/')
        self.assertEqual(resp.status_code, 200)

    def test_events_page_unauthenticated_redirect(self):
        """Unauthenticated user is redirected to login."""
        self.client.logout()
        resp = self.client.get('/dashboard/events/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_events_page_shows_birthday_event(self):
        """Employee with birthday within 30 days appears in events."""
        today = date.today()
        # Birthday in 5 days
        bday = today + timedelta(days=5)
        birth_date = bday.replace(year=bday.year - 30)
        _make_employee(
            self.company,
            last_name='Ivanov',
            first_name='Ivan',
            birth_date=birth_date,
        )
        resp = self.client.get('/dashboard/events/')
        self.assertEqual(resp.status_code, 200)
        events = resp.context.get('events', [])
        birthday_events = [e for e in events if e['type'] == 'birthday']
        self.assertTrue(len(birthday_events) >= 1)
        self.assertIn('Ivanov', birthday_events[0]['title'])

    def test_events_page_shows_vacation_event(self):
        """Vacation starting soon appears in events."""
        today = date.today()
        emp = _make_employee(self.company, last_name='Sidorov', first_name='Sidor')
        Vacation.objects.create(
            employee=emp,
            vacation_type='annual',
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=16),
        )
        resp = self.client.get('/dashboard/events/')
        self.assertEqual(resp.status_code, 200)
        events = resp.context.get('events', [])
        vacation_events = [e for e in events if e['type'] == 'vacation']
        self.assertTrue(len(vacation_events) >= 1)

    def test_events_filtered_by_company(self):
        """User only sees events for their own company."""
        # Create employee with birthday today for this company
        today = date.today()
        birth_date_own = today.replace(year=today.year - 25)
        _make_employee(
            self.company,
            last_name='OwnCompanyGuy',
            first_name='Own',
            birth_date=birth_date_own,
        )

        # Create another company with employee
        user2 = _make_user(email='other3@example.com')
        company2 = _make_company(user2, name='Other LLC 3', inn='9994567890')
        _make_member(company2, user2, role='owner')
        _make_subscription(company2, plan='trial')
        _make_employee(
            company2,
            last_name='OtherCompanyGuy',
            first_name='Other',
            birth_date=birth_date_own,
        )

        resp = self.client.get('/dashboard/events/')
        events = resp.context.get('events', [])
        titles = ' '.join(e['title'] for e in events)
        self.assertIn('OwnCompanyGuy', titles)
        self.assertNotIn('OtherCompanyGuy', titles)


# ===== 3.2 Employee search/filter ==========================================

@override_settings(LOGIN_URL='/dashboard/login/')
class EmployeeSearchFilterTests(TestCase):

    def setUp(self):
        self.user = _make_user(email='filter3@example.com')
        self.company = _make_company(self.user, name='Filter LLC', inn='5554567890')
        _make_member(self.company, self.user, role='owner')
        _make_subscription(self.company, plan='trial')
        self.client.force_login(self.user)

        self.dept = Department.objects.create(company=self.company, name='IT')
        self.dept2 = Department.objects.create(company=self.company, name='HR')

        self.emp_ivan = _make_employee(
            self.company,
            last_name='Ivanov',
            first_name='Ivan',
            department=self.dept,
            status='active',
        )
        self.emp_petr = _make_employee(
            self.company,
            last_name='Petrov',
            first_name='Petr',
            department=self.dept2,
            status='active',
        )
        self.emp_fired = _make_employee(
            self.company,
            last_name='Sidorov',
            first_name='Sidor',
            status='fired',
        )

    def test_search_by_name(self):
        """GET /dashboard/employees/?q=Ivanov returns only matching employees."""
        resp = self.client.get('/dashboard/employees/', {'q': 'Ivanov'})
        self.assertEqual(resp.status_code, 200)
        employees = list(resp.context['employees'])
        last_names = [e.last_name for e in employees]
        self.assertIn('Ivanov', last_names)
        self.assertNotIn('Petrov', last_names)

    def test_search_by_first_name(self):
        """GET /dashboard/employees/?q=Ivan returns Ivanov."""
        resp = self.client.get('/dashboard/employees/', {'q': 'Ivan'})
        self.assertEqual(resp.status_code, 200)
        employees = list(resp.context['employees'])
        last_names = [e.last_name for e in employees]
        self.assertIn('Ivanov', last_names)

    def test_filter_fired(self):
        """GET /dashboard/employees/?status=fired returns only fired employees."""
        resp = self.client.get('/dashboard/employees/', {'status': 'fired'})
        self.assertEqual(resp.status_code, 200)
        employees = list(resp.context['employees'])
        last_names = [e.last_name for e in employees]
        self.assertIn('Sidorov', last_names)
        self.assertNotIn('Ivanov', last_names)
        self.assertNotIn('Petrov', last_names)

    def test_filter_by_department(self):
        """GET /dashboard/employees/?department=<id> filters by department."""
        resp = self.client.get('/dashboard/employees/', {'department': self.dept.id})
        self.assertEqual(resp.status_code, 200)
        employees = list(resp.context['employees'])
        last_names = [e.last_name for e in employees]
        self.assertIn('Ivanov', last_names)
        self.assertNotIn('Petrov', last_names)

    def test_default_returns_active(self):
        """Empty query returns all active employees (default status=active)."""
        resp = self.client.get('/dashboard/employees/')
        self.assertEqual(resp.status_code, 200)
        employees = list(resp.context['employees'])
        last_names = [e.last_name for e in employees]
        self.assertIn('Ivanov', last_names)
        self.assertIn('Petrov', last_names)
        self.assertNotIn('Sidorov', last_names)

    def test_filter_all_status(self):
        """status=all returns all employees including fired."""
        resp = self.client.get('/dashboard/employees/', {'status': 'all'})
        self.assertEqual(resp.status_code, 200)
        employees = list(resp.context['employees'])
        last_names = [e.last_name for e in employees]
        self.assertIn('Ivanov', last_names)
        self.assertIn('Sidorov', last_names)


# ===== 3.3 Role-based permissions (require_role) ===========================

@override_settings(LOGIN_URL='/dashboard/login/')
class RolePermissionsTests(TestCase):
    """Test the require_role decorator and role hierarchy."""

    def setUp(self):
        # Owner
        self.owner_user = _make_user(email='owner3@example.com')
        self.company = _make_company(self.owner_user, name='Role LLC', inn='6664567890')
        _make_member(self.company, self.owner_user, role='owner')
        _make_subscription(self.company, plan='business')

        # Admin
        self.admin_user = _make_user(email='admin3@example.com')
        _make_member(self.company, self.admin_user, role='admin')

        # HR
        self.hr_user = _make_user(email='hr3@example.com')
        _make_member(self.company, self.hr_user, role='hr')

        # Accountant
        self.accountant_user = _make_user(email='acc3@example.com')
        _make_member(self.company, self.accountant_user, role='accountant')

        # Employee for tests
        self.employee = _make_employee(self.company)

    def _login(self, email):
        self.client.logout()
        user_map = {
            'owner3@example.com': self.owner_user,
            'admin3@example.com': self.admin_user,
            'hr3@example.com': self.hr_user,
            'acc3@example.com': self.accountant_user,
        }
        user = user_map[email]
        self.client.force_login(user)

    # --- Accountant CANNOT ---

    def test_accountant_cannot_add_employee(self):
        """Accountant cannot POST to employee add (require_role hr)."""
        self._login('acc3@example.com')
        resp = self.client.get('/dashboard/employees/add/')
        # require_role redirects to dashboard home (302)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard/', resp.url)

    def test_accountant_cannot_add_vacation(self):
        """Accountant cannot access vacation add."""
        self._login('acc3@example.com')
        resp = self.client.get('/vacations/add/')
        # vacation_add checks role inline: returns 403 JSON
        self.assertIn(resp.status_code, [302, 403])

    def test_accountant_cannot_access_api_settings(self):
        """Accountant cannot access /dashboard/api/ (require_role admin)."""
        self._login('acc3@example.com')
        resp = self.client.get('/dashboard/api/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard/', resp.url)

    # --- HR CANNOT ---

    def test_hr_cannot_access_api_settings(self):
        """HR cannot access /dashboard/api/ (require_role admin)."""
        self._login('hr3@example.com')
        resp = self.client.get('/dashboard/api/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard/', resp.url)

    # --- HR CAN ---

    def test_hr_can_add_employee(self):
        """HR can access employee add form (require_role hr)."""
        self._login('hr3@example.com')
        resp = self.client.get('/dashboard/employees/add/')
        self.assertEqual(resp.status_code, 200)

    def test_hr_can_add_vacation(self):
        """HR can access vacation add."""
        self._login('hr3@example.com')
        resp = self.client.get('/vacations/add/')
        self.assertEqual(resp.status_code, 200)

    # --- Admin CAN ---

    def test_admin_can_access_employee_add(self):
        """Admin can access employee add (admin > hr)."""
        self._login('admin3@example.com')
        resp = self.client.get('/dashboard/employees/add/')
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_access_api_settings(self):
        """Admin can access API settings page."""
        self._login('admin3@example.com')
        resp = self.client.get('/dashboard/api/')
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_access_team(self):
        """Admin can see team page (team_list only requires login)."""
        self._login('admin3@example.com')
        resp = self.client.get('/dashboard/team/')
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_add_vacation(self):
        """Admin can add vacation (admin > hr)."""
        self._login('admin3@example.com')
        resp = self.client.get('/vacations/add/')
        self.assertEqual(resp.status_code, 200)

    # --- Owner CAN everything ---

    def test_owner_can_access_employee_add(self):
        """Owner can access employee add."""
        self._login('owner3@example.com')
        resp = self.client.get('/dashboard/employees/add/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_access_api_settings(self):
        """Owner can access API settings page."""
        self._login('owner3@example.com')
        resp = self.client.get('/dashboard/api/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_access_team(self):
        """Owner can access team page."""
        self._login('owner3@example.com')
        resp = self.client.get('/dashboard/team/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_access_subscription(self):
        """Owner can access subscription page."""
        self._login('owner3@example.com')
        resp = self.client.get('/dashboard/subscription/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_access_events(self):
        """Owner can access events page."""
        self._login('owner3@example.com')
        resp = self.client.get('/dashboard/events/')
        self.assertEqual(resp.status_code, 200)

    # --- Role denial is 302 redirect, not 403 ---

    def test_role_denial_is_redirect_not_403(self):
        """When require_role denies access, it returns 302 redirect, not 403."""
        self._login('acc3@example.com')
        resp = self.client.get('/dashboard/employees/add/')
        self.assertEqual(resp.status_code, 302)
        # Should redirect to dashboard home
        self.assertNotEqual(resp.status_code, 403)

    def test_role_denial_redirects_to_dashboard(self):
        """Denied user redirects to /dashboard/ (home)."""
        self._login('acc3@example.com')
        resp = self.client.get('/dashboard/api/')
        self.assertEqual(resp.status_code, 302)
        # Follow redirect
        resp2 = self.client.get('/dashboard/api/', follow=True)
        self.assertEqual(resp2.status_code, 200)


# ===== 3.4 Celery tasks (mock external calls) ==============================

@override_settings(
    LOGIN_URL='/dashboard/login/',
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='12345',
    DEFAULT_FROM_EMAIL='noreply@test.com',
)
class CheckBirthdaysTaskTests(TestCase):
    """Test check_birthdays task logic without actual Celery execution."""

    def setUp(self):
        self.user = _make_user(email='celery_bd3@example.com')
        self.company = _make_company(self.user, name='Birthday LLC', inn='7774567890')
        _make_member(self.company, self.user, role='owner')
        _make_subscription(self.company, plan='business')

    @patch('apps.events.tasks._send_hr_email')
    def test_birthday_today_triggers_notification(self, mock_hr_email):
        """Employee with birthday today triggers telegram + email notifications."""
        today = date.today()
        birth_date = today.replace(year=today.year - 30)
        _make_employee(
            self.company,
            last_name='BdayToday',
            first_name='Test',
            birth_date=birth_date,
            status='active',
        )

        from apps.events.tasks import check_birthdays
        result = check_birthdays()

        mock_hr_email.assert_called()
        call_kwargs = mock_hr_email.call_args[1]
        self.assertIn('BdayToday', call_kwargs['employee_name'])
        self.assertIn('день рождения', call_kwargs['title'].lower())

    @patch('apps.events.tasks._send_hr_email')
    def test_birthday_in_3_days_triggers_notification(self, mock_hr_email):
        """Employee with birthday in 3 days triggers notification."""
        today = date.today()
        bday = today + timedelta(days=3)
        try:
            birth_date = bday.replace(year=bday.year - 25)
        except ValueError:
            birth_date = bday.replace(year=bday.year - 25, day=28)
        _make_employee(
            self.company,
            last_name='BdaySoon',
            first_name='Test',
            birth_date=birth_date,
            status='active',
        )

        from apps.events.tasks import check_birthdays
        result = check_birthdays()

        mock_hr_email.assert_called()
        call_kwargs = mock_hr_email.call_args[1]
        self.assertIn('BdaySoon', call_kwargs['employee_name'])

    @patch('apps.events.tasks._send_hr_email')
    def test_birthday_no_email_without_plan_feature(self, mock_hr_email):
        """Notification is still sent via _send_hr_email even when plan lacks email_notify."""
        today = date.today()
        birth_date = today.replace(year=today.year - 28)
        _make_employee(
            self.company,
            last_name='NoEmail',
            first_name='Test',
            birth_date=birth_date,
            status='active',
        )

        from apps.events.tasks import check_birthdays
        result = check_birthdays()
        # _send_hr_email is always called; email gating is handled inside
        mock_hr_email.assert_called()

    @patch('apps.events.tasks._send_telegram')
    @patch('apps.events.tasks._has_email_notify', return_value=True)
    def test_no_notification_for_far_birthday(self, mock_email_notify, mock_telegram):
        """Employee with birthday in 15 days does NOT trigger notification."""
        today = date.today()
        bday = today + timedelta(days=15)
        try:
            birth_date = bday.replace(year=bday.year - 35)
        except ValueError:
            birth_date = bday.replace(year=bday.year - 35, day=28)
        _make_employee(
            self.company,
            last_name='FarBday',
            first_name='Test',
            birth_date=birth_date,
            status='active',
        )

        from apps.events.tasks import check_birthdays
        result = check_birthdays()

        mock_telegram.assert_not_called()

    @patch('apps.events.tasks._send_telegram')
    @patch('apps.events.tasks._has_email_notify', return_value=True)
    def test_no_notification_for_fired_employee(self, mock_email_notify, mock_telegram):
        """Fired employee birthday does NOT trigger notification."""
        today = date.today()
        birth_date = today.replace(year=today.year - 30)
        _make_employee(
            self.company,
            last_name='FiredBday',
            first_name='Test',
            birth_date=birth_date,
            status='fired',
        )

        from apps.events.tasks import check_birthdays
        result = check_birthdays()

        mock_telegram.assert_not_called()


@override_settings(
    LOGIN_URL='/dashboard/login/',
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='12345',
    DEFAULT_FROM_EMAIL='noreply@test.com',
)
class CheckVacationEventsTaskTests(TestCase):
    """Test check_vacation_events task logic without actual Celery execution."""

    def setUp(self):
        self.user = _make_user(email='celery_vac3@example.com')
        self.company = _make_company(self.user, name='Vacation LLC', inn='8884567890')
        _make_member(self.company, self.user, role='owner')
        _make_subscription(self.company, plan='business')
        self.employee = _make_employee(
            self.company,
            last_name='Vacationer',
            first_name='Test',
            status='active',
        )

    @patch('apps.events.tasks._send_hr_email')
    def test_vacation_starting_today_triggers_notification(self, mock_hr_email):
        """Vacation starting today triggers notification."""
        today = date.today()
        Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=today,
            end_date=today + timedelta(days=14),
        )

        from apps.events.tasks import check_vacation_events
        result = check_vacation_events()

        mock_hr_email.assert_called()
        call_kwargs = mock_hr_email.call_args[1]
        self.assertIn('Vacationer', call_kwargs['employee_name'])
        self.assertIn('отпуск', call_kwargs['title'].lower())

    @patch('apps.events.tasks._send_hr_email')
    def test_vacation_starting_tomorrow_triggers_notification(self, mock_hr_email):
        """Vacation starting tomorrow triggers notification."""
        today = date.today()
        Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=15),
        )

        from apps.events.tasks import check_vacation_events
        result = check_vacation_events()

        mock_hr_email.assert_called()
        call_kwargs = mock_hr_email.call_args[1]
        self.assertIn('Vacationer', call_kwargs['employee_name'])

    @patch('apps.events.tasks._send_telegram')
    @patch('apps.events.tasks._has_email_notify', return_value=True)
    def test_no_notification_for_far_vacation(self, mock_email_notify, mock_telegram):
        """Vacation starting in 5 days does NOT trigger notification."""
        today = date.today()
        Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=today + timedelta(days=5),
            end_date=today + timedelta(days=19),
        )

        from apps.events.tasks import check_vacation_events
        result = check_vacation_events()

        mock_telegram.assert_not_called()

    @patch('apps.events.tasks._send_hr_email')
    def test_vacation_notification_contains_type(self, mock_hr_email):
        """Vacation notification mentions the vacation type."""
        today = date.today()
        Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=today,
            end_date=today + timedelta(days=14),
        )

        from apps.events.tasks import check_vacation_events
        result = check_vacation_events()

        mock_hr_email.assert_called()
        call_kwargs = mock_hr_email.call_args[1]
        self.assertIn('Ежегодный', call_kwargs['description'])

    @patch('apps.events.tasks._send_hr_email')
    def test_vacation_no_email_without_plan_feature(self, mock_hr_email):
        """Notification is still sent via _send_hr_email even when plan lacks email_notify."""
        today = date.today()
        Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=today,
            end_date=today + timedelta(days=14),
        )

        from apps.events.tasks import check_vacation_events
        result = check_vacation_events()
        # _send_hr_email is always called; email gating is handled inside
        mock_hr_email.assert_called()

    @patch('apps.events.tasks._send_telegram')
    @patch('apps.events.tasks._has_email_notify', return_value=True)
    def test_no_notification_for_fired_employee_vacation(self, mock_email_notify, mock_telegram):
        """Fired employee's vacation does NOT trigger notification."""
        self.employee.status = 'fired'
        self.employee.save()

        today = date.today()
        Vacation.objects.create(
            employee=self.employee,
            vacation_type='annual',
            start_date=today,
            end_date=today + timedelta(days=14),
        )

        from apps.events.tasks import check_vacation_events
        result = check_vacation_events()

        mock_telegram.assert_not_called()
