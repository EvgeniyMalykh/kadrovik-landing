# 📋 Кадровый автопилот

> **SaaS для кадрового учёта малого бизнеса** — автоматизация кадровых документов, табель, отпуска, и всё это в браузере без установки ПО.

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.1-green?logo=django)](https://djangoproject.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-red?logo=redis)](https://redis.io)

**Демо:** [app.kadrovik-auto.ru](https://app.kadrovik-auto.ru) · **Лендинг:** [kadrovik-auto.ru](https://kadrovik-auto.ru)

---

## Содержание

- [О проекте](#о-проекте)
- [Функциональность](#функциональность)
- [Архитектура](#архитектура)
- [Стек технологий](#стек-технологий)
- [Структура проекта](#структура-проекта)
- [Установка и запуск](#установка-и-запуск)
- [Переменные окружения](#переменные-окружения)
- [Деплой на VPS](#деплой-на-vps)
- [Мобильная адаптация](#мобильная-адаптация)
- [API и интеграции](#api-и-интеграции)
- [Лицензия](#лицензия)

---

## О проекте

**Кадровый автопилот** — веб-приложение для автоматизации кадрового делопроизводства на предприятиях малого бизнеса РФ. Система позволяет HR-специалисту вести базу сотрудников, формировать унифицированные кадровые документы (Т-1, Т-2, Т-5, Т-6, Т-8 и др.), заполнять табель учёта рабочего времени и оформлять заявления на отпуск — всё в веб-браузере, включая мобильный.

### Тарифы

| Тариф | Цена | Сотрудников |
|-------|------|-------------|
| Старт | 790 ₽/мес | до 10 |
| Бизнес | 1 990 ₽/мес | до 50 |
| Корпорация | 4 900 ₽/мес | неограниченно |

Пробный период — **7 дней бесплатно**.

---

## Функциональность

### 👥 Управление сотрудниками
- Карточка сотрудника с полным набором реквизитов (паспорт, СНИЛС, ИНН, контакты, трудовые данные)
- Структурные подразделения (создание прямо из формы)
- Тип договора: бессрочный, срочный, ГПХ
- Испытательный срок с отслеживанием даты окончания
- Статус сотрудника: работает / уволен

### 📄 Кадровые документы (PDF)
| Документ | Описание |
|----------|----------|
| **Т-1** | Приказ о приёме на работу |
| **Т-2** | Личная карточка сотрудника |
| **Т-5** | Приказ о переводе |
| **Т-6** | Приказ о предоставлении отпуска |
| **Т-8** | Приказ о прекращении трудового договора |
| **Т-13** | Табель учёта рабочего времени |
| **ТД** | Трудовой договор |
| **ГПХ** | Договор гражданско-правового характера |
| **Акт ГПХ** | Акт выполненных работ |
| **Справка** | Справка с места работы |
| **Оклад** | Приказ об изменении оклада |

Все документы автоматически заполняются реквизитами компании и данными сотрудника.

### 📅 Табель учёта рабочего времени (Т-13)
- Интерактивная таблица на весь месяц
- Коды: Я (явка), ОТ (отпуск), ОД (доп. отпуск), Б (больничный), В (выходной)
- Левый клик — смена кода, правый клик — изменение часов
- Автоматический подсчёт итогов
- Выгрузка в PDF

### 🏖️ Заявления об отпуске
- Виды отпуска: оплачиваемый, за свой счёт, учебный, декретный
- Ввод дат с маской ДД.ММ.ГГГГ, автоподсчёт дней
- Печатная форма заявления (HTML → print)
- **Публичная форма** для работника без авторизации: `/vacations/request/<company_id>/`

### 🏢 Профиль компании
- Реквизиты: ИНН, ОГРН, КПП, ОКПО, адреса
- ФИО и должность руководителя (подставляются в документы)
- Контактные данные

### 🔐 Аутентификация
- Регистрация с подтверждением email (токен в Redis, создание аккаунта только после верификации)
- Вход по email + пароль
- Восстановление пароля через email (ссылка действительна 1 час)
- Смена пароля в профиле

### 💳 Биллинг
- Тарифные планы с лимитами по сотрудникам
- Пробный период 7 дней
- Интеграция с платёжными системами (РФ)

---

## Архитектура

```
┌─────────────────────────────────────────────────┐
│                   Nginx (reverse proxy)          │
│   kadrovik-auto.ru → лендинг (static/HTML)      │
│   app.kadrovik-auto.ru → Django (:8000)          │
│   /static/ → /root/kadrovik/staticfiles/         │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              Docker Compose                      │
│                                                  │
│  ┌──────────────┐  ┌────────────┐               │
│  │  kadrovik-   │  │ kadrovik-  │               │
│  │   web-1      │  │   db-1     │               │
│  │  (gunicorn   │  │ (postgres  │               │
│  │   :8000)     │  │    :16)    │               │
│  └──────┬───────┘  └────────────┘               │
│         │                                        │
│  ┌──────▼───────┐  ┌────────────┐               │
│  │ kadrovik-    │  │ kadrovik-  │               │
│  │  redis-1     │  │ celery-1   │               │
│  │  (redis:7)   │  │ celery-    │               │
│  └──────────────┘  │  beat-1    │               │
│                    └────────────┘               │
└─────────────────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │  email_relay.py │  (systemd, хост)
              │  Redis queue →  │
              │  SMTP Yandex    │
              └─────────────────┘
```

### Поток регистрации
```
Пользователь → форма регистрации
    ↓
Данные сохраняются в Redis (не в БД)
    ↓
Отправляется письмо с токеном (Celery → email_relay → SMTP)
    ↓
Пользователь кликает ссылку → verify-email/<uuid>/
    ↓
Создаётся User + Company + CompanyMember + Subscription(TRIAL, 7 дней)
    ↓
Уведомление в Telegram + Google Sheets
```

---

## Стек технологий

| Категория | Технология |
|-----------|-----------|
| Backend | Django 5.1, Django REST Framework |
| База данных | PostgreSQL 16 |
| Кэш / очереди | Redis 7, Celery 5.4 |
| PDF-генерация | ReportLab 4.2 |
| Frontend | HTML/CSS (кастомный design system), HTMX 1.9 |
| Контейнеризация | Docker, Docker Compose |
| Веб-сервер | Gunicorn + Nginx |
| SMTP | Яндекс.Почта (STARTTLS :587) |
| Уведомления | Telegram Bot API |
| VPS | Timeweb Cloud (Ubuntu 22.04) |
| Домен/SSL | Let's Encrypt |

---

## Структура проекта

```
kadrovik/
├── apps/
│   ├── accounts/          # Пользователи, верификация email
│   │   ├── models.py      # User (AbstractUser), EmailVerification
│   │   ├── tasks.py       # Celery: send_verification_email, notify_new_registration
│   │   └── email_backend.py
│   ├── billing/           # Подписки, тарифы, платежи
│   │   ├── models.py      # Subscription, Payment
│   │   └── services.py
│   ├── companies/         # Компании и участники
│   │   └── models.py      # Company, CompanyMember
│   ├── dashboard/         # Основной модуль: views, URLs
│   │   ├── views.py       # Все основные view (сотрудники, табель, компания, auth)
│   │   ├── urls.py
│   │   └── templatetags/  # Кастомные теги (ts_tags)
│   ├── documents/         # PDF-генерация (ReportLab)
│   │   └── services.py    # Т-1, Т-2, Т-5, Т-6, Т-8, Т-13 и др.
│   ├── employees/         # Модель сотрудников, отделы
│   │   └── models.py      # Employee, Department, TimeRecord
│   ├── events/            # События (Celery Beat)
│   └── vacations/         # Заявления об отпуске
│       ├── models.py      # Vacation (тип, даты, причина)
│       ├── views.py       # list, add, delete, print, public form
│       └── urls.py
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
├── templates/
│   ├── base.html          # Sidebar, hamburger, drawer overlay
│   ├── base_auth.html     # Базовый шаблон для auth-страниц
│   ├── dashboard/
│   │   ├── employees.html
│   │   ├── timesheet.html
│   │   ├── vacations.html
│   │   ├── vacation_print.html      # Печатная форма заявления
│   │   ├── vacation_request_form.html  # Публичная форма для работника
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── forgot_password.html
│   │   ├── reset_password.html
│   │   ├── change_password.html
│   │   └── partials/               # HTMX-фрагменты
│   └── emails/
│       └── verify_email.html
├── static/
│   └── css/
│       └── dashboard.css   # Кастомный design system (dark theme)
├── staticfiles/            # collectstatic → nginx
├── docker-compose.production.yml
├── Dockerfile
├── requirements.txt
└── email_relay.py          # SMTP-relay: Redis queue → Yandex SMTP (хост)
```

---

## Установка и запуск

### Требования

- Docker 24+
- Docker Compose v2
- Python 3.12 (для локальной разработки без Docker)

### Клонирование

```bash
git clone https://github.com/EvgeniyMalykh/kadrovik-landing.git
cd kadrovik-landing
```

### Локальный запуск (Docker)

```bash
# 1. Скопируйте .env файл
cp .env.example .env
# Заполните переменные (см. раздел ниже)

# 2. Сборка и запуск
docker compose -f docker-compose.production.yml up --build -d

# 3. Применение миграций
docker exec kadrovik-web-1 python manage.py migrate --settings=config.settings.production

# 4. Создание суперпользователя
docker exec -it kadrovik-web-1 python manage.py createsuperuser --settings=config.settings.production

# 5. Сбор статики
docker exec kadrovik-web-1 python manage.py collectstatic --noinput --settings=config.settings.production

# Приложение доступно на http://localhost:8000
```

### Остановка

```bash
docker compose -f docker-compose.production.yml down
```

---

## Переменные окружения

Создайте файл `.env` в корне проекта:

```env
# Django
SECRET_KEY=ваш-секретный-ключ-минимум-50-символов
DEBUG=False
ALLOWED_HOSTS=app.kadrovik-auto.ru,localhost

# База данных
DB_NAME=kadrovik
DB_USER=kadrovik
DB_PASSWORD=strong_password_here
DB_HOST=db
DB_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_RELAY_URL=redis://redis:6379/2

# Email (Яндекс.Почта)
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your@yandex.ru
EMAIL_HOST_PASSWORD=app_password_from_yandex
DEFAULT_FROM_EMAIL=your@yandex.ru

# Telegram (уведомления о регистрациях)
TELEGRAM_BOT_TOKEN=токен_бота
TELEGRAM_CHAT_ID=ваш_chat_id

# Google Sheets (опционально)
GAS_URL=
```

> ⚠️ Файл `.env` не должен попасть в репозиторий — добавлен в `.gitignore`

---

## Деплой на VPS

Проект задеплоен на **Timeweb Cloud** (Ubuntu 22.04, 2 vCPU, 8 GB RAM).

### Инфраструктура

```
VPS 109.73.207.33
├── /root/kadrovik/              # Исходный код
│   ├── staticfiles/             # Nginx раздаёт статику отсюда
│   └── docker-compose.production.yml
├── /etc/nginx/sites-available/  # Nginx конфиг
└── /root/email_relay.py         # systemd-сервис: Redis → SMTP
```

### Обновление кода

```bash
ssh root@109.73.207.33
cd /root/kadrovik
git pull

# Python-изменения — перезапуск контейнера
docker compose -f docker-compose.production.yml restart web

# Только CSS — без перезапуска (nginx раздаёт напрямую)
cp static/css/dashboard.css staticfiles/css/dashboard.css

# Шаблоны — только docker cp (Django читает с диска)
docker cp templates/base.html kadrovik-web-1:/app/templates/base.html

# Миграции
docker exec kadrovik-web-1 python manage.py migrate --settings=config.settings.production
```

### Запущенные контейнеры

| Контейнер | Образ | Назначение |
|-----------|-------|-----------|
| kadrovik-web-1 | Dockerfile | Gunicorn :8000 |
| kadrovik-db-1 | postgres:16 | PostgreSQL |
| kadrovik-redis-1 | redis:7 | Кэш + очереди |
| kadrovik-celery-1 | Dockerfile | Celery worker |
| kadrovik-celery-beat-1 | Dockerfile | Celery Beat (cron) |

---

## Мобильная адаптация

Приложение полностью адаптировано для работы в мобильном браузере (breakpoint ≤ 768px):

- **Hamburger-меню** — фиксированная кнопка ☰, sidebar открывается по tap с оверлеем
- **Сотрудники** — десктоп: таблица с документами; мобильный: карточки
- **Отпуска** — аналогично, карточки с датами и кнопкой печати
- **Drawer-формы** — на мобильном открываются на весь экран (100vw)
- **Табель** — горизонтальный скролл
- **Tap targets** — минимум 44×44 px для всех кнопок
- **Формы** — двух/трёхколоночные строки схлопываются в одну колонку

---

## API и интеграции

### REST API

```
GET  /api/v1/employees/          # Список сотрудников
POST /api/v1/employees/          # Создание
GET  /api/v1/employees/<id>/     # Карточка
```

### Публичная форма заявления на отпуск

```
GET/POST /vacations/request/<company_id>/
```
Страница без авторизации — работник вводит ФИО, должность, выбирает вид и даты отпуска. После отправки заявление сохраняется в системе и отображается в кадровом кабинете.

### Email (Celery + SMTP relay)

Цепочка отправки: Django → Celery task → Redis queue → `email_relay.py` (systemd на хосте) → Яндекс SMTP

| Событие | Получатель |
|---------|-----------|
| Верификация email при регистрации | Новый пользователь |
| Сброс пароля | Пользователь |
| Уведомление о новой регистрации | Telegram чат + Google Sheets |

### Telegram Bot

Уведомления о новых регистрациях через Bot API:
```
🎉 Новая регистрация!
📧 Email: user@company.ru
🏢 Компания: ООО Ромашка
🕐 Дата: 16.04.2026 17:30
```

---

## Changelog

### v1.5.0 (апрель 2026)
- ✅ Восстановление и смена пароля
- ✅ Публичная форма заявления на отпуск для работника
- ✅ Полная мобильная адаптация (hamburger, card-view, full-screen drawer)
- ✅ Исправлен скролл в drawer-формах

### v1.4.0
- ✅ Модуль заявлений на отпуск (список, создание, удаление, печать)
- ✅ Drawer вместо модального окна для форм сотрудников

### v1.3.0
- ✅ Верификация email при регистрации
- ✅ Уведомления в Telegram + Google Sheets
- ✅ SMTP через Яндекс.Почта

### v1.2.0
- ✅ Маска ввода дат ДД.ММ.ГГГГ во всех формах
- ✅ Редактирование всех полей карточки сотрудника

### v1.1.0
- ✅ Табель учёта рабочего времени (Т-13)
- ✅ Генерация PDF-документов (ReportLab)

### v1.0.0
- ✅ MVP: регистрация, сотрудники, кадровые документы

---

## Лицензия

Проприетарное ПО. Все права защищены © 2026 Кадровый автопилот.

---

<div align="center">
  <strong>Кадровый автопилот</strong> — кадровый учёт без лишних усилий<br>
  <a href="https://kadrovik-auto.ru">kadrovik-auto.ru</a> · <a href="https://app.kadrovik-auto.ru">app.kadrovik-auto.ru</a>
</div>
