"""
Скрипт миграции БД для поддержки расписания, преподавателей и аудиторий.
Версия 3.

Что делает:
1. Создаёт бекап БД в папку backups/ с датой и временем
2. Добавляет новые таблицы:
   - academic_years (учебные годы)
   - teachers (справочник преподавателей)
   - rooms (аудитории)
   - schedule_lessons (расписание)
   - student_group_history (история переводов студентов)
   - group_aliases (алиасы групп)
3. Добавляет новые поля в существующие таблицы:
   - groups: code, academic_year_id
   - users: teacher_id
4. Создаёт индексы для быстрого поиска
5. Создаёт текущий учебный год 2025/2026

ВАЖНО: Старые данные НЕ удаляются!
"""

import sqlite3
import os
import shutil
from datetime import datetime

# Пути
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'journal.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


def create_backup():
    """Создаёт бекап БД в папку backups с датой и временем в имени"""
    if not os.path.exists(DB_PATH):
        print(f"❌ БД не найдена: {DB_PATH}")
        print("   Запустите приложение сначала, чтобы создать БД.")
        return None

    # Создаём папку для бекапов
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Формируем имя бекапа
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'journal_{timestamp}.db'
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    # Копируем БД
    shutil.copy2(DB_PATH, backup_path)

    print(f"✅ Бекап создан: {backup_path}")
    print(f"   Размер: {os.path.getsize(backup_path) / 1024:.2f} КБ")

    return backup_path


