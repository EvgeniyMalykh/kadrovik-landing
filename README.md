# Кадровый автопилот

> HR-автоматизация для малого бизнеса России: кадровые документы, табель, отпуска, подписка.

**Сайт:** [kadrovik-auto.ru](https://www.kadrovik-auto.ru)  
**Приложение:** [app.kadrovik-auto.ru](https://app.kadrovik-auto.ru)

---

## Стек технологий

| Слой | Технология |
|------|-----------|
| Backend | Python 3.12, Django 5.x |
| Task queue | Celery + Redis |
| БД | PostgreSQL 16 |
| Frontend | HTMX, vanilla JS, CSS custom |
| Деплой | Docker Compose (production) |
| Веб-сервер | Nginx + Gunicorn |
| Email | Gmail SMTP (smtp.gmail.com:587) |
| Оплата | ЮKassa (подключена, webhook активен) |
| Уведомления | Telegram Bot API (@kadrovik_leads_bot) |
| Аналитика | Google Apps Script → Google Sheets + Яндекс.Метрика (ID: 108635022) |
| SEO | Яндекс.Вебмастер, sitemap.xml, Schema.org, OG-теги |

---

## Архитектура

```
www.kadrovik-auto.ru (Nginx) ──► /var/www/kadrovik-landing/   (лендинг, статика)
app.kadrovik-auto.ru         ──► Docker: kadrovik-web-1:8000   (Django/Gunicorn)
                                          kadrovik-db-1          (PostgreSQL 16)
                                          kadrovik-redis-1       (Redis 7)
                                          kadrovik-celery-1      (Celery worker)
                                          kadrovik-celery-beat-1 (Celery beat)

Nginx: kadrovik-auto.ru (без www) → 301 → www.kadrovik-auto.ru
SSL: Let's Encrypt, действует до 2026-07-14, HSTS включён
```

---

## Структура приложений (apps/)

| Приложение | Назначение |
|-----------|-----------|
| `accounts` | Регистрация, email-верификация, смена/сброс пароля |
| `companies` | Профиль организации (ИНН, наименование, адрес, подпись) |
| `employees` | Сотрудники: приём, увольнение, персональные данные, производственный календарь |
| `documents` | Генерация кадровых документов (Т-1, Т-2, Т-5, Т-6, Т-8, Т-13, ГПХ, справки) |
| `billing` | Подписки, платежи ЮKassa, вебхук, тарифные планы |
| `events` | Celery-задачи: уведомления об истечении подписки |
| `dashboard` | Главный интерфейс, формы, чат поддержки, табель |
| `vacations` | Журнал отпусков + публичная форма заявки для сотрудников |

---

## Тарифные планы

| Тариф | Цена | Сотрудников |
|-------|------|------------|
| Пробный | бесплатно | до 50 (7 дней) |
| Старт | 790 ₽/мес | до 10 |
| Бизнес | 1 990 ₽/мес | до 50 |
| Корпоратив | 4 900 ₽/мес | до 200 |

Пробный период: **7 дней бесплатно** при регистрации.  
После истечения trial — блокировка с редиректом на `/dashboard/subscription/`.

---

## Кадровые документы

Приложение генерирует следующие документы (PDF):

- **Т-1** — приказ о приёме на работу
- **Т-2** — личная карточка сотрудника
- **Т-5** — приказ о переводе
- **Т-6** — приказ об отпуске (с выбором вида: ежегодный / дополнительный / без сохранения з/п)
- **Т-8** — приказ об увольнении
- **Т-13** — табель учёта рабочего времени (норма часов по производственному календарю РФ)
- **Трудовой договор**
- **Договор ГПХ + Акт**
- **Справка с места работы**
- **Приказ об изменении оклада**
- **Заявление на дополнительный оплачиваемый отпуск**
- **Приказ о премировании**
- **Приказ о дисциплинарном взыскании**

### Коды табеля (Т-13)

`Я` `ОТ` `ОД` `УЧ` `ОЖ` `Б` `К` `НН` `П` `В` `Я½` `РВ` `Я/С`

### Производственный календарь РФ

Норма рабочих дней и часов рассчитывается автоматически на основе модели `ProductionCalendar`:
- Учитываются праздничные и предпраздничные дни
- Данные на 2025–2026 гг. заведены в БД

---

## Виды отпусков

| Код | Тип |
|-----|-----|
| `annual` | Ежегодный оплачиваемый |
| `additional` | Дополнительный оплачиваемый (ОД) |
| `unpaid` | Без сохранения заработной платы |
| `educational` | Учебный (УЧ) |
| `maternity` | По беременности и родам (ОЖ) |

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
```

### Основной дашборд
```
/dashboard/employees/               — список сотрудников
/dashboard/employees/add/           — добавить сотрудника
/dashboard/employees/<id>/edit/     — редактировать
/dashboard/employees/<id>/delete/   — удалить
/dashboard/company/                 — профиль организации
/dashboard/subscription/            — подписка и тарифы
/dashboard/timesheet/               — табель (редактирование)
/dashboard/t13/                     — табель Т-13 (печать/скачать)
/dashboard/team/                    — управление командой
/dashboard/events/                  — события и уведомления
```

### Кадровые документы (генерация PDF)
```
/dashboard/employees/<id>/t1/               — приказ Т-1
/dashboard/employees/<id>/t2/               — карточка Т-2
/dashboard/employees/<id>/t5/               — перевод Т-5
/dashboard/employees/<id>/t6/               — отпуск Т-6 (?start=&end=&order=&vtype=)
/dashboard/employees/<id>/t8/               — увольнение Т-8
/dashboard/employees/<id>/salary-change/    — смена оклада
/dashboard/employees/<id>/certificate/      — справка
/dashboard/employees/<id>/labor-contract/   — трудовой договор
/dashboard/employees/<id>/gph-contract/     — договор ГПХ
/dashboard/employees/<id>/gph-act/          — акт ГПХ
/dashboard/employees/<id>/transfer-order/   — приказ о переводе
/dashboard/employees/<id>/dismissal-order/  — приказ об увольнении
/dashboard/employees/<id>/bonus-order/      — приказ о премии
/dashboard/employees/<id>/disciplinary-order/ — дисц. взыскание
```

### Отпуска
```
/vacations/                              — журнал отпусков
/vacations/request/                      — публичная форма заявки (без логина)
/vacations/<id>/additional-pdf/          — PDF заявления на доп. отпуск
/vacations/schedule/                     — график отпусков
```

### Формы (журнал + редактор)
```
/dashboard/forms/                        — журнал документов
/dashboard/forms/<doc_type>/             — редактор формы
/dashboard/forms/<doc_type>/save/        — сохранение
/dashboard/forms/api/employee/<id>/      — API: данные сотрудника (JSON)
```

### Оплата (ЮKassa)
```
/dashboard/checkout/<plan>/         — страница оплаты (start/business/pro)
/dashboard/payment/success/         — успешная оплата
/dashboard/webhook/yukassa/         — webhook ЮKassa (payment.succeeded)
/billing/cancel-autorenew/          — отменить автопродление
```

### Чат поддержки
```
/dashboard/chat-support/   — отправка сообщения клиентом
/dashboard/chat-history/   — история переписки (JSON)
/dashboard/chat-webhook/   — webhook Telegram (ответы оператора)
/dashboard/chat-poll/      — polling новых сообщений
```

### API
```
/api/v1/employees/                  — REST API сотрудников
/admin/                             — Django Admin
```

---

## Оплата (ЮKassa)

Платежи полностью интегрированы:

- `shopId`: настроен в `production.py`
- `secret_key`: настроен в `production.py`
- Webhook URL: `https://app.kadrovik-auto.ru/dashboard/webhook/yukassa/`
- После `payment.succeeded` → активируется подписка + отправляется email владельцу
- Автоплатежи: fallback (если `save_payment_method` отклонён ЮKassa — создаётся обычный платёж)

---

## Email

Письма отправляются через **Gmail SMTP** напрямую из Django:

```
smtp.gmail.com:587, TLS
From: evgeniymalykh@gmail.com
```

Типы писем:
- Подтверждение email при регистрации
- Сброс пароля
- Уведомление об активации подписки (после оплаты)
- Уведомление об истечении подписки (за 3 дня и за 1 день, Celery)

---

## Мобильная версия

Сервис полностью адаптирован под мобильные устройства:

- Сайдбар — гамбургер-меню (slide-in)
- Сотрудники, Отпуска, Команда, Журнал документов — мобильные карточки вместо таблиц
- Дравер (форма сотрудника) — полноэкранный на телефоне
- Кнопки создания документов — адаптивная сетка
- Все формы — одна колонка на мобильном
- CSS версия: `dashboard.css?v=13`

---

## SEO и аналитика

- **Яндекс.Вебмастер:** сайт подтверждён как `https://www.kadrovik-auto.ru`
- **Редирект:** `kadrovik-auto.ru` → `www.kadrovik-auto.ru` (301, настроен в Nginx)
- **Яндекс.Метрика:** счётчик `108635022` (лендинг + приложение)
- **sitemap.xml:** `/var/www/kadrovik-landing/sitemap.xml`
- **robots.txt:** с `Host:` и `Sitemap:`
- **Schema.org:** `SoftwareApplication`, `FAQPage`, `SiteNavigationElement`
- **Open Graph:** og:image 1200×630 (`/var/www/kadrovik-landing/og-image.png`)
- **Favicon:** `К` + шестерёнка, тёмно-синий

---

## Telegram-бот (@kadrovik_leads_bot)

### 1. Лиды с лендинга
Каждая новая регистрация → уведомление в Telegram.

### 2. Чат поддержки
- Клиент пишет в виджет → сообщение приходит в бот с `[session_id]`
- Оператор делает **Reply** → ответ уходит клиенту в браузер
- История хранится в Redis `db=3` (7 дней)
- Команда `/чаты` — список активных сессий

Webhook: `https://app.kadrovik-auto.ru/dashboard/chat-webhook/`

---

## Деплой на VPS

**Сервер:** Timeweb Cloud, Ubuntu 22.04, IP: `109.73.207.33`  
**Проект:** `/root/kadrovik/`

### Запуск / перезапуск
```bash
cd /root/kadrovik
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml restart web
```

### КРИТИЧНО: обновление файлов в контейнере

Контейнеры поднимаются из образа при restart. После изменения файлов нужно **скопировать их в ВСЕ контейнеры**:

```bash
# Шаблон (пример)
docker cp templates/dashboard/employees.html kadrovik-web-1:/app/templates/dashboard/employees.html
docker cp templates/dashboard/employees.html kadrovik-celery-1:/app/templates/dashboard/employees.html
docker cp templates/dashboard/employees.html kadrovik-celery-beat-1:/app/templates/dashboard/employees.html

# Python-файл (пример)
docker cp apps/billing/views.py kadrovik-web-1:/app/apps/billing/views.py
docker cp apps/billing/views.py kadrovik-celery-1:/app/apps/billing/views.py
docker cp apps/billing/views.py kadrovik-celery-beat-1:/app/apps/billing/views.py
```

### Статические файлы (CSS)
```bash
# После изменения dashboard.css
docker cp static/css/dashboard.css kadrovik-web-1:/app/static/css/dashboard.css
# Обновить версию в base.html: dashboard.css?v=XX
```

---

## Переменные окружения (.env)

```env
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=app.kadrovik-auto.ru,109.73.207.33

DB_NAME=kadrovik_db
DB_USER=kadrovik_user
DB_PASSWORD=
DB_HOST=db
DB_PORT=5432

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

GAS_URL=

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=

YUKASSA_SHOP_ID=
YUKASSA_SECRET_KEY=
```

---

## Локальная разработка

```bash
git clone https://github.com/EvgeniyMalykh/kadrovik-landing.git
cd kadrovik-landing

python -m venv venv
source venv/bin/activate
pip install -r requirements/base.txt

cp .env.example .env
# Заполнить .env

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Администрирование

- **Django Admin:** https://app.kadrovik-auto.ru/admin/
- **Логи приложения:** `docker logs kadrovik-web-1 --tail 100`
- **Логи Celery:** `docker logs kadrovik-celery-1 --tail 50`
- **Логи Nginx:** `/var/log/nginx/`

```bash
# Вход в контейнер
docker exec -it kadrovik-web-1 bash

# Django shell
docker exec -it kadrovik-web-1 python manage.py shell

# Применить миграции
docker exec kadrovik-web-1 python manage.py migrate
```

---

## Лицензия

Частная разработка. Все права защищены.
