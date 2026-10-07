"""
Миграция БД до версии 7.

Что делает:
1. Создаёт бэкап БД.
2. Создаёт таблицу journal_plan — тематический план занятий
   для каждой пары Группа-Предмет.
3. Индекс по group_subject_id.
"""

import os
import shutil
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'journal.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


def create_backup(prefix='before_v7'):
    if not os.path.exists(DB_PATH):
        print(f"[!] БД не найдена: {DB_PATH}")
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(BACKUP_DIR, f'journal_{ts}_{prefix}.db')
    shutil.copy2(DB_PATH, dst)
    print(f"[+] Бекап: {dst}")
    return dst


def table_exists(cursor, name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    )
    return cursor.fetchone() is not None


def migrate():
    print("=" * 70)
    print("МИГРАЦИЯ БД ДО ВЕРСИИ 7")
    print("=" * 70)
    print()

    print("[1/3] Создание бекапа...")
    backup = create_backup(prefix='before_v7')
    if not backup:
        return False
    print()

    print("[2/3] Подключение к БД...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print(f"    БД: {DB_PATH}")
    print()

    try:
        print("[3/3] Создание таблицы journal_plan...")
        if not table_exists(cursor, 'journal_plan'):
            cursor.execute('''
                CREATE TABLE journal_plan (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_subject_id INTEGER NOT NULL,
                    order_number INTEGER,
                    topic TEXT NOT NULL,
                    hours INTEGER DEFAULT 2,
                    lesson_type TEXT DEFAULT 'lecture',
                    used_lesson_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (group_subject_id) REFERENCES group_subjects(id) ON DELETE CASCADE
                )
            ''')
            print("    ✅ Таблица journal_plan создана")
        else:
            print("    ⏭️  Таблица journal_plan уже существует")

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_plan_gsid "
            "ON journal_plan(group_subject_id)"
        )
        print("    ✅ Индекс idx_plan_gsid создан")

        conn.commit()
        print()
        print("=" * 70)
        print("[+] МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО")
        print("=" * 70)
        print()
        print(f"Бекап: {backup}")
        print()
        return True

    except Exception as e:
        conn.rollback()
        print()
        print("=" * 70)
        print(f"[!] ОШИБКА: {e}")
        print("=" * 70)
        print(f"Бекап: {backup}")
        return False

    finally:
        conn.close()


if __name__ == '__main__':
    success = migrate()
    exit(0 if success else 1)