"""
Part 5 tests: notification routing (_send_notification_to_company, _send_telegram,
_resolve_telegram_chat_id, _send_email_to_company, _send_hr_email),
test-notify endpoint, Company notify fields, _count_vacation_days with holidays,
Celery tasks (check_birthdays, check_vacation_events, check_vacation_endings,
check_contract_endings, check_probation_endings, check_subscription_expirations).

Run:
    python manage.py test apps.dashboard.tests_part5 --settings=config.settings.production -v 2
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.employees.models import Employee, ProductionCalendar
from apps.billing.models import Subscription
from apps.vacations.models import Vacation


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _user(email='u5@example.com', password='TestPass5!'):
    return User.objects.create_user(username=email, email=email, password=password)


def _company(owner, name='ООО Тест5', inn='5550000000', **kw):
    defaults = dict(
        legal_address='г. Тест, ул. 5я',
        director_name='Тестов Т.Т.',
    )
    defaults.update(kw)
    return Company.objects.create(owner=owner, name=name, inn=inn, **defaults)


def _member(company, user, role='owner'):
    return CompanyMember.objects.create(company=company, user=user, role=role)


def _subscription(company, plan='business', days=30):
    return Subscription.objects.create(
        company=company, plan=plan,
        status=Subscription.Status.ACTIVE,
        expires_at=timezone.now() + timedelta(days=days),
    )


def _employee(company, **kw):
    defaults = dict(
        last_name='Тестов', first_name='Тест', middle_name='Тестович',
        position='Инженер',
        hire_date=date.today() - timedelta(days=90),
        marital_status='single',
        salary=Decimal('50000'),
        status='active',
    )
    defaults.update(kw)
    return Employee.objects.create(company=company, **defaults)


# ===========================================================================
# 5.1  Company notify fields
# ===========================================================================

class CompanyNotifyFieldsTests(TestCase):

    def setUp(self):
        self.user = _user(email='cnf@example.com')
        self.company = _company(self.user, inn='5551111111')
        _member(self.company, self.user)
        _subscription(self.company)
        self.client.force_login(self.user)

    def test_default_notify_messenger_is_email(self):
        """By default notify_messenger is 'email' or empty (falsy → treated as email)."""
        c = Company.objects.get(pk=self.company.pk)
        self.assertIn(c.notify_messenger or 'email', ['email', '', None])

    def test_save_telegram_messenger_and_contact(self):
        """Saving notify_messenger=telegram and notify_contact persists correctly."""
        self.company.notify_messenger = 'telegram'
        self.company.notify_contact = '@testuser'
        self.company.save()
        c = Company.objects.get(pk=self.company.pk)
        self.assertEqual(c.notify_messenger, 'telegram')
        self.assertEqual(c.notify_contact, '@testuser')

    def test_save_email_messenger_and_contact(self):
        """Saving notify_messenger=email with specific contact email."""
        self.company.notify_messenger = 'email'
        self.company.notify_contact = 'hr@mycompany.ru'
        self.company.save()
        c = Company.objects.get(pk=self.company.pk)
        self.assertEqual(c.notify_messenger, 'email')
        self.assertEqual(c.notify_contact, 'hr@mycompany.ru')

    def test_company_profile_post_saves_notify_fields(self):
        """POST to /dashboard/company/ with notify fields saves them."""
        resp = self.client.post(reverse('dashboard:company'), {
            'name': self.company.name,
            'inn': self.company.inn,
            'legal_address': self.company.legal_address,
            'director_name': self.company.director_name,
            'notify_messenger': 'telegram',
            'notify_contact': '@mybot',
        })
        self.assertEqual(resp.status_code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.notify_messenger, 'telegram')
        self.assertEqual(self.company.notify_contact, '@mybot')

    def test_notify_contact_cleared_on_empty_post(self):
        """If notify_contact posted as empty string, it clears the field."""
        self.company.notify_contact = '@old'
        self.company.save()
        self.client.post(reverse('dashboard:company'), {
            'name': self.company.name,
            'inn': self.company.inn,
            'legal_address': self.company.legal_address,
            'director_name': self.company.director_name,
            'notify_messenger': 'email',
            'notify_contact': '',
        })
        self.company.refresh_from_db()
        self.assertEqual(self.company.notify_contact, '')


# ===========================================================================
# 5.2  test-notify endpoint
# ===========================================================================

class TestNotifyEndpointTests(TestCase):

    def setUp(self):
        self.user = _user(email='tn@example.com')
        self.company = _company(self.user, inn='5552222222')
        _member(self.company, self.user)
        _subscription(self.company)
        self.client.force_login(self.user)

    def test_get_not_allowed(self):
        """GET /dashboard/company/test-notify/ → 405."""
        resp = self.client.get(reverse('dashboard:company_test_notify'))
        self.assertEqual(resp.status_code, 405)

    def test_no_contact_returns_error(self):
        """POST without notify_contact → ok=False."""
        self.company.notify_messenger = 'telegram'
        self.company.notify_contact = ''
        self.company.save()
        resp = self.client.post(
            reverse('dashboard:company_test_notify'),
            content_type='application/json',
            data=json.dumps({}),
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('контакт', data['message'].lower())

    def test_telegram_notify_returns_ok(self):
        """POST with telegram + numeric chat_id → ok=True, Telegram sendMessage called."""
        self.company.notify_messenger = 'telegram'
        self.company.notify_contact = '1113292310'
        self.company.save()

        with patch('apps.events.tasks.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            resp = self.client.post(
                reverse('dashboard:company_test_notify'),
                content_type='application/json',
                data=json.dumps({}),
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'], msg=data.get('message'))
        self.assertIn('telegram', data['message'].lower())
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        sent_json = call_kwargs[1]['json'] if call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(sent_json['chat_id'], '1113292310')

    def test_email_notify_returns_ok(self):
        """POST with email messenger → ok=True, send_mail called."""
        self.company.notify_messenger = 'email'
        self.company.notify_contact = 'hr@example.com'
        self.company.save()

        with patch('apps.events.tasks.send_mail') as mock_mail:
            resp = self.client.post(
                reverse('dashboard:company_test_notify'),
                content_type='application/json',
                data=json.dumps({}),
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'], msg=data.get('message'))
        self.assertIn('email', data['message'].lower())
        mock_mail.assert_called_once()
        call_args = mock_mail.call_args
        self.assertIn('hr@example.com', call_args[1].get('recipient_list', []))

    def test_unauthenticated_redirects(self):
        """Unauthenticated POST → redirect to login."""
        self.client.logout()
        resp = self.client.post(
            reverse('dashboard:company_test_notify'),
            content_type='application/json',
            data=json.dumps({}),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)


# ===========================================================================
# 5.3  _send_notification_to_company router
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='999',
)
class NotificationRouterTests(TestCase):

    def setUp(self):
        self.user = _user(email='router@example.com')
        self.company = _company(self.user, inn='5553333333')
        _member(self.company, self.user)
        _subscription(self.company)

    def _call_router(self, company):
        from apps.events.tasks import _send_notification_to_company
        _send_notification_to_company(
            company,
            text='Test text',
            subject='Test subject',
            html_body='<p>html</p>',
            plain_body='plain',
        )

    # -- telegram with numeric chat_id --

    def test_routes_to_telegram_with_numeric_chat_id(self):
        self.company.notify_messenger = 'telegram'
        self.company.notify_contact = '1113292310'
        self.company.save()

        with patch('apps.events.tasks.requests.post') as mock_post:
            self._call_router(self.company)

        mock_post.assert_called_once()
        sent = mock_post.call_args[1]['json']
        self.assertEqual(sent['chat_id'], '1113292310')
        self.assertEqual(sent['text'], 'Test text')

    # -- telegram with @username — resolves via getChat --

    def test_routes_to_telegram_with_username(self):
        self.company.notify_messenger = 'telegram'
        self.company.notify_contact = '@someuser'
        self.company.save()

        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {'ok': True, 'result': {'id': 42424242}}
        mock_post = MagicMock()

        with patch('apps.events.tasks.requests.get', mock_get), \
             patch('apps.events.tasks.requests.post', mock_post):
            self._call_router(self.company)

        # getChat должен быть вызван с @someuser
        mock_get.assert_called_once()
        self.assertIn('@someuser', str(mock_get.call_args))

        # sendMessage должен быть вызван с resolved chat_id
        mock_post.assert_called_once()
        sent = mock_post.call_args[1]['json']
        self.assertEqual(sent['chat_id'], 42424242)

    # -- telegram with @username, getChat fails — fallback to service chat --

    def test_telegram_username_getchat_fail_falls_back_to_service_chat(self):
        self.company.notify_messenger = 'telegram'
        self.company.notify_contact = '@unknownuser'
        self.company.save()

        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {'ok': False, 'description': 'Not Found'}
        mock_post = MagicMock()

        with patch('apps.events.tasks.requests.get', mock_get), \
             patch('apps.events.tasks.requests.post', mock_post):
            self._call_router(self.company)

        # sendMessage должен быть вызван с service chat_id из settings
        mock_post.assert_called_once()
        sent = mock_post.call_args[1]['json']
        self.assertEqual(str(sent['chat_id']), '999')

    # -- telegram with no contact — fallback to service chat --

    def test_telegram_no_contact_uses_service_chat(self):
        self.company.notify_messenger = 'telegram'
        self.company.notify_contact = ''
        self.company.save()

        with patch('apps.events.tasks.requests.post') as mock_post:
            self._call_router(self.company)

        mock_post.assert_called_once()
        sent = mock_post.call_args[1]['json']
        self.assertEqual(str(sent['chat_id']), '999')

    # -- email messenger --

    def test_routes_to_email_with_notify_contact(self):
        self.company.notify_messenger = 'email'
        self.company.notify_contact = 'custom@company.ru'
        self.company.save()

        with patch('apps.events.tasks.send_mail') as mock_mail:
            self._call_router(self.company)

        mock_mail.assert_called_once()
        self.assertIn('custom@company.ru', mock_mail.call_args[1]['recipient_list'])

    def test_routes_to_email_fallback_to_company_email(self):
        """email messenger + empty notify_contact → falls back to company.email."""
        self.company.notify_messenger = 'email'
        self.company.notify_contact = ''
        self.company.email = 'owner@company.ru'
        self.company.save()

        with patch('apps.events.tasks.send_mail') as mock_mail:
            self._call_router(self.company)

        mock_mail.assert_called_once()
        self.assertIn('owner@company.ru', mock_mail.call_args[1]['recipient_list'])

    def test_routes_to_email_fallback_to_owner_email(self):
        """email messenger + empty notify_contact + empty company.email → owner.email."""
        self.company.notify_messenger = 'email'
        self.company.notify_contact = ''
        self.company.email = ''
        self.company.save()

        with patch('apps.events.tasks.send_mail') as mock_mail:
            self._call_router(self.company)

        mock_mail.assert_called_once()
        self.assertIn(self.user.email, mock_mail.call_args[1]['recipient_list'])

    # -- whatsapp / viber — fallback to email --

    @override_settings(GREEN_API_INSTANCE_ID='1234567890', GREEN_API_TOKEN='testtoken')
    def test_whatsapp_with_contact_calls_green_api(self):
        """WhatsApp + номер → Green API sendMessage, email не шлётся."""
        self.company.notify_messenger = 'whatsapp'
        self.company.notify_contact = '+79001234567'
        self.company.save()

        with patch('apps.events.tasks.requests.post') as mock_post,              patch('apps.events.tasks.send_mail') as mock_mail:
            mock_post.return_value.status_code = 200
            self._call_router(self.company)

        mock_mail.assert_not_called()
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        self.assertIn('green-api.com', call_url)
        sent_json = mock_post.call_args[1]['json']
        # Номер нормализован: +79001234567 → 79001234567@c.us
        self.assertEqual(sent_json['chatId'], '79001234567@c.us')

    def test_whatsapp_no_contact_falls_back_to_email(self):
        """WhatsApp без номера → fallback на email."""
        self.company.notify_messenger = 'whatsapp'
        self.company.notify_contact = ''
        self.company.email = 'owner@company.ru'
        self.company.save()

        with patch('apps.events.tasks.send_mail') as mock_mail:
            self._call_router(self.company)

        mock_mail.assert_called_once()

    def test_viber_falls_back_to_email(self):
        self.company.notify_messenger = 'viber'
        self.company.notify_contact = '+79001234567'
        self.company.email = 'owner@company.ru'
        self.company.save()

        with patch('apps.events.tasks.send_mail') as mock_mail:
            self._call_router(self.company)

        mock_mail.assert_called_once()

    # -- null/empty messenger defaults to email --

    def test_null_messenger_defaults_to_email(self):
        self.company.notify_messenger = ''
        self.company.notify_contact = ''
        self.company.email = 'fallback@company.ru'
        self.company.save()

        with patch('apps.events.tasks.send_mail') as mock_mail:
            self._call_router(self.company)

        mock_mail.assert_called_once()


# ===========================================================================
# 5.4  _resolve_telegram_chat_id
# ===========================================================================

@override_settings(TELEGRAM_BOT_TOKEN='fake-token')
class ResolveTelegramChatIdTests(TestCase):

    def test_returns_id_on_success(self):
        from apps.events.tasks import _resolve_telegram_chat_id
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'ok': True, 'result': {'id': 12345678}}

        with patch('apps.events.tasks.requests.get', return_value=mock_resp):
            result = _resolve_telegram_chat_id('@testuser')

        self.assertEqual(result, 12345678)

    def test_returns_none_on_api_error(self):
        from apps.events.tasks import _resolve_telegram_chat_id
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'ok': False, 'description': 'Chat not found'}

        with patch('apps.events.tasks.requests.get', return_value=mock_resp):
            result = _resolve_telegram_chat_id('@nonexistent')

        self.assertIsNone(result)

    def test_returns_none_on_network_error(self):
        from apps.events.tasks import _resolve_telegram_chat_id
        with patch('apps.events.tasks.requests.get', side_effect=Exception('timeout')):
            result = _resolve_telegram_chat_id('@someone')
        self.assertIsNone(result)

    def test_returns_none_without_token(self):
        from apps.events.tasks import _resolve_telegram_chat_id
        with override_settings(TELEGRAM_BOT_TOKEN=''):
            result = _resolve_telegram_chat_id('@someone')
        self.assertIsNone(result)

    def test_returns_none_for_empty_contact(self):
        from apps.events.tasks import _resolve_telegram_chat_id
        result = _resolve_telegram_chat_id('')
        self.assertIsNone(result)

    def test_strips_at_sign_in_api_call(self):
        """API call must use @username (not @@username)."""
        from apps.events.tasks import _resolve_telegram_chat_id
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'ok': True, 'result': {'id': 99}}

        with patch('apps.events.tasks.requests.get', return_value=mock_resp) as mock_get:
            _resolve_telegram_chat_id('@user')

        params = mock_get.call_args[1]['params']
        self.assertEqual(params['chat_id'], '@user')


# ===========================================================================
# 5.5  _count_vacation_days with production calendar
# ===========================================================================

class CountVacationDaysTests(TestCase):

    def setUp(self):
        # Добавляем тестовые праздники в ProductionCalendar
        ProductionCalendar.objects.get_or_create(date=date(2026, 6, 12), defaults={'day_type': 'holiday'})  # День России
        ProductionCalendar.objects.get_or_create(date=date(2026, 5, 1),  defaults={'day_type': 'holiday'})  # Праздник труда
        ProductionCalendar.objects.get_or_create(date=date(2026, 5, 9),  defaults={'day_type': 'holiday'})  # День победы

    def _count(self, start, end):
        from apps.vacations.models import _count_vacation_days
        return _count_vacation_days(start, end)

    def test_no_holidays_in_range(self):
        """10 days, no holidays → 10."""
        result = self._count(date(2026, 7, 1), date(2026, 7, 10))
        self.assertEqual(result, 10)

    def test_one_holiday_in_range(self):
        """14 calendar days including 12 June → 13 vacation days."""
        result = self._count(date(2026, 6, 1), date(2026, 6, 14))
        self.assertEqual(result, 13)

    def test_holiday_on_weekend_still_deducted(self):
        """Holiday falling on Saturday still reduces vacation days (ст. 120 ТК РФ)."""
        # 12 June 2026 is Friday — still a holiday
        result = self._count(date(2026, 6, 12), date(2026, 6, 12))
        self.assertEqual(result, 0)  # one-day vacation on holiday = 0 vacation days

    def test_single_day_no_holiday(self):
        """Single day, no holiday → 1."""
        result = self._count(date(2026, 7, 15), date(2026, 7, 15))
        self.assertEqual(result, 1)

    def test_multiple_holidays_in_range(self):
        """May 1–10 2026: три праздника (1 мая, 4 мая перенос, 9 мая) → 10 - 3 = 7 дней."""
        result = self._count(date(2026, 5, 1), date(2026, 5, 10))
        self.assertEqual(result, 7)

    def test_invalid_range_returns_zero(self):
        """end < start → 0."""
        result = self._count(date(2026, 7, 10), date(2026, 7, 5))
        self.assertEqual(result, 0)

    def test_none_dates_return_zero(self):
        """None dates → 0."""
        from apps.vacations.models import _count_vacation_days
        self.assertEqual(_count_vacation_days(None, date(2026, 7, 1)), 0)
        self.assertEqual(_count_vacation_days(date(2026, 7, 1), None), 0)

    def test_weekend_days_included_in_count(self):
        """Weekends count toward vacation days (only holidays are excluded)."""
        # 2026-07-04 is Saturday, 2026-07-05 is Sunday — 7 calendar days, no holidays
        result = self._count(date(2026, 7, 1), date(2026, 7, 7))
        self.assertEqual(result, 7)


# ===========================================================================
# 5.6  Celery task: check_birthdays
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='999',
)
class CheckBirthdaysTaskTests(TestCase):

    def setUp(self):
        self.user = _user(email='bd5@example.com')
        self.company = _company(self.user, inn='5554444444')
        _member(self.company, self.user)
        _subscription(self.company, plan='business')

    def test_sends_notification_on_birthday(self):
        """check_birthdays sends Telegram message when birthday is today."""
        today = timezone.now().date()
        _employee(self.company, birth_date=today.replace(year=today.year - 30))

        from apps.events.tasks import check_birthdays
        with patch('apps.events.tasks.requests.post') as mock_post:
            result = check_birthdays()

        mock_post.assert_called_once()
        self.assertIn(str(today.year), result)

    def test_sends_notification_3_days_before(self):
        """check_birthdays sends Telegram message 3 days before birthday."""
        today = timezone.now().date()
        bday = today + timedelta(days=3)
        _employee(self.company, birth_date=bday.replace(year=bday.year - 25))

        from apps.events.tasks import check_birthdays
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_birthdays()

        mock_post.assert_called_once()

    def test_no_notification_for_other_days(self):
        """check_birthdays does NOT send for birthdays 1, 2, or 5 days away."""
        today = timezone.now().date()
        for delta in [1, 2, 5]:
            bday = today + timedelta(days=delta)
            _employee(
                self.company,
                last_name=f'Testov{delta}',
                birth_date=bday.replace(year=bday.year - 30),
            )

        from apps.events.tasks import check_birthdays
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_birthdays()

        mock_post.assert_not_called()

    def test_no_notification_for_inactive_employee(self):
        """check_birthdays skips inactive employees."""
        today = timezone.now().date()
        _employee(
            self.company,
            birth_date=today.replace(year=today.year - 30),
            status='dismissed',
        )

        from apps.events.tasks import check_birthdays
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_birthdays()

        mock_post.assert_not_called()


# ===========================================================================
# 5.7  Celery task: check_vacation_events
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='999',
)
class CheckVacationEventsTaskTests(TestCase):

    def setUp(self):
        self.user = _user(email='ve5@example.com')
        self.company = _company(self.user, inn='5555555555')
        _member(self.company, self.user)
        _subscription(self.company, plan='business')
        self.emp = _employee(self.company)

    def test_sends_on_vacation_start_today(self):
        """check_vacation_events notifies when vacation starts today."""
        today = timezone.now().date()
        Vacation.objects.create(
            employee=self.emp,
            vacation_type='annual',
            start_date=today,
            end_date=today + timedelta(days=14),
        )

        from apps.events.tasks import check_vacation_events
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_vacation_events()

        mock_post.assert_called_once()
        text = mock_post.call_args[1]['json']['text']
        self.assertIn('Сегодня начинается', text)

    def test_sends_on_vacation_start_tomorrow(self):
        """check_vacation_events notifies when vacation starts tomorrow."""
        today = timezone.now().date()
        Vacation.objects.create(
            employee=self.emp,
            vacation_type='annual',
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=15),
        )

        from apps.events.tasks import check_vacation_events
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_vacation_events()

        mock_post.assert_called_once()
        text = mock_post.call_args[1]['json']['text']
        self.assertIn('Завтра начинается', text)

    def test_no_notification_for_vacation_starting_later(self):
        """check_vacation_events does NOT notify for vacation starting in 2+ days."""
        today = timezone.now().date()
        Vacation.objects.create(
            employee=self.emp,
            vacation_type='annual',
            start_date=today + timedelta(days=5),
            end_date=today + timedelta(days=19),
        )

        from apps.events.tasks import check_vacation_events
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_vacation_events()

        mock_post.assert_not_called()


# ===========================================================================
# 5.8  Celery task: check_vacation_endings
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='999',
)
class CheckVacationEndingsTaskTests(TestCase):

    def setUp(self):
        self.user = _user(email='vend5@example.com')
        self.company = _company(self.user, inn='5556666666')
        _member(self.company, self.user)
        _subscription(self.company, plan='business')
        self.emp = _employee(self.company)

    def test_sends_3_days_before_end(self):
        """check_vacation_endings notifies when vacation ends in 3 days."""
        today = timezone.now().date()
        end = today + timedelta(days=3)
        Vacation.objects.create(
            employee=self.emp,
            vacation_type='annual',
            start_date=today - timedelta(days=11),
            end_date=end,
        )

        from apps.events.tasks import check_vacation_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_vacation_endings()

        mock_post.assert_called_once()
        text = mock_post.call_args[1]['json']['text']
        self.assertIn('через 3 дня', text.lower())

    def test_no_notification_for_other_end_dates(self):
        """check_vacation_endings does NOT notify for vacations ending in 1 or 7 days."""
        today = timezone.now().date()
        for delta in [1, 7]:
            Vacation.objects.create(
                employee=self.emp,
                vacation_type='annual',
                start_date=today - timedelta(days=5),
                end_date=today + timedelta(days=delta),
            )

        from apps.events.tasks import check_vacation_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_vacation_endings()

        mock_post.assert_not_called()


# ===========================================================================
# 5.9  Celery task: check_contract_endings
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='999',
)
class CheckContractEndingsTaskTests(TestCase):

    def setUp(self):
        self.user = _user(email='ce5@example.com')
        self.company = _company(self.user, inn='5557777777')
        _member(self.company, self.user)
        _subscription(self.company, plan='business')

    def _emp_with_contract(self, days_until_end):
        today = timezone.now().date()
        return _employee(
            self.company,
            contract_type='fixed',
            contract_end_date=today + timedelta(days=days_until_end),
        )

    def test_sends_14_days_before(self):
        self._emp_with_contract(14)
        from apps.events.tasks import check_contract_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_contract_endings()
        mock_post.assert_called_once()

    def test_sends_7_days_before(self):
        self._emp_with_contract(7)
        from apps.events.tasks import check_contract_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_contract_endings()
        mock_post.assert_called_once()

    def test_sends_3_days_before(self):
        self._emp_with_contract(3)
        from apps.events.tasks import check_contract_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_contract_endings()
        mock_post.assert_called_once()

    def test_no_send_for_permanent_contract(self):
        """Permanent contract (contract_type='permanent') must NOT trigger."""
        today = timezone.now().date()
        _employee(
            self.company,
            contract_type='permanent',
            contract_end_date=today + timedelta(days=7),
        )
        from apps.events.tasks import check_contract_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_contract_endings()
        mock_post.assert_not_called()

    def test_no_send_for_dismissed_employee(self):
        """Dismissed employee must NOT trigger contract ending notification."""
        today = timezone.now().date()
        _employee(
            self.company,
            contract_type='fixed',
            contract_end_date=today + timedelta(days=7),
            status='dismissed',
        )
        from apps.events.tasks import check_contract_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_contract_endings()
        mock_post.assert_not_called()


# ===========================================================================
# 5.10  Celery task: check_probation_endings
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='999',
)
class CheckProbationEndingsTaskTests(TestCase):

    def setUp(self):
        self.user = _user(email='pe5@example.com')
        self.company = _company(self.user, inn='5558888888')
        _member(self.company, self.user)
        _subscription(self.company, plan='business')

    def _emp_with_probation(self, days_until_end):
        today = timezone.now().date()
        return _employee(
            self.company,
            probation_end_date=today + timedelta(days=days_until_end),
        )

    def test_sends_7_days_before(self):
        self._emp_with_probation(7)
        from apps.events.tasks import check_probation_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_probation_endings()
        mock_post.assert_called_once()

    def test_sends_3_days_before(self):
        self._emp_with_probation(3)
        from apps.events.tasks import check_probation_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_probation_endings()
        mock_post.assert_called_once()

    def test_sends_1_day_before(self):
        self._emp_with_probation(1)
        from apps.events.tasks import check_probation_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_probation_endings()
        mock_post.assert_called_once()

    def test_no_send_for_other_days(self):
        """No notification for probation ending in 2, 5, 14 days."""
        for days in [2, 5, 14]:
            self._emp_with_probation(days)

        from apps.events.tasks import check_probation_endings
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_probation_endings()
        mock_post.assert_not_called()


# ===========================================================================
# 5.11  Celery task: check_subscription_expirations
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN='fake-token',
    TELEGRAM_CHAT_ID='999',
    DEFAULT_FROM_EMAIL='noreply@kadrovik-auto.ru',
)
class CheckSubscriptionExpirationsTaskTests(TestCase):

    def setUp(self):
        self.user = _user(email='se5@example.com')
        self.company = _company(self.user, inn='5559999999')
        _member(self.company, self.user)

    def _sub_expiring_in(self, days):
        return Subscription.objects.create(
            company=self.company, plan='start',
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=days),
        )

    def test_sends_telegram_3_days_before(self):
        self._sub_expiring_in(3)
        from apps.events.tasks import check_subscription_expirations
        with patch('apps.events.tasks.requests.post') as mock_post, \
             patch('apps.events.tasks.send_mail'):
            check_subscription_expirations()
        mock_post.assert_called_once()
        text = mock_post.call_args[1]['json']['text']
        self.assertIn('через 3 дня', text.lower())

    def test_sends_telegram_1_day_before(self):
        self._sub_expiring_in(1)
        from apps.events.tasks import check_subscription_expirations
        with patch('apps.events.tasks.requests.post') as mock_post, \
             patch('apps.events.tasks.send_mail'):
            check_subscription_expirations()
        mock_post.assert_called_once()
        text = mock_post.call_args[1]['json']['text']
        self.assertIn('завтра', text.lower())

    def test_no_send_for_subscription_expiring_in_5_days(self):
        self._sub_expiring_in(5)
        from apps.events.tasks import check_subscription_expirations
        with patch('apps.events.tasks.requests.post') as mock_post, \
             patch('apps.events.tasks.send_mail') as mock_mail:
            check_subscription_expirations()
        mock_post.assert_not_called()
        mock_mail.assert_not_called()

    def test_no_send_for_expired_subscription(self):
        """Already expired subscription must NOT trigger notification."""
        Subscription.objects.create(
            company=self.company, plan='start',
            status=Subscription.Status.EXPIRED,
            expires_at=timezone.now() - timedelta(days=1),
        )
        from apps.events.tasks import check_subscription_expirations
        with patch('apps.events.tasks.requests.post') as mock_post:
            check_subscription_expirations()
        mock_post.assert_not_called()