def check_column_exists(cursor, table_name, column_name):
    """Проверяет, существует ли колонка в таблице"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


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
    print("МИГРАЦИЯ БД ДО ВЕРСИИ 3")
    print("=" * 70)
    print()

    # Шаг 1: Бекап
    print("📦 Шаг 1: Создание бекапа...")
    backup_path = create_backup()
    if not backup_path:
        return False
    print()

    # Шаг 2: Подключение к БД
    print("🔌 Шаг 2: Подключение к базе данных...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print(f"   Подключено: {DB_PATH}")
    print()

    try:
        # Шаг 3: Новые таблицы
        print("📋 Шаг 3: Создание новых таблиц...")

        # 3.1 Учебные годы
        if not check_table_exists(cursor, 'academic_years'):
            cursor.execute('''
                CREATE TABLE academic_years (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    is_current INTEGER DEFAULT 0
                )
            ''')
            print("   ✅ Таблица academic_years создана")
        else:
            print("   ⏭️  Таблица academic_years уже существует")

        # 3.2 Преподаватели
        if not check_table_exists(cursor, 'teachers'):
            cursor.execute('''
                CREATE TABLE teachers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT UNIQUE NOT NULL,
                    short_name TEXT,
                    is_active INTEGER DEFAULT 1
                )
            ''')
            print("   ✅ Таблица teachers создана")
        else:
            print("   ⏭️  Таблица teachers уже существует")

        # 3.3 Аудитории
        if not check_table_exists(cursor, 'rooms'):
            cursor.execute('''
                CREATE TABLE rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    building TEXT,
                    capacity INTEGER,
                    room_type TEXT DEFAULT 'classroom'
                )
            ''')
            print("   ✅ Таблица rooms создана")
        else:
            print("   ⏭️  Таблица rooms уже существует")

        # 3.4 Расписание
        if not check_table_exists(cursor, 'schedule_lessons'):
            cursor.execute('''
                CREATE TABLE schedule_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    academic_year_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    pair_number INTEGER NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    group_id INTEGER NOT NULL,
                    subject_id INTEGER NOT NULL,
                    teacher_id INTEGER,
                    teacher_name_raw TEXT,
                    room_id INTEGER,
                    room_name_raw TEXT,
                    lesson_type TEXT DEFAULT 'lecture',
                    original_group_name TEXT,
                    source_file TEXT,
                    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id),
                    FOREIGN KEY (group_id) REFERENCES groups(id),
                    FOREIGN KEY (subject_id) REFERENCES subjects(id),
                    FOREIGN KEY (teacher_id) REFERENCES teachers(id),
                    FOREIGN KEY (room_id) REFERENCES rooms(id)
                )
            ''')
            print("   ✅ Таблица schedule_lessons создана")
        else:
            print("   ⏭️  Таблица schedule_lessons уже существует")

        # 3.5 История переводов студентов
        if not check_table_exists(cursor, 'student_group_history'):
            cursor.execute('''
                CREATE TABLE student_group_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    academic_year_id INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    FOREIGN KEY (student_id) REFERENCES students(id),
                    FOREIGN KEY (group_id) REFERENCES groups(id),
                    FOREIGN KEY (academic_year_id) REFERENCES academic_years(id)
                )
            ''')
            print("   ✅ Таблица student_group_history создана")
        else:
            print("   ⏭️  Таблица student_group_history уже существует")

        # 3.6 Алиасы групп
        if not check_table_exists(cursor, 'group_aliases'):
            cursor.execute('''
                CREATE TABLE group_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    alias TEXT UNIQUE NOT NULL,
                    FOREIGN KEY (group_id) REFERENCES groups(id)
                )
            ''')
            print("   ✅ Таблица group_aliases создана")
        else:
            print("   ⏭️  Таблица group_aliases уже существует")

        print()

        # Шаг 4: Новые поля в существующих таблицах
        print("🔧 Шаг 4: Добавление полей в существующие таблицы...")

        # 4.1 groups: code
        if not check_column_exists(cursor, 'groups', 'code'):
            cursor.execute('ALTER TABLE groups ADD COLUMN code TEXT')
            print("   ✅ groups.code добавлено")
        else:
            print("   ⏭️  groups.code уже существует")

        # 4.2 groups: academic_year_id
        if not check_column_exists(cursor, 'groups', 'academic_year_id'):
            cursor.execute('ALTER TABLE groups ADD COLUMN academic_year_id INTEGER')
            print("   ✅ groups.academic_year_id добавлено")
        else:
            print("   ⏭️  groups.academic_year_id уже существует")

        # 4.3 users: teacher_id
        if not check_column_exists(cursor, 'users', 'teacher_id'):
            cursor.execute('ALTER TABLE users ADD COLUMN teacher_id INTEGER')
            print("   ✅ users.teacher_id добавлено")
        else:
            print("   ⏭️  users.teacher_id уже существует")

        print()

        # Шаг 5: Индексы
        print("🔍 Шаг 5: Создание индексов...")

        indexes = [
            ('idx_schedule_date', 'schedule_lessons(date)'),
            ('idx_schedule_group', 'schedule_lessons(group_id)'),
            ('idx_schedule_teacher', 'schedule_lessons(teacher_id)'),
            ('idx_schedule_room', 'schedule_lessons(room_id)'),
            ('idx_schedule_academic_year', 'schedule_lessons(academic_year_id)'),
            ('idx_history_student', 'student_group_history(student_id)'),
            ('idx_history_group', 'student_group_history(group_id)'),
            ('idx_alias_alias', 'group_aliases(alias)'),
        ]

        for idx_name, idx_def in indexes:
            try:
                cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}')
                print(f"   ✅ {idx_name}")
            except Exception as e:
                print(f"   ⚠️  {idx_name}: {e}")

        print()

        # Шаг 6: Создание текущего учебного года
        print("📅 Шаг 6: Создание учебного года 2025/2026...")

        existing_year = cursor.execute(
            "SELECT id FROM academic_years WHERE name = '2025/2026'"
        ).fetchone()

        if not existing_year:
            cursor.execute('''
                INSERT INTO academic_years (name, start_date, end_date, is_current)
                VALUES (?, ?, ?, ?)
            ''', ('2025/2026', '2025-09-01', '2026-06-30', 1))
            print("   ✅ Учебный год 2025/2026 создан")
        else:
            print("   ⏭️  Учебный год 2025/2026 уже существует")

        print()

        # Шаг 7: Базовые аудитории
        print("🏫 Шаг 7: Создание базовых аудиторий...")

        base_rooms = [
            ('84', 'учебный корпус', 30, 'classroom'),
            ('90', 'учебный корпус', 30, 'classroom'),
            ('Спорт зал', 'спортивный корпус', 50, 'gym'),
            ('акт зал', 'главный корпус', 200, 'act_hall'),
            ('Библиотека', 'главный корпус', 30, 'library'),
            ('Библ', 'главный корпус', 30, 'library'),
            ('с/р', 'самостоятельная работа', None, 'none'),
        ]

        for name, building, capacity, room_type in base_rooms:
            existing = cursor.execute(
                "SELECT id FROM rooms WHERE name = ?", (name,)
            ).fetchone()
            if not existing:
                cursor.execute('''
                    INSERT INTO rooms (name, building, capacity, room_type)
                    VALUES (?, ?, ?, ?)
                ''', (name, building, capacity, room_type))
                print(f"   ✅ {name}")
            else:
                print(f"   ⏭️  {name} уже существует")

        print()

        # Сохраняем изменения
        conn.commit()

        print("=" * 70)
        print("✅ МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("=" * 70)
        print()
        print(f"📦 Бекап сохранён: {backup_path}")
        print(f"   (не удаляйте его — это резервная копия на случай отката)")
        print()
        print("Следующие шаги:")
        print("  1. Запустите: python migrations/import_teachers.py")
        print("  2. Запустите приложение: python app.py")
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