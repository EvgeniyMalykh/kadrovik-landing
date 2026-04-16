# Кадровый автопилот

> HR-автоматизация для малого бизнеса России: кадровые документы, табель, отпуска, подписка.

**Сайт:** [kadrovik-auto.ru](https://kadrovik-auto.ru)  
**Приложение:** [app.kadrovik-auto.ru](https://app.kadrovik-auto.ru)

---

## Стек технологий

| Слой | Технология |
|------|-----------|
| Backend | Python 3.11, Django 5.x |
| Task queue | Celery + Redis |
| БД | PostgreSQL 16 |
| Frontend | HTMX, Alpine.js, Tailwind CSS |
| Деплой | Docker Compose (production) |
| Веб-сервер | Nginx + Gunicorn |
| Email | Яндекс.360 SMTP → Redis relay → systemd |
| Оплата | ЮKassa (инфраструктура готова, ключи не настроены) |
| Уведомления | Telegram Bot API (@kadrovik_leads_bot) |
| Аналитика | Google Apps Script → Google Sheets |

---

## Архитектура

```
kadrovik-auto.ru (Nginx) ──► /var/www/kadrovik-landing/   (лендинг, статика)
app.kadrovik-auto.ru     ──► Docker: kadrovik-web-1:8000   (Django/Gunicorn)
                                      kadrovik-db-1          (PostgreSQL 16)
                                      kadrovik-redis-1       (Redis 7)
                                      kadrovik-celery-1      (Celery worker)
                                      kadrovik-celery-beat-1 (Celery beat)

Email relay: systemd email_relay.service (/root/email_relay.py)
  Django → Redis db=2 (queue) → email_relay.py → smtp.yandex.ru:587
```

---

## Структура приложений (apps/)

| Приложение | Назначение |
|-----------|-----------|
| `accounts` | Регистрация, email-верификация, смена/сброс пароля |
| `companies` | Профиль организации (ИНН, наименование, адрес, подпись) |
| `employees` | Сотрудники: приём, увольнение, отпуска, персональные данные |
| `documents` | Генерация кадровых документов (Т-1, Т-2, Т-5, Т-6, Т-8, Т-13, ГПХ, справки) |
| `billing` | Подписки, платежи ЮKassa, тарифные планы |
| `events` | Celery-задачи: уведомления об истечении подписки |
| `dashboard` | Главный интерфейс, формы, чат поддержки, табель |
| `vacations` | Журнал отпусков + публичная форма заявки для сотрудников |

---

## Тарифные планы

| Тариф | Цена | Сотрудников |
|-------|------|------------|
| Старт | 790 ₽/мес | до 10 |
| Бизнес | 1 990 ₽/мес | до 50 |
| Корпоратив | 4 900 ₽/мес | неограниченно |

Пробный период: **7 дней бесплатно** при регистрации.

---

## Кадровые документы

Приложение генерирует следующие документы (DOCX/PDF):

- **Т-1** — приказ о приёме на работу
- **Т-2** — личная карточка сотрудника
- **Т-5** — приказ о переводе
- **Т-6** — приказ об отпуске
- **Т-8** — приказ об увольнении
- **Т-13** — табель учёта рабочего времени (на всю компанию)
- **Трудовой договор** — по шаблону
- **Договор ГПХ + Акт** — для подрядчиков
- **Справка с места работы** — произвольная форма
- **Приказ об изменении оклада**

### Раздел «Формы» (редактор)

Доступен через левое меню → **Формы**. Позволяет:
- Выбрать шаблон (отпуск, ГПХ, Акт ГПХ, справка, оклад)
- Выбрать сотрудника — поля заполняются автоматически из БД
- Отредактировать нужные поля
- Сохранить документ в журнал
- Распечатать через браузер

---

## URL-маршруты

### Аутентификация
```
/dashboard/login/                   — вход
/dashboard/register/                — регистрация
/dashboard/logout/                  — выход
/dashboard/forgot-password/         — сброс пароля
/dashboard/reset-password/<token>/  — новый пароль по токену
/dashboard/change-password/         — смена пароля
/dashboard/verify-email/<token>/    — подтверждение email
/dashboard/resend-verification/     — повторная отправка письма
```

### Основной дашборд
```
/dashboard/                         — главная
/dashboard/employees/               — список сотрудников
/dashboard/employees/add/           — добавить сотрудника
/dashboard/employees/<id>/edit/     — редактировать
/dashboard/employees/<id>/delete/   — удалить
/dashboard/company/                 — профиль организации
/dashboard/subscription/            — подписка и тарифы
/dashboard/timesheet/               — табель (редактирование)
```

### Кадровые документы (генерация)
```
/dashboard/employees/<id>/t1/               — приказ Т-1
/dashboard/employees/<id>/t2/               — карточка Т-2
/dashboard/employees/<id>/t5/               — перевод Т-5
/dashboard/employees/<id>/t6/               — отпуск Т-6
/dashboard/employees/<id>/t8/               — увольнение Т-8
/dashboard/employees/<id>/salary-change/    — смена оклада
/dashboard/employees/<id>/certificate/      — справка
/dashboard/employees/<id>/labor-contract/   — трудовой договор
/dashboard/employees/<id>/gph-contract/     — договор ГПХ
/dashboard/employees/<id>/gph-act/          — акт ГПХ
/dashboard/t13/                             — табель Т-13 (вся компания)
```

### Формы (журнал + редактор)
```
/dashboard/forms/                        — журнал документов
/dashboard/forms/<doc_type>/             — редактор формы
/dashboard/forms/<doc_type>/save/        — сохранение
/dashboard/forms/api/employee/<id>/      — API: данные сотрудника (JSON)
```

### Отпуска
```
/vacations/                              — журнал отпусков
/vacations/request/                      — публичная форма заявки (без логина)
```

### Чат поддержки
```
/dashboard/chat-support/   — отправка сообщения клиентом
/dashboard/chat-history/   — история переписки (JSON)
/dashboard/chat-webhook/   — webhook Telegram (ответы оператора)
/dashboard/chat-poll/      — polling новых сообщений клиентом
```

### Оплата
```
/dashboard/checkout/<plan>/         — страница оплаты
/dashboard/payment/success/         — успешная оплата
/dashboard/webhook/yukassa/         — webhook ЮKassa
```

### API
```
/api/v1/employees/                  — REST API сотрудников
/documents/t1/<id>/                 — скачать Т-1 (legacy)
/admin/                             — Django Admin
```

---

## Email

Email отправляется через **Redis relay** (не напрямую из Django):

1. Django пишет письмо в Redis `db=2`, ключ `email_relay_queue`
2. `email_relay.py` (systemd) читает очередь и отправляет через `smtp.yandex.ru:587`

```bash
# Статус relay
systemctl status email_relay

# Логи
journalctl -u email_relay -n 50
```

Типы писем:
- Подтверждение email при регистрации
- Сброс пароля
- Уведомление об истечении подписки (за 3 дня и за 1 день)

---

## Telegram-бот (@kadrovik_leads_bot)

Бот выполняет две функции:

### 1. Лиды с лендинга
Каждая новая регистрация → уведомление в Telegram с именем, email, количеством сотрудников.

### 2. Чат поддержки
- Клиент пишет в виджет на сайте → сообщение приходит в бот с `[session_id]`
- Оператор делает **Reply** на сообщение → ответ уходит клиенту в браузер
- История хранится в Redis `db=3` (7 дней)
- Команда `/чаты` — список активных сессий с email и последним сообщением

Webhook зарегистрирован: `https://app.kadrovik-auto.ru/dashboard/chat-webhook/`

---

## ЮKassa (оплата)

Инфраструктура подготовлена, ключи ещё не подключены.

После получения ключей в [yookassa.ru → Интеграция → API-ключи](https://yookassa.ru):

```python
# config/settings/production.py
YUKASSA_SHOP_ID = "ваш_shop_id"
YUKASSA_SECRET_KEY = "ваш_секретный_ключ"
```

Webhook URL для ЮKassa: `https://app.kadrovik-auto.ru/dashboard/webhook/yukassa/`

---

## Google Sheets (аналитика регистраций)

Каждая новая регистрация → запись в Google Таблицу через GAS.

Колонки: `Дата | Имя | Email | Telegram | Сотрудников | Источник`

GAS URL задаётся в `.env`:
```
GAS_URL=https://script.google.com/macros/s/.../exec
```

---

## Деплой на VPS

**Сервер:** Timeweb Cloud, Ubuntu 22.04, IP: 109.73.207.33  
**Проект:** `/root/kadrovik/`

### Запуск / перезапуск
```bash
cd /root/kadrovik
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml restart web
```

### КРИТИЧНО: обновление файлов в контейнере

Контейнеры пересобираются из образа при restart. Поэтому после изменения Python-файлов или шаблонов нужно **вручную скопировать** их в работающие контейнеры:

```bash
# Пример: обновить views.py
docker cp apps/dashboard/views.py kadrovik-web-1:/app/apps/dashboard/views.py
docker cp apps/dashboard/views.py kadrovik-celery-1:/app/apps/dashboard/views.py

# Перезапуск после копирования
docker compose -f docker-compose.production.yml restart web
```

Файлы которые требуют копирования после изменения:
- `apps/accounts/models.py`, `tasks.py`, `views.py`
- `apps/dashboard/views.py`, `urls.py`
- `apps/billing/views.py`, `services.py`, `urls.py`
- `apps/events/tasks.py`
- `config/urls.py`, `settings/production.py`
- Все шаблоны `templates/**/*.html`

### Статические файлы

```bash
# После изменения CSS
cp /root/kadrovik/static/css/dashboard.css /root/kadrovik/staticfiles/css/dashboard.css

# Nginx раздаёт staticfiles напрямую (без Django)
```

---

## Переменные окружения (.env)

```env
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=app.kadrovik-auto.ru,109.73.207.33

DB_NAME=kadrovik
DB_USER=kadrovik
DB_PASSWORD=
DB_HOST=db
DB_PORT=5432

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

GAS_URL=

EMAIL_HOST_USER=zhenyamalykh@yandex.ru
EMAIL_HOST_PASSWORD=

# После подключения ЮKassa:
# YUKASSA_SHOP_ID=
# YUKASSA_SECRET_KEY=
```

---

## Локальная разработка

```bash
git clone https://github.com/EvgeniyMalykh/kadrovik-landing.git
cd kadrovik-landing

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Заполнить .env

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Git-репозиторий

```
https://github.com/EvgeniyMalykh/kadrovik-landing
```

Основная ветка: `main`

---

## Администрирование

- **Django Admin:** https://app.kadrovik-auto.ru/admin/
- **Логи приложения:** `/var/log/kadrovik/`
- **Логи email relay:** `journalctl -u email_relay`
- **Логи Nginx:** `/var/log/nginx/`

```bash
# Просмотр логов контейнеров
docker logs kadrovik-web-1 --tail 50
docker logs kadrovik-celery-1 --tail 50

# Вход в контейнер
docker exec -it kadrovik-web-1 bash

# Django shell
docker exec -it kadrovik-web-1 python manage.py shell
```

---

## Лицензия

Частная разработка. Все права защищены.
