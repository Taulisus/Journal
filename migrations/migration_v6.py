"""
Миграция БД до версии 6.

Что делает:
1. Создаёт бекап БД в backups/ перед любыми изменениями.
2. Добавляет таблицы, если их нет:
   - academic_years        — учебные годы
   - teachers              — справочник преподавателей
   - rooms                 — аудитории
   - schedule_lessons      — расписание
   - group_aliases         — алиасы групп
   - student_group_history — история переводов студентов
   - activity_log          — лог действий
   - stats_cache           — кэш статистики
   - position_permissions  — права ролей
3. Создаёт индексы для быстрого поиска.
4. Добавляет поля в существующие таблицы (если их нет):
   - groups.code, groups.academic_year_id
   - users.teacher_id
5. Заполняет сиды (только если таблицы пусты):
   - academic_years: текущий 2025/2026
   - rooms: 7 базовых аудиторий
   - position_permissions: дефолтные права ролей
6. До-выдаёт право edit_schedule ролям teacher / methodist / head_teacher / admin
   (идемпотентно, можно запускать повторно).
7. НЕ удаляет и НЕ изменяет существующие данные.

Скрипт идемпотентен: можно запускать повторно без вреда.

Использование:
    python migrations/migration_v6.py
"""

import os
import shutil
import sqlite3
from datetime import datetime


# ============================================================
#                 ПУТИ
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'journal.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


# ============================================================
#                 УТИЛИТЫ
# ============================================================

def create_backup(prefix='before_v6'):
    """Создаёт бэкап БД в backups/ с меткой времени."""
    if not os.path.exists(DB_PATH):
        print(f"[!] БД не найдена: {DB_PATH}")
        print("    Запустите приложение один раз, чтобы создать БД.")
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'journal_{timestamp}_{prefix}.db'
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    shutil.copy2(DB_PATH, backup_path)

    size_kb = os.path.getsize(backup_path) / 1024
    print(f"[+] Бекап создан: {backup_path}")
    print(f"    Размер: {size_kb:.2f} КБ")
    return backup_path


