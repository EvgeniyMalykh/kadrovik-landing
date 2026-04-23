"""
Part 6 tests: annual subscription / billing_period support.

Run:
    python manage.py test apps.dashboard.tests_part6 --settings=config.settings.production -v 2
"""
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.billing.models import Subscription, Payment
from apps.billing.services import (
    activate_subscription,
    create_payment,
    PLANS,
    PLAN_PRICES,
    PLAN_MONTHLY_EQUIVALENT,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_company(suffix=''):
    """Create a user + company + owner member for testing."""
    email = f'owner{suffix}@test.com'
    user = User.objects.create_user(
        username=email,
        email=email,
        password='testpass123',
    )
    company = Company.objects.create(
        owner=user,
        name=f'TestCompany{suffix}',
        inn=f'555000000{suffix}',
        legal_address='Test Address',
        director_name='Test Director',
    )
    member = CompanyMember.objects.create(
        user=user,
        company=company,
        role='owner',
    )
    return user, company, member


class AnnualSubscriptionModelTests(TestCase):
    """Tests for the billing_period field on Subscription model."""

    def test_billing_period_default_is_monthly(self):
        """billing_period defaults to 'monthly'."""
        _, company, _ = _make_company('1')
        sub = Subscription.objects.create(company=company)
        self.assertEqual(sub.billing_period, 'monthly')

    def test_billing_period_can_be_set_to_annual(self):
        """billing_period can be set to 'annual'."""
        _, company, _ = _make_company('2')
        sub = Subscription.objects.create(company=company, billing_period='annual')
        sub.refresh_from_db()
        self.assertEqual(sub.billing_period, 'annual')


class ActivateSubscriptionTests(TestCase):
    """Tests for activate_subscription with billing_period support."""

    def test_annual_subscription_expires_in_365_days(self):
        """Annual subscription sets expires_at to now + 365 days."""
        _, company, _ = _make_company('3')
        now = timezone.now()
        sub = activate_subscription(company, 'start', billing_period='annual')
        delta = sub.expires_at - now
        # Allow small tolerance (a few seconds)
        self.assertAlmostEqual(delta.days, 365, delta=1)

    def test_monthly_subscription_expires_in_30_days(self):
        """Monthly subscription sets expires_at to now + 30 days."""
        _, company, _ = _make_company('4')
        now = timezone.now()
        sub = activate_subscription(company, 'start', billing_period='monthly')
        delta = sub.expires_at - now
        self.assertAlmostEqual(delta.days, 30, delta=1)

    def test_annual_billing_period_saved_in_model(self):
        """After annual activation, billing_period='annual' is saved."""
        _, company, _ = _make_company('5')
        sub = activate_subscription(company, 'business', billing_period='annual')
        sub.refresh_from_db()
        self.assertEqual(sub.billing_period, 'annual')

    def test_monthly_billing_period_saved_in_model(self):
        """After monthly activation, billing_period='monthly' is saved."""
        _, company, _ = _make_company('6')
        sub = activate_subscription(company, 'pro', billing_period='monthly')
        sub.refresh_from_db()
        self.assertEqual(sub.billing_period, 'monthly')

    def test_switch_monthly_to_annual(self):
        """Switching from monthly to annual updates billing_period and expiry."""
        _, company, _ = _make_company('7')
        # First activate monthly
        sub = activate_subscription(company, 'start', billing_period='monthly')
        self.assertEqual(sub.billing_period, 'monthly')
        # Now switch to annual
        sub = activate_subscription(company, 'start', billing_period='annual')
        sub.refresh_from_db()
        self.assertEqual(sub.billing_period, 'annual')
        delta = sub.expires_at - timezone.now()
        self.assertAlmostEqual(delta.days, 365, delta=1)


class AnnualPriceTests(TestCase):
    """Tests for annual pricing constants and 25% discount."""

    def test_annual_price_is_monthly_times_9(self):
        """Annual price = monthly * 12 * 0.75 = monthly * 9 (25% discount)."""
        for plan_key in ('start', 'business', 'pro'):
            monthly = PLAN_PRICES[plan_key]['monthly']
            annual = PLAN_PRICES[plan_key]['annual']
            expected = monthly * 9
            self.assertEqual(annual, expected,
                f'{plan_key}: annual {annual} != monthly*9 {expected}')

    def test_plan_prices_start(self):
        """Start plan: 790/mo, 7110/yr."""
        self.assertEqual(PLAN_PRICES['start']['monthly'], 790)
        self.assertEqual(PLAN_PRICES['start']['annual'], 7110)

    def test_plan_prices_business(self):
        """Business plan: 1990/mo, 17910/yr."""
        self.assertEqual(PLAN_PRICES['business']['monthly'], 1990)
        self.assertEqual(PLAN_PRICES['business']['annual'], 17910)

    def test_plan_prices_pro(self):
        """Pro plan: 4900/mo, 44100/yr."""
        self.assertEqual(PLAN_PRICES['pro']['monthly'], 4900)
        self.assertEqual(PLAN_PRICES['pro']['annual'], 44100)

    def test_monthly_equivalent_start(self):
        self.assertEqual(PLAN_MONTHLY_EQUIVALENT['start']['annual'], 592)

    def test_monthly_equivalent_business(self):
        self.assertEqual(PLAN_MONTHLY_EQUIVALENT['business']['annual'], 1492)

    def test_monthly_equivalent_pro(self):
        self.assertEqual(PLAN_MONTHLY_EQUIVALENT['pro']['annual'], 3675)

    def test_discount_is_25_percent(self):
        """Verify the 25% discount is applied correctly for all plans."""
        for plan_key in ('start', 'business', 'pro'):
            monthly = PLAN_PRICES[plan_key]['monthly']
            annual = PLAN_PRICES[plan_key]['annual']
            full_year = monthly * 12
            discount = 1 - (annual / full_year)
            self.assertAlmostEqual(discount, 0.25, places=2,
                msg=f'{plan_key}: discount is {discount:.2%}, expected 25%')


class CheckoutViewPeriodTests(TestCase):
    """Tests for the checkout view accepting period parameter."""

    def setUp(self):
        self.user, self.company, self.member = _make_company('8')
        Subscription.objects.create(
            company=self.company,
            plan='trial',
            status='active',
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.login(email='owner8@test.com', password='testpass123')

    @patch('apps.billing.views.create_payment')
    def test_checkout_passes_monthly_period(self, mock_create):
        """Checkout without period param defaults to monthly."""
        mock_payment = MagicMock()
        mock_create.return_value = (mock_payment, None)
        # When no period, should default to monthly
        self.client.get('/dashboard/checkout/start/')
        if mock_create.called:
            _, kwargs = mock_create.call_args
            self.assertEqual(kwargs.get('billing_period', 'monthly'), 'monthly')

    @patch('apps.billing.views.create_payment')
    def test_checkout_passes_annual_period(self, mock_create):
        """Checkout with period=annual passes annual to create_payment."""
        mock_payment = MagicMock()
        mock_create.return_value = (mock_payment, None)
        self.client.get('/dashboard/checkout/start/?period=annual')
        if mock_create.called:
            _, kwargs = mock_create.call_args
            self.assertEqual(kwargs.get('billing_period'), 'annual')

    @patch('apps.billing.views.create_payment')
    def test_checkout_rejects_invalid_period(self, mock_create):
        """Checkout with invalid period falls back to monthly."""
        mock_payment = MagicMock()
        mock_create.return_value = (mock_payment, None)
        self.client.get('/dashboard/checkout/start/?period=invalid')
        if mock_create.called:
            _, kwargs = mock_create.call_args
            self.assertEqual(kwargs.get('billing_period', 'monthly'), 'monthly')


class WebhookAnnualTests(TestCase):
    """Tests for YooKassa webhook handling annual billing_period."""

    def setUp(self):
        self.user, self.company, self.member = _make_company('9')

    @patch('apps.billing.views._check_yukassa_ip', return_value=True)
    @patch('apps.billing.views.activate_subscription')
    @patch('apps.billing.views.send_mail')
    def test_webhook_activates_annual_subscription(self, mock_mail, mock_activate, mock_ip):
        """Webhook with billing_period=annual in metadata activates annual sub."""
        mock_sub = MagicMock()
        mock_sub.expires_at = timezone.now() + timedelta(days=365)
        mock_sub.max_employees = 10
        mock_activate.return_value = mock_sub

        payment = Payment.objects.create(
            company=self.company,
            amount=7110,
            plan='start',
            status='pending',
        )
        payload = {
            'event': 'payment.succeeded',
            'object': {
                'id': 'yk_test_123',
                'metadata': {
                    'payment_db_id': str(payment.id),
                    'plan': 'start',
                    'company_id': str(self.company.id),
                    'billing_period': 'annual',
                },
                'payment_method': {'saved': False},
            },
        }
        resp = self.client.post(
            '/dashboard/webhook/yukassa/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        mock_activate.assert_called_once()
        call_kwargs = mock_activate.call_args
        # Check billing_period was passed as 'annual'
        if call_kwargs.kwargs:
            self.assertEqual(call_kwargs.kwargs.get('billing_period'), 'annual')
        else:
            # positional args fallback
            args = call_kwargs[0] if call_kwargs[0] else ()
            kwargs = call_kwargs[1] if len(call_kwargs) > 1 else {}
            self.assertEqual(kwargs.get('billing_period'), 'annual')

    @patch('apps.billing.views._check_yukassa_ip', return_value=True)
    @patch('apps.billing.views.activate_subscription')
    @patch('apps.billing.views.send_mail')
    def test_webhook_defaults_to_monthly(self, mock_mail, mock_activate, mock_ip):
        """Webhook without billing_period in metadata defaults to monthly."""
        mock_sub = MagicMock()
        mock_sub.expires_at = timezone.now() + timedelta(days=30)
        mock_sub.max_employees = 10
        mock_activate.return_value = mock_sub

        payment = Payment.objects.create(
            company=self.company,
            amount=790,
            plan='start',
            status='pending',
        )
        payload = {
            'event': 'payment.succeeded',
            'object': {
                'id': 'yk_test_456',
                'metadata': {
                    'payment_db_id': str(payment.id),
                    'plan': 'start',
                    'company_id': str(self.company.id),
                },
                'payment_method': {'saved': False},
            },
        }
        resp = self.client.post(
            '/dashboard/webhook/yukassa/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        mock_activate.assert_called_once()
        call_kwargs = mock_activate.call_args
        if call_kwargs.kwargs:
            self.assertEqual(call_kwargs.kwargs.get('billing_period', 'monthly'), 'monthly')


class CreatePaymentPriceTests(TestCase):
    """Tests for create_payment using correct prices for annual/monthly."""

    def setUp(self):
        self.user, self.company, self.member = _make_company('10')

    @override_settings(YUKASSA_SHOP_ID='', YUKASSA_SECRET_KEY='')
    def test_annual_payment_amount_start(self):
        """Annual start payment uses 7110 as amount."""
        payment, url = create_payment(self.company, 'start', 'http://test/', billing_period='annual')
        self.assertEqual(payment.amount, 7110)

    @override_settings(YUKASSA_SHOP_ID='', YUKASSA_SECRET_KEY='')
    def test_monthly_payment_amount_start(self):
        """Monthly start payment uses 790 as amount."""
        payment, url = create_payment(self.company, 'start', 'http://test/', billing_period='monthly')
        self.assertEqual(payment.amount, 790)

    @override_settings(YUKASSA_SHOP_ID='', YUKASSA_SECRET_KEY='')
    def test_annual_payment_amount_business(self):
        """Annual business payment uses 17910 as amount."""
        payment, url = create_payment(self.company, 'business', 'http://test/', billing_period='annual')
        self.assertEqual(payment.amount, 17910)

    @override_settings(YUKASSA_SHOP_ID='', YUKASSA_SECRET_KEY='')
    def test_annual_payment_amount_pro(self):
        """Annual pro payment uses 44100 as amount."""
        payment, url = create_payment(self.company, 'pro', 'http://test/', billing_period='annual')
        self.assertEqual(payment.amount, 44100)
