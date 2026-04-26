"""
Tests for accounts app: notification tasks, email sending, Telegram/Google Sheets integration.
"""
from unittest.mock import patch, MagicMock, PropertyMock
from django.test import TestCase, override_settings
from django.core import mail

from apps.accounts.models import User


# ---------------------------------------------------------------------------
#  helpers
# ---------------------------------------------------------------------------

def _create_user(email="test@example.com", password="TestPass123!"):
    return User.objects.create_user(
        username=email,
        email=email,
        password=password,
    )


# ===========================================================================
# 1. _send_telegram  (Green API primary, Bot API fallback)
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN="fake-bot-token",
    TELEGRAM_CHAT_ID="123456",
    GREEN_API_TG_INSTANCE_ID="inst123",
    GREEN_API_TG_TOKEN="tok456",
)
class SendTelegramTests(TestCase):

    def test_green_api_success_no_fallback(self):
        """Green API returns 200 -> message sent, no Bot API fallback."""
        from apps.accounts.tasks import _send_telegram
        with patch("apps.accounts.tasks.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_post.return_value = mock_resp
            _send_telegram("Hello test")
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertIn("green-api.com", args[0])

    def test_green_api_failure_falls_back_to_bot_api(self):
        """Green API returns non-200 -> falls back to Bot API."""
        from apps.accounts.tasks import _send_telegram
        with patch("apps.accounts.tasks.requests.post") as mock_post:
            green_resp = MagicMock()
            green_resp.ok = False
            green_resp.status_code = 500
            green_resp.text = "Internal error"
            bot_resp = MagicMock()
            bot_resp.ok = True
            mock_post.side_effect = [green_resp, bot_resp]

            _send_telegram("Fallback test")
            self.assertEqual(mock_post.call_count, 2)
            second_call = mock_post.call_args_list[1]
            self.assertIn("api.telegram.org", second_call[0][0])

    def test_green_api_exception_falls_back_to_bot_api(self):
        """Green API raises exception -> falls back to Bot API."""
        from apps.accounts.tasks import _send_telegram
        with patch("apps.accounts.tasks.requests.post") as mock_post:
            bot_resp = MagicMock()
            bot_resp.ok = True
            mock_post.side_effect = [Exception("connection error"), bot_resp]

            _send_telegram("Exception test")
            self.assertEqual(mock_post.call_count, 2)
            second_call = mock_post.call_args_list[1]
            self.assertIn("api.telegram.org", second_call[0][0])

    def test_empty_chat_id_does_nothing(self):
        """Empty chat_id -> no HTTP calls."""
        from apps.accounts.tasks import _send_telegram
        with self.settings(TELEGRAM_CHAT_ID=""):
            with patch("apps.accounts.tasks.requests.post") as mock_post:
                _send_telegram("Should not send")
                mock_post.assert_not_called()

    def test_html_tags_stripped(self):
        """HTML tags stripped from text before sending."""
        from apps.accounts.tasks import _send_telegram
        with patch("apps.accounts.tasks.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_post.return_value = mock_resp
            _send_telegram("<b>Bold</b> and <i>italic</i>")
            _, kwargs = mock_post.call_args
            # Green API uses 'message' key, not 'text'
            sent_text = kwargs["json"].get("message", kwargs["json"].get("text", ""))
            self.assertEqual(sent_text, "Bold and italic")

    @override_settings(
        GREEN_API_TG_INSTANCE_ID="",
        GREEN_API_TG_TOKEN="",
    )
    def test_no_green_api_creds_uses_bot_api(self):
        """No Green API credentials -> uses Bot API directly."""
        from apps.accounts.tasks import _send_telegram
        with patch("apps.accounts.tasks.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_post.return_value = mock_resp
            _send_telegram("Bot only")
            mock_post.assert_called_once()
            args, _ = mock_post.call_args
            self.assertIn("api.telegram.org", args[0])


# ===========================================================================
# 2. _send_google_sheets
# ===========================================================================

class SendGoogleSheetsTests(TestCase):

    @override_settings(
        GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"test","client_email":"test@test.iam.gserviceaccount.com","token_uri":"https://oauth2.googleapis.com/token","private_key":"-----BEGIN RSA PRIVATE KEY-----\\nMIIBogIBAAJBALRiMLAH...fake...\\n-----END RSA PRIVATE KEY-----\\n"}',
        GOOGLE_SHEET_ID="test-sheet-id",
    )
    def test_gspread_success(self):
        """gspread writes data and returns without fallback."""
        from apps.accounts.tasks import _send_google_sheets
        mock_gc = MagicMock()
        mock_sh = MagicMock()
        mock_ws = MagicMock()
        mock_gc.open_by_key.return_value = mock_sh
        mock_sh.worksheet.return_value = mock_ws

        with patch("google.oauth2.service_account.Credentials.from_service_account_info") as mock_creds, \
             patch("gspread.authorize", return_value=mock_gc) as mock_auth, \
             patch("apps.accounts.tasks.requests.post") as mock_http:
            mock_creds.return_value = MagicMock()
            _send_google_sheets(
                "test@example.com", "TestCo", "01.01.2025",
                display_name="John", telegram="@john", employee_count=5,
            )
            mock_ws.append_row.assert_called_once()
            row = mock_ws.append_row.call_args[0][0]
            self.assertEqual(row[0], "01.01.2025")
            self.assertEqual(row[1], "John")
            self.assertEqual(row[2], "test@example.com")
            mock_http.assert_not_called()

    @override_settings(GOOGLE_SERVICE_ACCOUNT_JSON="", GAS_URL="https://example.com/gas")
    def test_no_gspread_creds_falls_back_to_gas(self):
        """No gspread credentials -> GAS webhook is called."""
        from apps.accounts.tasks import _send_google_sheets
        with patch("apps.accounts.tasks.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "OK"
            mock_post.return_value = mock_resp
            _send_google_sheets("test@example.com", "TestCo", "01.01.2025")
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertIn("action", kwargs["json"])
            self.assertEqual(kwargs["json"]["email"], "test@example.com")

    @override_settings(
        GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"test"}',
        GOOGLE_SHEET_ID="test-sheet-id",
        GAS_URL="https://example.com/gas",
    )
    def test_gspread_exception_falls_back_to_gas(self):
        """gspread raises exception -> falls back to GAS."""
        from apps.accounts.tasks import _send_google_sheets
        with patch("gspread.authorize", side_effect=Exception("auth failed")):
            with patch("apps.accounts.tasks.requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.text = "OK"
                mock_post.return_value = mock_resp
                _send_google_sheets("test@example.com", "TestCo", "01.01.2025")
                mock_post.assert_called_once()


# ===========================================================================
# 3. notify_new_registration
# ===========================================================================

@override_settings(
    TELEGRAM_BOT_TOKEN="fake-bot-token",
    TELEGRAM_CHAT_ID="123456",
)
class NotifyNewRegistrationTests(TestCase):

    def test_calls_telegram_and_sheets(self):
        """notify_new_registration calls both _send_telegram and _send_google_sheets."""
        from apps.accounts.tasks import notify_new_registration
        with patch("apps.accounts.tasks._send_telegram") as mock_tg, \
             patch("apps.accounts.tasks._send_google_sheets") as mock_gs:
            notify_new_registration(
                email="new@co.com",
                company_name="NewCo",
                registered_at="01.01.2025",
                display_name="Иван",
                telegram="@ivan",
                employee_count=10,
            )
            mock_tg.assert_called_once()
            mock_gs.assert_called_once_with(
                "new@co.com", "NewCo", "01.01.2025", "Иван", "@ivan", 10,
            )


# ===========================================================================
# 4. send_verification_email
# ===========================================================================

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@kadrovik.ru",
)
class SendVerificationEmailTests(TestCase):

    def test_sends_email(self):
        """send_verification_email sends HTML email with verify link."""
        user = _create_user()
        from apps.accounts.tasks import send_verification_email
        with patch(
            "apps.accounts.tasks.render_to_string",
            return_value="<html>Verify: http://example.com/verify/123/</html>",
        ):
            send_verification_email(user.id, "http://example.com/verify/123/")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("Подтвердите email", msg.subject)
        self.assertEqual(msg.to, [user.email])

    def test_nonexistent_user_does_nothing(self):
        """send_verification_email with non-existent user_id does nothing."""
        from apps.accounts.tasks import send_verification_email
        send_verification_email(99999, "http://example.com/verify/123/")
        self.assertEqual(len(mail.outbox), 0)


# ===========================================================================
# 5. send_password_reset_email
# ===========================================================================

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@kadrovik.ru",
)
class SendPasswordResetEmailTests(TestCase):

    def test_sends_reset_email(self):
        """send_password_reset_email sends HTML email."""
        from apps.accounts.tasks import send_password_reset_email
        send_password_reset_email("user@example.com", "http://example.com/reset/abc/")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("Сброс пароля", msg.subject)
        self.assertEqual(msg.to, ["user@example.com"])


# ===========================================================================
# 6. send_verification_email_pending
# ===========================================================================

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@kadrovik.ru",
)
class SendVerificationEmailPendingTests(TestCase):

    def test_sends_email_without_user_in_db(self):
        """Sends verification email to address not yet in DB."""
        from apps.accounts.tasks import send_verification_email_pending
        with patch(
            "apps.accounts.tasks.render_to_string",
            return_value="<html>Link</html>",
        ):
            send_verification_email_pending("new@example.com", "http://example.com/verify/123/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])


# ===========================================================================
# 7. User model tests
# ===========================================================================

class UserModelTests(TestCase):

    def test_create_user(self):
        """User created with correct fields."""
        user = _create_user(email="model@test.com")
        self.assertEqual(user.email, "model@test.com")
        self.assertFalse(user.email_verified)
        self.assertTrue(user.check_password("TestPass123!"))

    def test_email_unique(self):
        """Duplicate email raises IntegrityError."""
        from django.db import IntegrityError
        _create_user(email="dup@test.com")
        with self.assertRaises(IntegrityError):
            _create_user(email="dup@test.com")

    def test_str_returns_email(self):
        user = _create_user(email="str@test.com")
        self.assertEqual(str(user), "str@test.com")

    def test_username_field_is_email(self):
        self.assertEqual(User.USERNAME_FIELD, "email")

    def test_email_verified_default_false(self):
        user = _create_user(email="unverified@test.com")
        self.assertFalse(user.email_verified)

    def test_set_email_verified(self):
        user = _create_user(email="verify@test.com")
        user.email_verified = True
        user.save()
        user.refresh_from_db()
        self.assertTrue(user.email_verified)


# ===========================================================================
# 8. EmailVerification model tests
# ===========================================================================

class EmailVerificationModelTests(TestCase):

    def test_create_verification(self):
        """EmailVerification creates with UUID token."""
        from apps.accounts.models import EmailVerification
        from django.utils import timezone
        from datetime import timedelta
        user = _create_user(email="ev@test.com")
        ev = EmailVerification.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        self.assertIsNotNone(ev.token)
        self.assertEqual(str(ev), f"EmailVerification(ev@test.com)")

    def test_verification_token_is_unique(self):
        """Two verifications get different tokens."""
        from apps.accounts.models import EmailVerification
        from django.utils import timezone
        from datetime import timedelta
        u1 = _create_user(email="ev1@test.com")
        u2 = _create_user(email="ev2@test.com")
        ev1 = EmailVerification.objects.create(user=u1, expires_at=timezone.now() + timedelta(hours=24))
        ev2 = EmailVerification.objects.create(user=u2, expires_at=timezone.now() + timedelta(hours=24))
        self.assertNotEqual(ev1.token, ev2.token)