def table_exists(cursor, table_name):
    """Проверяет, существует ли таблица."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def column_exists(cursor, table_name, column_name):
    """Проверяет, существует ли колонка в таблице."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def index_exists(cursor, index_name):
    """Проверяет, существует ли индекс."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cursor.fetchone() is not None


def count_rows(cursor, table_name):
    """Возвращает число строк в таблице (0, если таблицы нет)."""
    if not table_exists(cursor, table_name):
        return 0
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


# ============================================================
#                 СОЗДАНИЕ ТАБЛИЦ
# ============================================================

def create_tables(cursor):
    """Создаёт все новые таблицы, если их нет."""
    created = []
    skipped = []

    # --- academic_years ---
    if not table_exists(cursor, 'academic_years'):
        cursor.execute('''
            CREATE TABLE academic_years (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                is_current INTEGER DEFAULT 0
            )
        ''')
        created.append('academic_years')
    else:
        skipped.append('academic_years')

    # --- teachers ---
    if not table_exists(cursor, 'teachers'):
        cursor.execute('''
            CREATE TABLE teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT UNIQUE NOT NULL,
                short_name TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        created.append('teachers')
    else:
        skipped.append('teachers')

    # --- rooms ---
    if not table_exists(cursor, 'rooms'):
        cursor.execute('''
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                building TEXT,
                capacity INTEGER,
                room_type TEXT DEFAULT 'classroom'
            )
        ''')
        created.append('rooms')
    else:
        skipped.append('rooms')

    # --- student_group_history ---
    if not table_exists(cursor, 'student_group_history'):
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
        created.append('student_group_history')
    else:
        skipped.append('student_group_history')

    # --- group_aliases ---
    if not table_exists(cursor, 'group_aliases'):
        cursor.execute('''
            CREATE TABLE group_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                alias TEXT UNIQUE NOT NULL,
                FOREIGN KEY (group_id) REFERENCES groups(id)
            )
        ''')
        created.append('group_aliases')
    else:
        skipped.append('group_aliases')

    # --- schedule_lessons ---
    if not table_exists(cursor, 'schedule_lessons'):
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
        created.append('schedule_lessons')
    else:
        skipped.append('schedule_lessons')

    # --- activity_log ---
    if not table_exists(cursor, 'activity_log'):
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
        created.append('activity_log')
    else:
        skipped.append('activity_log')

    # --- stats_cache ---
    if not table_exists(cursor, 'stats_cache'):
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
        created.append('stats_cache')
    else:
        skipped.append('stats_cache')

    # --- position_permissions ---
    if not table_exists(cursor, 'position_permissions'):
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
        created.append('position_permissions')
    else:
        skipped.append('position_permissions')

    print()
    if created:
        print(f"[+] Созданы таблицы: {', '.join(created)}")
    if skipped:
        print(f"[=] Уже существуют:  {', '.join(skipped)}")


# ============================================================
#                 ДОБАВЛЕНИЕ ПОЛЕЙ В СУЩЕСТВУЮЩИЕ ТАБЛИЦЫ
# ============================================================

def add_columns(cursor):
    """Добавляет поля в существующие таблицы, если их нет."""
    added = []

    # groups.code
    if table_exists(cursor, 'groups') and not column_exists(cursor, 'groups', 'code'):
        cursor.execute("ALTER TABLE groups ADD COLUMN code TEXT")
        added.append('groups.code')

    # groups.academic_year_id
    if table_exists(cursor, 'groups') and not column_exists(cursor, 'groups', 'academic_year_id'):
        cursor.execute("ALTER TABLE groups ADD COLUMN academic_year_id INTEGER")
        added.append('groups.academic_year_id')

    # users.teacher_id
    if table_exists(cursor, 'users') and not column_exists(cursor, 'users', 'teacher_id'):
        cursor.execute("ALTER TABLE users ADD COLUMN teacher_id INTEGER")
        added.append('users.teacher_id')

    if added:
        print()
        print(f"[+] Добавлены поля: {', '.join(added)}")
    else:
        print()
        print("[=] Все поля уже существуют")


# ============================================================
#                 ИНДЕКСЫ
# ============================================================

INDEXES = [
    # Расписание
    ('idx_schedule_date', 'schedule_lessons(date)'),
    ('idx_schedule_group', 'schedule_lessons(group_id)'),
    ('idx_schedule_teacher', 'schedule_lessons(teacher_id)'),
    ('idx_schedule_room', 'schedule_lessons(room_id)'),
    ('idx_schedule_academic_year', 'schedule_lessons(academic_year_id)'),
    ('idx_schedule_group_date', 'schedule_lessons(group_id, date)'),
    ('idx_schedule_teacher_date', 'schedule_lessons(teacher_id, date)'),
    ('idx_schedule_room_date', 'schedule_lessons(room_id, date)'),

    # История переводов
    ('idx_history_student', 'student_group_history(student_id)'),
    ('idx_history_group', 'student_group_history(group_id)'),

    # Алиасы групп
    ('idx_alias_alias', 'group_aliases(alias)'),
    ('idx_alias_group', 'group_aliases(group_id)'),

    # Лог действий
    ('idx_activity_created', 'activity_log(created_at DESC)'),
    ('idx_activity_user', 'activity_log(user_id)'),
    ('idx_activity_action', 'activity_log(action)'),

    # Кэш статистики
    ('idx_stats_user_key', 'stats_cache(user_id, stat_key)'),

    # Права ролей
    ('idx_pos_perm_position', 'position_permissions(position_id)'),
    ('idx_pos_perm_permission', 'position_permissions(permission_id)'),

    # Существующие таблицы — для скорости
    ('idx_students_group', 'students(group_id)'),
    ('idx_students_name', 'students(full_name)'),
    ('idx_group_subjects_group', 'group_subjects(group_id)'),
    ('idx_group_subjects_subject', 'group_subjects(subject_id)'),
    ('idx_teacher_journals_user', 'teacher_journals(user_id)'),
    ('idx_curators_user', 'curators(user_id)'),
    ('idx_user_permissions_user', 'user_permissions(user_id)'),
    ('idx_user_positions_user', 'user_positions(user_id)'),
]


def create_indexes(cursor):
    """Создаёт индексы, если их нет и если таблица существует."""
    created = []
    skipped = []

    for idx_name, idx_def in INDEXES:
        # Извлекаем имя таблицы из определения (до открывающей скобки)
        table_name = idx_def.split('(')[0].strip()

        if not table_exists(cursor, table_name):
            skipped.append(idx_name)
            continue

        try:
            cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}')
            created.append(idx_name)
        except sqlite3.OperationalError as e:
            print(f"[!] Не удалось создать {idx_name}: {e}")

    print()
    if created:
        print(f"[+] Создано индексов: {len(created)}")
        for name in created:
            print(f"    · {name}")
    if skipped:
        print(f"[=] Пропущено (нет таблицы): {', '.join(skipped)}")


# ============================================================
#                 СИДЫ
# ============================================================

DEFAULT_ROOMS = [
    ('84', 'учебный корпус', 30, 'classroom'),
    ('90', 'учебный корпус', 30, 'classroom'),
    ('Спорт зал', 'спортивный корпус', 50, 'gym'),
    ('акт зал', 'главный корпус', 200, 'act_hall'),
    ('Библиотека', 'главный корпус', 30, 'library'),
    ('Библ', 'главный корпус', 30, 'library'),
    ('с/р', 'самостоятельная работа', None, 'none'),
]

DEFAULT_ROLE_PERMISSIONS = {
    'admin': '__ALL__',
    'teacher': [
        'view_journals',
        'view_student_card',
        'create_report',
        'edit_profile',
        'set_semester_grade',
        'edit_schedule',
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
        'edit_schedule',
    ],
    'methodist': [
        'view_journals',
        'view_student_card',
        'create_report',
        'add_journal',
        'add_students',
        'edit_profile',
        'edit_schedule',
    ],
}


def seed_academic_year(cursor):
    """Создаёт текущий учебный год, если таблица пуста."""
    if count_rows(cursor, 'academic_years') > 0:
        print("[=] academic_years: уже заполнена")
        return

    cursor.execute(
        "INSERT INTO academic_years (name, start_date, end_date, is_current) "
        "VALUES (?, ?, ?, 1)",
        ('2025/2026', '2025-09-01', '2026-06-30'),
    )
    print("[+] academic_years: создан 2025/2026")


def seed_rooms(cursor):
    """Заполняет rooms, если таблица пуста."""
    if count_rows(cursor, 'rooms') > 0:
        print("[=] rooms: уже заполнена")
        return

    for name, building, capacity, room_type in DEFAULT_ROOMS:
        cursor.execute(
            "INSERT INTO rooms (name, building, capacity, room_type) "
            "VALUES (?, ?, ?, ?)",
            (name, building, capacity, room_type),
        )
    print(f"[+] rooms: добавлено {len(DEFAULT_ROOMS)} аудиторий")


def seed_position_permissions(cursor):
    """Заполняет position_permissions, если таблица пуста."""
    if count_rows(cursor, 'position_permissions') > 0:
        print("[=] position_permissions: уже заполнена")
        return

    if count_rows(cursor, 'permissions') == 0:
        print("[!] position_permissions: нет прав в permissions — пропуск")
        return

    if count_rows(cursor, 'positions') == 0:
        print("[!] position_permissions: нет ролей в positions — пропуск")
        return

    # Собираем id прав по коду
    perm_rows = cursor.execute("SELECT id, code FROM permissions").fetchall()
    perm_by_code = {row[1]: row[0] for row in perm_rows}
    all_perm_ids = [row[0] for row in perm_rows]

    # Собираем id ролей по коду
    pos_rows = cursor.execute("SELECT id, code FROM positions").fetchall()
    pos_by_code = {row[1]: row[0] for row in pos_rows}

    total = 0
    for role_code, perm_codes in DEFAULT_ROLE_PERMISSIONS.items():
        pos_id = pos_by_code.get(role_code)
        if not pos_id:
            print(f"[!] Роль '{role_code}' не найдена — пропуск")
            continue

        if perm_codes == '__ALL__':
            target_ids = all_perm_ids
        else:
            target_ids = [perm_by_code[c] for c in perm_codes if c in perm_by_code]

        for perm_id in target_ids:
            try:
                cursor.execute(
                    "INSERT INTO position_permissions (position_id, permission_id) "
                    "VALUES (?, ?)",
                    (pos_id, perm_id),
                )
                total += 1
            except sqlite3.IntegrityError:
                pass

    print(f"[+] position_permissions: добавлено {total} связей")


def seed_edit_schedule_permission(cursor):
    """
    До-выдаёт право 'edit_schedule' ролям teacher / methodist / head_teacher / admin.
    Идемпотентно — безопасно запускать повторно.

    В отличие от seed_position_permissions, эта функция НЕ проверяет,
    пуста ли таблица — она работает поверх существующих данных.
    """
    # 1. Убедиться, что право есть в permissions
    cursor.execute(
        "INSERT OR IGNORE INTO permissions (code, name, description) "
        "VALUES (?, ?, ?)",
        ('edit_schedule', 'Редактирование расписания',
         'Добавление и изменение занятий в расписании')
    )

    # 2. Найти его id
    row = cursor.execute(
        "SELECT id FROM permissions WHERE code = ?",
        ('edit_schedule',)
    ).fetchone()
    if not row:
        print("[!] Не удалось найти право edit_schedule — пропуск")
        return

    perm_id = row[0]

    # 3. Выдать ролям
    roles = ('teacher', 'methodist', 'head_teacher', 'admin')
    issued = 0
    for role_code in roles:
        pos = cursor.execute(
            "SELECT id FROM positions WHERE code = ?",
            (role_code,)
        ).fetchone()
        if not pos:
            continue
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO position_permissions "
                "(position_id, permission_id) VALUES (?, ?)",
                (pos[0], perm_id)
            )
            issued += 1
        except sqlite3.IntegrityError:
            pass

    # 4. Admin (user_id=1) — лично
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO user_permissions "
            "(user_id, permission_id) VALUES (?, ?)",
            (1, perm_id)
        )
    except sqlite3.IntegrityError:
        pass

    print(f"[+] edit_schedule выдан {issued} ролям + admin")


def run_seeds(cursor):
    """Запускает все сиды."""
    print()
    print("[*] Заполнение сидов...")
    seed_academic_year(cursor)
    seed_rooms(cursor)
    seed_position_permissions(cursor)
    seed_edit_schedule_permission(cursor)


# ============================================================
#                 ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def migrate():
    print("=" * 70)
    print("МИГРАЦИЯ БД ДО ВЕРСИИ 6")
    print("=" * 70)
    print()

    # Шаг 1: Бекап
    print("[1/5] Создание бекапа...")
    backup_path = create_backup(prefix='before_v6')
    if not backup_path:
        return False
    print()

    # Шаг 2: Подключение
    print("[2/5] Подключение к базе данных...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print(f"    БД: {DB_PATH}")
    print()

    try:
        # Шаг 3: Таблицы
        print("[3/5] Создание таблиц...")
        create_tables(cursor)
        print()

        # Шаг 4: Поля в существующих таблицах
        print("[4/5] Проверка полей в существующих таблицах...")
        add_columns(cursor)
        print()

        # Шаг 5: Индексы
        print("[5/5] Создание индексов...")
        create_indexes(cursor)

        # Шаг 6: Сиды
        run_seeds(cursor)

        # Сохраняем
        conn.commit()
        conn.close()

        print()
        print("=" * 70)
        print("[+] МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО")
        print("=" * 70)
        print()
        print(f"Бекап: {backup_path}")
        print("(не удаляйте — пригодится, если что-то пойдёт не так)")
        print()
        print("Следующие шаги:")
        print("  1. Запустите приложение: python app.py")
        print("  2. Откройте /schedule — проверьте, что расписание работает")
        print("  3. Откройте /roles — проверьте, что право edit_schedule на месте")
        print()

        return True

    except Exception as e:
        conn.rollback()
        conn.close()

        print()
        print("=" * 70)
        print(f"[!] ОШИБКА МИГРАЦИИ: {e}")
        print("=" * 70)
        print()
        print("Изменения откатаны. Оригинальная БД не тронута.")
        print(f"Бекап: {backup_path}")
        print()
        return False


if __name__ == '__main__':
    success = migrate()
    exit(0 if success else 1)