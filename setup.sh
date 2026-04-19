#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Кадровый автопилот — настройка окружения ==="

# Создаём venv если нет
if [ ! -d "venv" ]; then
    echo "Создаём виртуальное окружение..."
    python3 -m venv venv
fi

# Активируем и устанавливаем зависимости
source venv/bin/activate
echo "Устанавливаем зависимости..."
pip install --upgrade pip -q
pip install -r requirements/local.txt -q
echo "✓ Зависимости установлены"

# Копируем .env если нет
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "✓ Создан .env из .env.example — заполните переменные"
fi

echo ""
echo "Готово! Окружение настроено."
echo "Для запуска: source venv/bin/activate && python manage.py runserver"
