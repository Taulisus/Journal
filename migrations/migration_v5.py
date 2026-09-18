"""
Миграция БД до версии 5.

Что делает:
1. Создаёт бекап БД в backups/
2. Создаёт таблицу position_permissions — права по умолчанию для каждой должности
3. Заполняет её дефолтными правами для ролей:
   admin, teacher, curator, head_teacher, methodist
4. Создаёт индексы
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


# Дефолтные права для ролей (по коду permission)
DEFAULT_ROLE_PERMISSIONS = {
    'admin': [
        # Админу — все права (заполним динамически ниже)
        '__ALL__',
    ],
    'teacher': [
        'view_journals',
        'view_student_card',
        'create_report',
        'edit_profile',
        'set_semester_grade',
    ],
    'curator': [
        'view_journals',
        'view_student_card',
        'create_report',
        'add_students',
        'edit_profile',
    ],
    'head_teacher': [
        'view_journals',
        'view_student_card',
        'create_report',
        'edit_profile',
        'set_semester_grade',
    ],
    'methodist': [
        'view_journals',
        'view_student_card',
        'create_report',
        'add_journal',
        'add_students',
        'edit_profile',
    ],
}


def create_backup():
    if not os.path.exists(DB_PATH):
        print(f"❌ БД не найдена: {DB_PATH}")
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'journal_{timestamp}_before_v5.db'
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    shutil.copy2(DB_PATH, backup_path)

    print(f"✅ Бекап создан: {backup_path}")
    print(f"   Размер: {os.path.getsize(backup_path) / 1024:.2f} КБ")

    return backup_path


def check_table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def migrate():
    print("=" * 70)
    print("МИГРАЦИЯ БД ДО ВЕРСИИ 5")
    print("=" * 70)
    print()

    print("📦 Шаг 1: Создание бекапа...")
    backup_path = create_backup()
    if not backup_path:
        return False
    print()

    print("🔌 Шаг 2: Подключение к базе данных...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print(f"   Подключено: {DB_PATH}")
    print()

    try:
        # Шаг 3: Таблица position_permissions
        print("📋 Шаг 3: Создание таблицы position_permissions...")

        if not check_table_exists(cursor, 'position_permissions'):
            cursor.execute('''
                CREATE TABLE position_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id INTEGER NOT NULL,
                    permission_id INTEGER NOT NULL,
                    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
                    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
                    UNIQUE(position_id, permission_id)
                )
            ''')
            print("   ✅ Таблица position_permissions создана")
        else:
            print("   ⏭️  Таблица position_permissions уже существует")

        # Шаг 4: Индекс
        print()
        print("🔍 Шаг 4: Создание индексов...")

        indexes = [
            ('idx_pos_perm_position', 'position_permissions(position_id)'),
            ('idx_pos_perm_permission', 'position_permissions(permission_id)'),
        ]

        for idx_name, idx_def in indexes:
            try:
                cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}')
                print(f"   ✅ {idx_name}")
            except Exception as e:
                print(f"   ⚠️  {idx_name}: {e}")

        # Шаг 5: Заполнение дефолтных прав
        print()
        print("📋 Шаг 5: Заполнение дефолтных прав для ролей...")

        # Собираем словарь: код permission → id
        perm_rows = cursor.execute("SELECT id, code FROM permissions").fetchall()
        perm_by_code = {row[1]: row[0] for row in perm_rows}
        all_perm_ids = [row[0] for row in perm_rows]

        if not perm_by_code:
            print("   ⚠️  Нет прав в таблице permissions — пропускаем заполнение")
        else:
            # Собираем словарь: код position → id
            pos_rows = cursor.execute("SELECT id, code FROM positions").fetchall()
            pos_by_code = {row[1]: row[0] for row in pos_rows}

            for role_code, perm_codes in DEFAULT_ROLE_PERMISSIONS.items():
                pos_id = pos_by_code.get(role_code)
                if not pos_id:
                    print(f"   ⚠️  Роль '{role_code}' не найдена в positions — пропуск")
                    continue

                # Определяем список permission_id
                if '__ALL__' in perm_codes:
                    target_ids = all_perm_ids
                else:
                    target_ids = [perm_by_code[c] for c in perm_codes if c in perm_by_code]

                # Удаляем старые, чтобы перезаписать (только для этой роли)
                cursor.execute(
                    "DELETE FROM position_permissions WHERE position_id = ?",
                    (pos_id,)
                )

                for perm_id in target_ids:
                    try:
                        cursor.execute(
                            "INSERT INTO position_permissions (position_id, permission_id) "
                            "VALUES (?, ?)",
                            (pos_id, perm_id)
                        )
                    except Exception as e:
                        print(f"   ⚠️  Не удалось добавить {role_code}→{perm_id}: {e}")

                print(f"   ✅ {role_code}: {len(target_ids)} прав")

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
        print("  2. Откройте /roles — проверьте, что права ролей отображаются")
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