"""
Миграция БД до версии 4.

Что делает:
1. Создаёт бекап БД в backups/
2. Создаёт таблицу activity_log — лог действий пользователей
3. Создаёт таблицу stats_cache — кэш статистики
4. Создаёт индексы для быстрого поиска
5. НЕ удаляет и НЕ изменяет существующие таблицы

ВАЖНО: Старые данные НЕ удаляются!
"""

import sqlite3
import os
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'journal.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


def create_backup():
    """Создаёт бекап БД в папку backups с датой и временем в имени"""
    if not os.path.exists(DB_PATH):
        print(f"❌ БД не найдена: {DB_PATH}")
        print("   Запустите приложение сначала, чтобы создать БД.")
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'journal_{timestamp}_before_v4.db'
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    shutil.copy2(DB_PATH, backup_path)

    print(f"✅ Бекап создан: {backup_path}")
    print(f"   Размер: {os.path.getsize(backup_path) / 1024:.2f} КБ")

    return backup_path


def check_table_exists(cursor, table_name):
    """Проверяет, существует ли таблица"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def migrate():
    """Основная функция миграции"""
    print("=" * 70)
    print("МИГРАЦИЯ БД ДО ВЕРСИИ 4")
    print("=" * 70)
    print()

    # Шаг 1: Бекап
    print("📦 Шаг 1: Создание бекапа...")
    backup_path = create_backup()
    if not backup_path:
        return False
    print()

    # Шаг 2: Подключение
    print("🔌 Шаг 2: Подключение к базе данных...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print(f"   Подключено: {DB_PATH}")
    print()

    try:
        # Шаг 3: Таблица activity_log
        print("📋 Шаг 3: Создание таблицы activity_log...")

        if not check_table_exists(cursor, 'activity_log'):
            cursor.execute('''
                CREATE TABLE activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    description TEXT,
                    target_type TEXT,
                    target_id INTEGER,
                    ip TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')
            print("   ✅ Таблица activity_log создана")
        else:
            print("   ⏭️  Таблица activity_log уже существует")

        # Шаг 4: Таблица stats_cache
        print()
        print("📋 Шаг 4: Создание таблицы stats_cache...")

        if not check_table_exists(cursor, 'stats_cache'):
            cursor.execute('''
                CREATE TABLE stats_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    stat_key TEXT NOT NULL,
                    stat_value TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, stat_key),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            print("   ✅ Таблица stats_cache создана")
        else:
            print("   ⏭️  Таблица stats_cache уже существует")

        # Шаг 5: Индексы
        print()
        print("🔍 Шаг 5: Создание индексов...")

        indexes = [
            ('idx_activity_created', 'activity_log(created_at DESC)'),
            ('idx_activity_user', 'activity_log(user_id)'),
            ('idx_activity_action', 'activity_log(action)'),
            ('idx_stats_user_key', 'stats_cache(user_id, stat_key)'),
        ]

        for idx_name, idx_def in indexes:
            try:
                cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}')
                print(f"   ✅ {idx_name}")
            except Exception as e:
                print(f"   ⚠️  {idx_name}: {e}")

        # Сохраняем
        conn.commit()

        print()
        print("=" * 70)
        print("✅ МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("=" * 70)
        print()
        print(f"📦 Бекап сохранён: {backup_path}")
        print(f"   (не удаляйте его — это резервная копия на случай отката)")
        print()
        print("Следующие шаги:")
        print("  1. Запустите приложение: python app.py")
        print("  2. Проверьте главную страницу")
        print()

        return True

    except Exception as e:
        conn.rollback()
        print()
        print("=" * 70)
        print(f"❌ ОШИБКА МИГРАЦИИ: {e}")
        print("=" * 70)
        print()
        print(f"Все изменения откатаны. Оригинальная БД не изменена.")
        print(f"Бекап доступен: {backup_path}")
        return False

    finally:
        conn.close()


if __name__ == '__main__':
    success = migrate()
    exit(0 if success else 1)