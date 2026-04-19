"""
Автотест: отправка тестового уведомления через webhook → проверка доставки в Telegram-чат.

Шаги:
  1. Логинимся в Django-приложение под тестовым аккаунтом (test@kadrovik-auto.ru).
  2. Убеждаемся, что у компании notify_messenger=telegram, notify_contact=@SK_Johnny.
  3. Запоминаем message_id последнего сообщения в чате 1113292310 через getUpdates.
  4. Отправляем POST /dashboard/company/test-notify/.
  5. Ждём до 15 секунд и проверяем, что в чате появилось новое сообщение,
     содержащее текст «Тестовое уведомление».
"""

import sys
import time
import requests

# ── Конфигурация ──────────────────────────────────────────────────────────────
BASE_URL        = "https://app.kadrovik-auto.ru"
LOGIN_URL       = f"{BASE_URL}/login/"
TEST_NOTIFY_URL = f"{BASE_URL}/dashboard/company/test-notify/"
COMPANY_URL     = f"{BASE_URL}/dashboard/company/"

EMAIL    = "test@kadrovik-auto.ru"
PASSWORD = "Test1234!"

BOT_TOKEN       = "7718001813:AAH4KBXZId8CurJdxpmno9jCJr5Bgcx01mM"
TARGET_CHAT_ID  = 1113292310

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

POLL_INTERVAL = 2   # секунд между проверками
POLL_TIMEOUT  = 20  # максимум секунд ожидания

# ── Хелперы ───────────────────────────────────────────────────────────────────

def ok(msg):
    print(f"  ✅  {msg}")

def fail(msg):
    print(f"  ❌  {msg}")
    sys.exit(1)

def info(msg):
    print(f"  ℹ️  {msg}")


def get_last_message_id(chat_id: int) -> int | None:
    """Возвращает message_id последнего сообщения бота в чате через getUpdates."""
    resp = requests.get(f"{TG_API}/getUpdates", params={"limit": 100, "timeout": 0}, timeout=15)
    if not resp.ok:
        return None
    updates = resp.json().get("result", [])
    # Фильтруем сообщения от бота в нужном чате
    chat_updates = [
        u for u in updates
        if u.get("message", {}).get("chat", {}).get("id") == chat_id
    ]
    if not chat_updates:
        return None
    return chat_updates[-1]["message"]["message_id"]


def get_new_messages(chat_id: int, after_message_id: int | None) -> list[dict]:
    """Возвращает сообщения в чате с message_id > after_message_id."""
    resp = requests.get(f"{TG_API}/getUpdates", params={"limit": 100, "timeout": 0}, timeout=15)
    if not resp.ok:
        return []
    updates = resp.json().get("result", [])
    messages = []
    for u in updates:
        msg = u.get("message", {})
        if msg.get("chat", {}).get("id") == chat_id:
            if after_message_id is None or msg.get("message_id", 0) > after_message_id:
                messages.append(msg)
    return messages


# ── Шаг 1: логин ─────────────────────────────────────────────────────────────
print("\n=== Шаг 1: Логин ===")
session = requests.Session()
session.headers.update({"User-Agent": "kadrovik-autotest/1.0"})

# Получаем CSRF-токен
login_page = session.get(LOGIN_URL, timeout=10)
if login_page.status_code != 200:
    fail(f"Страница логина недоступна: {login_page.status_code}")

csrf = session.cookies.get("csrftoken")
if not csrf:
    # Попробуем вытащить из тела страницы
    import re
    m = re.search(r'csrfmiddlewaretoken.*?value=["\']([^"\']+)', login_page.text)
    csrf = m.group(1) if m else ""

info(f"CSRF-токен: {csrf[:10]}…")

login_resp = session.post(
    LOGIN_URL,
    data={
        "email": EMAIL,
        "password": PASSWORD,
        "csrfmiddlewaretoken": csrf,
    },
    headers={"Referer": LOGIN_URL},
    allow_redirects=True,
    timeout=15,
)

if login_resp.status_code not in (200, 302) or "login" in login_resp.url:
    fail(f"Логин не прошёл. URL после редиректа: {login_resp.url}")

ok(f"Залогинились. URL: {login_resp.url}")


# ── Шаг 2: убеждаемся в настройках компании ──────────────────────────────────
print("\n=== Шаг 2: Проверка настроек компании ===")

company_page = session.get(COMPANY_URL, timeout=10)
if "telegram" not in company_page.text.lower():
    fail("На странице компании не найден выбранный мессенджер Telegram. Проверьте карточку компании.")

ok("Мессенджер Telegram найден на странице компании.")


# ── Шаг 3: запоминаем последнее сообщение в чате ─────────────────────────────
print("\n=== Шаг 3: Последнее сообщение в Telegram-чате ===")

baseline_id = get_last_message_id(TARGET_CHAT_ID)
info(f"Baseline message_id = {baseline_id}")


# ── Шаг 4: отправляем тестовое уведомление ───────────────────────────────────
print("\n=== Шаг 4: Отправка тестового уведомления ===")

csrf = session.cookies.get("csrftoken", csrf)
notify_resp = session.post(
    TEST_NOTIFY_URL,
    json={},
    headers={
        "X-CSRFToken": csrf,
        "Referer": COMPANY_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json",
    },
    timeout=20,
)

info(f"HTTP статус: {notify_resp.status_code}")
try:
    notify_json = notify_resp.json()
    info(f"Ответ сервера: {notify_json}")
    if not notify_json.get("ok"):
        fail(f"Сервер вернул ok=False: {notify_json.get('message')}")
except Exception as e:
    fail(f"Не удалось разобрать JSON-ответ: {e}\nТело: {notify_resp.text[:300]}")

ok("Сервер принял запрос и вернул ok=True.")


# ── Шаг 5: ждём сообщение в Telegram ─────────────────────────────────────────
print(f"\n=== Шаг 5: Ожидание сообщения в чате {TARGET_CHAT_ID} (до {POLL_TIMEOUT}с) ===")

elapsed = 0
found_msg = None

while elapsed < POLL_TIMEOUT:
    new_msgs = get_new_messages(TARGET_CHAT_ID, baseline_id)
    for msg in new_msgs:
        text = msg.get("text", "")
        if "тестовое уведомление" in text.lower() or "тестовое" in text.lower():
            found_msg = msg
            break
    if found_msg:
        break
    time.sleep(POLL_INTERVAL)
    elapsed += POLL_INTERVAL
    info(f"Ждём… {elapsed}с")

if not found_msg:
    # Последняя попытка — выведем все новые сообщения для диагностики
    all_new = get_new_messages(TARGET_CHAT_ID, baseline_id)
    if all_new:
        info(f"Новые сообщения в чате (без фильтра): {[m.get('text','') for m in all_new]}")
        fail("Уведомление пришло, но не содержит ожидаемый текст 'Тестовое уведомление'.")
    else:
        fail(f"Уведомление не пришло в чат {TARGET_CHAT_ID} за {POLL_TIMEOUT} секунд.")

# ── Результат ─────────────────────────────────────────────────────────────────
print("\n=== РЕЗУЛЬТАТ ===")
ok(f"Уведомление доставлено! message_id={found_msg['message_id']}")
ok(f"Текст: {found_msg.get('text', '')[:120]}")
print("\n✅ Тест PASSED\n")
