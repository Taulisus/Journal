import sqlite3
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash


def get_db():
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS group_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
            UNIQUE(group_id, subject_id)
        );

        CREATE TABLE IF NOT EXISTS group_subject_hours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_subject_id INTEGER NOT NULL,
            semester INTEGER NOT NULL DEFAULT 1,
            lecture_hours INTEGER DEFAULT 0,
            practice_hours INTEGER DEFAULT 0,
            independent_hours INTEGER DEFAULT 0,
            exam_hours INTEGER DEFAULT 0,
            FOREIGN KEY (group_subject_id) REFERENCES group_subjects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS student_semester_grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            group_subject_id INTEGER NOT NULL,
            semester INTEGER NOT NULL DEFAULT 1,
            grade TEXT,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (group_subject_id) REFERENCES group_subjects(id) ON DELETE CASCADE,
            UNIQUE(student_id, group_subject_id, semester)
        );

        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            phone TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            code TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            position_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
            UNIQUE(user_id, position_id)
        );

        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS user_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
            UNIQUE(user_id, permission_id)
        );

        CREATE TABLE IF NOT EXISTS position_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
            FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
            UNIQUE(position_id, permission_id)
        );

        CREATE TABLE IF NOT EXISTS teacher_journals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_subject_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (group_subject_id) REFERENCES group_subjects(id) ON DELETE CASCADE,
            UNIQUE(user_id, group_subject_id)
        );

        CREATE TABLE IF NOT EXISTS curators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            UNIQUE(user_id, group_id)
        );

        CREATE TABLE IF NOT EXISTS teacher_hours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_subject_id INTEGER NOT NULL,
            semester INTEGER NOT NULL DEFAULT 1,
            lecture_hours INTEGER DEFAULT 0,
            practice_hours INTEGER DEFAULT 0,
            independent_hours INTEGER DEFAULT 0,
            exam_hours INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (group_subject_id) REFERENCES group_subjects(id) ON DELETE CASCADE,
            UNIQUE(user_id, group_subject_id, semester)
        );

        CREATE TABLE IF NOT EXISTS student_group_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            academic_year_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (academic_year_id) REFERENCES academic_years(id)
        );
    ''')

    user = cursor.execute("SELECT COUNT(*) as count FROM users").fetchone()
    if user['count'] == 0:
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                       ('admin', generate_password_hash('admin123')))
        cursor.execute("INSERT INTO user_profiles (user_id, full_name, phone) VALUES (?, ?, ?)",
                       (1, 'Администратор', ''))

    pos_count = cursor.execute("SELECT COUNT(*) as count FROM positions").fetchone()
    if pos_count['count'] == 0:
        positions = [
            ('admin', 'Администратор'),
            ('teacher', 'Преподаватель'),
            ('curator', 'Куратор'),
            ('head_teacher', 'Завуч'),
            ('methodist', 'Методист'),
        ]
        for code, name in positions:
            cursor.execute("INSERT INTO positions (code, name) VALUES (?, ?)", (code, name))
        cursor.execute("INSERT INTO user_positions (user_id, position_id) VALUES (1, 1)")

    perm_count = cursor.execute("SELECT COUNT(*) as count FROM permissions").fetchone()
    if perm_count['count'] == 0:
        perms = [
            ('view_journals', 'Просмотр журналов', 'Доступ к просмотру журналов группы'),
            ('view_student_card', 'Просмотр карточки студента', 'Доступ к карточке студента'),
            ('add_journal', 'Добавление журнала', 'Создание новых журналов'),
            ('add_students', 'Добавление студентов', 'Добавление и импорт студентов'),
            ('manage_users', 'Управление пользователями', 'Создание, удаление, редактирование пользователей'),
            ('manage_permissions', 'Управление правами', 'Назначение прав пользователям'),
            ('create_report', 'Отчеты', 'Доступ к отчетам и печати'),
            ('delete_student', 'Удаление студента', 'Право на удаление студентов'),
            ('assign_teacher', 'Назначение преподавателя', 'Назначение преподавателя на журнал'),
            ('edit_profile', 'Редактирование профиля', 'Изменение своего профиля'),
            ('set_semester_grade', 'Выставление оценки за семестр', 'Итоговая оценка за семестр'),
        ]
        for code, name, desc in perms:
            cursor.execute("INSERT INTO permissions (code, name, description) VALUES (?, ?, ?)", (code, name, desc))
        all_perms = cursor.execute("SELECT id FROM permissions").fetchall()
        for perm in all_perms:
            cursor.execute("INSERT INTO user_permissions (user_id, permission_id) VALUES (1, ?)", (perm['id'],))

    conn.commit()
    conn.close()
    print("База данных инициализирована. Логин: admin, Пароль: admin123")


class User:
    @staticmethod
    def find_by_username(username):
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        return user

    @staticmethod
    def get_by_id(user_id):
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return user

    @staticmethod
    def check_password(user, password):
        return check_password_hash(user['password_hash'], password)

    @staticmethod
    def get_all():
        conn = get_db()
        users = conn.execute('''
            SELECT u.id, u.username, up.full_name, up.phone
            FROM users u LEFT JOIN user_profiles up ON u.id = up.user_id
            ORDER BY u.id
        ''').fetchall()
        conn.close()
        return users

    @staticmethod
    def create(username, password, full_name='', phone='', position_ids=None, permission_ids=None):
        conn = get_db()
        try:
            cur = conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                               (username, generate_password_hash(password)))
            uid = cur.lastrowid
            conn.execute("INSERT INTO user_profiles (user_id, full_name, phone) VALUES (?, ?, ?)",
                         (uid, full_name, phone))
            if position_ids:
                for pid in position_ids:
                    try:
                        conn.execute("INSERT INTO user_positions (user_id, position_id) VALUES (?, ?)", (uid, int(pid)))
                    except:
                        pass
            if permission_ids:
                for pid in permission_ids:
                    try:
                        conn.execute("INSERT INTO user_permissions (user_id, permission_id) VALUES (?, ?)",
                                     (uid, int(pid)))
                    except:
                        pass
            conn.commit()
            conn.close()
            return True, f"Пользователь {username} создан", uid
        except sqlite3.IntegrityError:
            conn.close()
            return False, "Пользователь с таким логином уже существует", None

    @staticmethod
    def delete(user_id):
        conn = get_db()
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def update_profile(user_id, username, full_name, phone):
        username = (username or '').strip()
        full_name = (full_name or '').strip()
        phone = (phone or '').strip()

        if not username:
            return False, 'Логин не может быть пустым'
        if len(username) < 3:
            return False, 'Логин должен быть не короче 3 символов'

        conn = get_db()
        try:
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (username, user_id)
            ).fetchone()
            if existing:
                return False, 'Такой логин уже занят'

            conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
            conn.execute("UPDATE user_profiles SET full_name = ?, phone = ? WHERE user_id = ?",
                         (full_name, phone, user_id))
            conn.commit()
            return True, 'Профиль обновлён'
        except Exception as e:
            conn.rollback()
            return False, f'Ошибка: {str(e)}'
        finally:
            conn.close()

    @staticmethod
    def change_password(user_id, current_password, new_password, new_password2):
        if not current_password or not new_password or not new_password2:
            return False, 'Заполните все поля'
        if len(new_password) < 6:
            return False, 'Новый пароль должен быть не короче 6 символов'
        if new_password != new_password2:
            return False, 'Новые пароли не совпадают'

        conn = get_db()
        try:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                return False, 'Пользователь не найден'
            if not check_password_hash(user['password_hash'], current_password):
                return False, 'Неверный текущий пароль'
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(new_password), user_id))
            conn.commit()
            return True, 'Пароль изменён'
        except Exception as e:
            conn.rollback()
            return False, f'Ошибка: {str(e)}'
        finally:
            conn.close()

    @staticmethod
    def get_profile(user_id):
        conn = get_db()
        try:
            row = conn.execute('''
                SELECT u.id, u.username, up.full_name, up.phone
                FROM users u
                LEFT JOIN user_profiles up ON u.id = up.user_id
                WHERE u.id = ?
            ''', (user_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


class Group:
    @staticmethod
    def get_all():
        conn = get_db()
        groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
        conn.close()
        return groups

    @staticmethod
    def get_by_id(gid):
        conn = get_db()
        group = conn.execute("SELECT * FROM groups WHERE id = ?", (gid,)).fetchone()
        conn.close()
        return group

    @staticmethod
    def create(name):
        conn = get_db()
        try:
            cur = conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
            new_id = cur.lastrowid
            conn.commit()
            conn.close()
            return True, "Группа создана", new_id
        except sqlite3.IntegrityError:
            conn.close()
            return False, "Группа с таким названием уже существует", None

    @staticmethod
    def update(gid, name):
        conn = get_db()
        try:
            conn.execute("UPDATE groups SET name = ? WHERE id = ?", (name, gid))
            conn.commit()
            conn.close()
            return True, "Группа обновлена"
        except sqlite3.IntegrityError:
            conn.close()
            return False, "Группа с таким названием уже существует"

    @staticmethod
    def delete(gid):
        conn = get_db()
        conn.execute("DELETE FROM groups WHERE id = ?", (gid,))
        conn.commit()
        conn.close()
        return True, "Группа удалена"


class Subject:
    @staticmethod
    def get_all():
        conn = get_db()
        subjects = conn.execute("SELECT * FROM subjects ORDER BY name").fetchall()
        conn.close()
        return subjects

    @staticmethod
    def get_by_id(sid):
        conn = get_db()
        subject = conn.execute("SELECT * FROM subjects WHERE id = ?", (sid,)).fetchone()
        conn.close()
        return subject

    @staticmethod
    def create(name):
        conn = get_db()
        cur = conn.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return True, "Предмет создан", new_id

    @staticmethod
    def update(sid, name, **kwargs):
        conn = get_db()
        conn.execute("UPDATE subjects SET name=? WHERE id=?", (name, sid))
        conn.commit()
        conn.close()
        return True, "Предмет обновлен"

    @staticmethod
    def delete(sid):
        conn = get_db()
        conn.execute("DELETE FROM subjects WHERE id = ?", (sid,))
        conn.commit()
        conn.close()
        return True, "Предмет удален"


class Student:
    @staticmethod
    def get_all():
        conn = get_db()
        students = conn.execute('''
            SELECT s.*, g.name as group_name 
            FROM students s JOIN groups g ON s.group_id=g.id 
            ORDER BY g.name, s.full_name
        ''').fetchall()
        conn.close()
        return students

    @staticmethod
    def get_by_group(gid):
        conn = get_db()
        students = conn.execute("SELECT * FROM students WHERE group_id = ? ORDER BY full_name", (gid,)).fetchall()
        conn.close()
        return students

    @staticmethod
    def get_by_id(sid):
        conn = get_db()
        student = conn.execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
        conn.close()
        return student

    @staticmethod
    def get_group_id(sid):
        conn = get_db()
        row = conn.execute("SELECT group_id FROM students WHERE id = ?", (sid,)).fetchone()
        conn.close()
        return row['group_id'] if row else None

    @staticmethod
    def create(gid, name):
        conn = get_db()
        try:
            cur = conn.execute("INSERT INTO students (group_id, full_name) VALUES (?, ?)", (gid, name))
            student_id = cur.lastrowid

            journals = conn.execute(
                "SELECT id FROM group_subjects WHERE group_id = ?", (gid,)
            ).fetchall()

            for journal in journals:
                gsid = journal['id']
                table_name = f"journal_{gsid}"

                table_exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                ).fetchone()

                if not table_exists:
                    continue

                lessons = conn.execute(f'''
                    SELECT DISTINCT date, time_interval, semester, topic, type
                    FROM {table_name}
                ''').fetchall()

                for lesson in lessons:
                    conn.execute(f'''
                        INSERT INTO {table_name} 
                        (student_id, date, time_interval, semester, topic, type, attendance, grade)
                        VALUES (?, ?, ?, ?, ?, ?, 'present', NULL)
                    ''', (
                        student_id,
                        lesson['date'],
                        lesson['time_interval'],
                        lesson['semester'],
                        lesson['topic'],
                        lesson['type']
                    ))

            conn.commit()
            conn.close()
            return True, "Студент добавлен", student_id
        except Exception as e:
            conn.rollback()
            conn.close()
            return False, f"Ошибка: {str(e)}", None

    @staticmethod
    def update(sid, gid, name):
        conn = get_db()
        conn.execute("UPDATE students SET group_id=?, full_name=? WHERE id=?", (gid, name, sid))
        conn.commit()
        conn.close()
        return True, "Данные обновлены"

    @staticmethod
    def delete(sid):
        conn = get_db()
        conn.execute("DELETE FROM students WHERE id = ?", (sid,))
        conn.commit()
        conn.close()
        return True, "Студент удален"

    @staticmethod
    def mass_transfer(student_ids, new_group_id, transfer_date, academic_year_id):
        """
        Массовый перевод студентов в другую группу.

        Параметры:
          student_ids      — список id студентов
          new_group_id     — id группы-приёмника
          transfer_date    — дата перевода (YYYY-MM-DD)
          academic_year_id — id учебного года

        Возвращает dict:
          {
            'transferred': N,      — сколько успешно переведено
            'skipped_same': N,     — пропущено (уже в этой группе)
            'skipped_dup': N,      — пропущено (однофамилец уже в новой группе)
            'errors': [str, ...]   — описания ошибок
            'details': [ {...} ]   — информация по каждому студенту
          }
        """
        if not student_ids:
            return {
                'transferred': 0,
                'skipped_same': 0,
                'skipped_dup': 0,
                'errors': ['Не выбрано ни одного студента'],
                'details': [],
            }

        conn = get_db()
        stats = {
            'transferred': 0,
            'skipped_same': 0,
            'skipped_dup': 0,
            'errors': [],
            'details': [],
        }

        try:
            # 1. Информация о новой группе
            new_group = conn.execute(
                "SELECT id, name FROM groups WHERE id = ?", (new_group_id,)
            ).fetchone()
            if not new_group:
                return {
                    'transferred': 0,
                    'skipped_same': 0,
                    'skipped_dup': 0,
                    'errors': ['Группа-приёмник не найдена'],
                    'details': [],
                }

            # 2. Список студентов, которых переводим (только существующие)
            placeholders = ','.join('?' for _ in student_ids)
            students_rows = conn.execute(f'''
                SELECT s.id, s.full_name, s.group_id, g.name AS group_name
                FROM students s
                JOIN groups g ON s.group_id = g.id
                WHERE s.id IN ({placeholders})
            ''', student_ids).fetchall()

            found_ids = {row['id'] for row in students_rows}
            missing = [sid for sid in student_ids if sid not in found_ids]
            for sid in missing:
                stats['errors'].append(f'Студент #{sid} не найден')
                stats['details'].append({
                    'student_id': sid,
                    'action': 'not_found',
                    'message': 'Не найден',
                })

            # 3. Собираем ФИО уже присутствующих в новой группе (для проверки дублей)
            existing_in_new = conn.execute(
                "SELECT LOWER(full_name) AS lname FROM students WHERE group_id = ?",
                (new_group_id,)
            ).fetchall()
            existing_names = {r['lname'] for r in existing_in_new}

            # 4. Журналы новой группы (для последующего заполнения)
            new_journals = conn.execute(
                "SELECT id FROM group_subjects WHERE group_id = ?",
                (new_group_id,)
            ).fetchall()
            new_journal_ids = [j['id'] for j in new_journals]

            # 5. Проходим по каждому студенту
            for row in students_rows:
                sid = row['id']
                sname = row['full_name']
                old_gid = row['group_id']
                old_gname = row['group_name']

                # 5.1. Уже в новой группе?
                if old_gid == new_group_id:
                    stats['skipped_same'] += 1
                    stats['details'].append({
                        'student_id': sid,
                        'name': sname,
                        'action': 'same_group',
                        'message': f'Уже в группе «{new_group["name"]}»',
                    })
                    continue

                # 5.2. Однофамилец в новой группе?
                if sname.lower() in existing_names:
                    stats['skipped_dup'] += 1
                    stats['details'].append({
                        'student_id': sid,
                        'name': sname,
                        'action': 'duplicate',
                        'message': f'В группе «{new_group["name"]}» уже есть студент с таким ФИО',
                    })
                    continue

                # 5.3. Всё ок — переводим
                # 5.3.1. Меняем group_id
                conn.execute(
                    "UPDATE students SET group_id = ? WHERE id = ?",
                    (new_group_id, sid)
                )

                # 5.3.2. Заполняем записи в журналах новой группы
                for gsid in new_journal_ids:
                    table_name = f"journal_{gsid}"

                    table_exists = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (table_name,)
                    ).fetchone()
                    if not table_exists:
                        continue

                    # Уникальные занятия
                    lessons = conn.execute(f'''
                        SELECT DISTINCT date, time_interval, semester, topic, type
                        FROM {table_name}
                    ''').fetchall()

                    for lesson in lessons:
                        # Проверим, нет ли уже такой записи (на всякий случай)
                        existing_entry = conn.execute(f'''
                            SELECT id FROM {table_name}
                            WHERE student_id = ? AND date = ? AND time_interval = ?
                            LIMIT 1
                        ''', (sid, lesson['date'], lesson['time_interval'])).fetchone()

                        if existing_entry:
                            continue

                        conn.execute(f'''
                            INSERT INTO {table_name}
                            (student_id, date, time_interval, semester, topic, type, attendance, grade)
                            VALUES (?, ?, ?, ?, ?, ?, 'present', NULL)
                        ''', (
                            sid,
                            lesson['date'],
                            lesson['time_interval'],
                            lesson['semester'],
                            lesson['topic'],
                            lesson['type']
                        ))

                # 5.3.3. Закрываем текущую запись в истории (если есть)
                conn.execute('''
                    UPDATE student_group_history
                    SET end_date = ?
                    WHERE student_id = ? AND end_date IS NULL
                ''', (transfer_date, sid))

                # 5.3.4. Создаём новую запись в истории
                conn.execute('''
                    INSERT INTO student_group_history
                    (student_id, group_id, academic_year_id, start_date, end_date)
                    VALUES (?, ?, ?, ?, NULL)
                ''', (sid, new_group_id, academic_year_id, transfer_date))

                stats['transferred'] += 1
                stats['details'].append({
                    'student_id': sid,
                    'name': sname,
                    'action': 'transferred',
                    'message': f'Переведён из «{old_gname}» в «{new_group["name"]}»',
                })

            conn.commit()

        except Exception as e:
            conn.rollback()
            stats['errors'].append(f'Критическая ошибка: {str(e)}')
        finally:
            conn.close()

        return stats


class StudentGroupHistory:
    @staticmethod
    def get_for_student(sid):
        """История переводов конкретного студента (новые сверху)."""
        conn = get_db()
        rows = conn.execute('''
            SELECT sgh.*, g.name AS group_name, ay.name AS academic_year_name
            FROM student_group_history sgh
            JOIN groups g ON sgh.group_id = g.id
            LEFT JOIN academic_years ay ON sgh.academic_year_id = ay.id
            WHERE sgh.student_id = ?
            ORDER BY sgh.start_date DESC, sgh.id DESC
        ''', (sid,)).fetchall()
        conn.close()
        return rows

    @staticmethod
    def add(student_id, group_id, academic_year_id, start_date, end_date=None):
        conn = get_db()
        try:
            conn.execute('''
                INSERT INTO student_group_history
                (student_id, group_id, academic_year_id, start_date, end_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (student_id, group_id, academic_year_id, start_date, end_date))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"[StudentGroupHistory] Ошибка: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def close_current(student_id, end_date):
        conn = get_db()
        try:
            conn.execute('''
                UPDATE student_group_history
                SET end_date = ?
                WHERE student_id = ? AND end_date IS NULL
            ''', (end_date, student_id))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"[StudentGroupHistory] Ошибка: {e}")
            return False
        finally:
            conn.close()


class GroupSubject:
    @staticmethod
    def get_all():
        conn = get_db()
        pairs = conn.execute('''
            SELECT gs.*, g.name as group_name, s.name as subject_name
            FROM group_subjects gs
            JOIN groups g ON gs.group_id=g.id
            JOIN subjects s ON gs.subject_id=s.id
            ORDER BY g.name, s.name
        ''').fetchall()
        conn.close()
        return pairs

    @staticmethod
    def get_by_id(gsid):
        conn = get_db()
        pair = conn.execute('''
            SELECT gs.*, g.name as group_name, s.name as subject_name
            FROM group_subjects gs
            JOIN groups g ON gs.group_id=g.id
            JOIN subjects s ON gs.subject_id=s.id
            WHERE gs.id=?
        ''', (gsid,)).fetchone()
        conn.close()
        return pair

    @staticmethod
    def create(gid, sid, semesters_data=None):
        conn = get_db()
        try:
            cur = conn.execute("INSERT INTO group_subjects (group_id, subject_id) VALUES (?, ?)", (gid, sid))
            gsid = cur.lastrowid

            conn.execute(f'''
                CREATE TABLE IF NOT EXISTS journal_{gsid} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    time_interval TEXT DEFAULT '',
                    semester INTEGER NOT NULL DEFAULT 1,
                    topic TEXT,
                    type TEXT DEFAULT 'lecture',
                    attendance TEXT DEFAULT 'present',
                    grade TEXT,
                    comment TEXT,
                    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
                )
            ''')

            if semesters_data:
                for sem in semesters_data:
                    conn.execute('''
                        INSERT INTO group_subject_hours 
                        (group_subject_id, semester, lecture_hours, practice_hours, independent_hours, exam_hours)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (gsid, sem['semester'], sem.get('lecture', 0), sem.get('practice', 0),
                          sem.get('independent', 0), sem.get('exam', 0)))
            else:
                conn.execute('''
                    INSERT INTO group_subject_hours 
                    (group_subject_id, semester, lecture_hours, practice_hours, independent_hours, exam_hours)
                    VALUES (?, 1, 0, 0, 0, 0)
                ''', (gsid,))

            conn.commit()
            conn.close()
            return True, "Пара создана", gsid
        except sqlite3.IntegrityError:
            conn.close()
            return False, "Такая пара уже существует", None

    @staticmethod
    def get_hours(gsid, semester=None):
        conn = get_db()
        if semester:
            hours = conn.execute(
                "SELECT * FROM group_subject_hours WHERE group_subject_id=? AND semester=?",
                (gsid, semester)
            ).fetchone()
            conn.close()
            if hours:
                return dict(hours)
            return {'lecture_hours': 0, 'practice_hours': 0, 'independent_hours': 0, 'exam_hours': 0,
                    'semester': semester}
        else:
            hours = conn.execute(
                "SELECT * FROM group_subject_hours WHERE group_subject_id=? ORDER BY semester",
                (gsid,)
            ).fetchall()
            conn.close()
            return [dict(h) for h in hours]

    @staticmethod
    def get_semesters(gsid):
        conn = get_db()
        semesters = conn.execute(
            "SELECT DISTINCT semester FROM group_subject_hours WHERE group_subject_id=? ORDER BY semester",
            (gsid,)
        ).fetchall()
        conn.close()
        return [s['semester'] for s in semesters]

    @staticmethod
    def delete(gsid):
        conn = get_db()
        conn.execute(f"DROP TABLE IF EXISTS journal_{gsid}")
        conn.execute("DELETE FROM group_subject_hours WHERE group_subject_id=?", (gsid,))
        conn.execute("DELETE FROM student_semester_grades WHERE group_subject_id=?", (gsid,))
        conn.execute("DELETE FROM group_subjects WHERE id=?", (gsid,))
        conn.commit()
        conn.close()
        return True, "Пара удалена"


class SemesterGrade:
    @staticmethod
    def set_grade(student_id, gsid, semester, grade):
        conn = get_db()
        ex = conn.execute(
            "SELECT id FROM student_semester_grades WHERE student_id=? AND group_subject_id=? AND semester=?",
            (student_id, gsid, semester)
        ).fetchone()
        if ex:
            conn.execute("UPDATE student_semester_grades SET grade=? WHERE id=?", (grade, ex['id']))
        else:
            conn.execute(
                "INSERT INTO student_semester_grades (student_id, group_subject_id, semester, grade) VALUES (?,?,?,?)",
                (student_id, gsid, semester, grade)
            )
        conn.commit()
        conn.close()

    @staticmethod
    def get_grades(gsid, semester):
        conn = get_db()
        grades = conn.execute('''
            SELECT ssg.*, s.full_name 
            FROM student_semester_grades ssg 
            JOIN students s ON ssg.student_id=s.id 
            WHERE ssg.group_subject_id=? AND ssg.semester=?
            ORDER BY s.full_name
        ''', (gsid, semester)).fetchall()
        conn.close()
        return grades

    @staticmethod
    def get_student_grade(student_id, gsid, semester):
        conn = get_db()
        grade = conn.execute(
            "SELECT * FROM student_semester_grades WHERE student_id=? AND group_subject_id=? AND semester=?",
            (student_id, gsid, semester)
        ).fetchone()
        conn.close()
        return grade['grade'] if grade else None


class UserProfile:
    @staticmethod
    def get_by_user_id(uid):
        conn = get_db()
        profile = conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (uid,)).fetchone()
        conn.close()
        return profile

    @staticmethod
    def save(uid, full_name, phone):
        conn = get_db()
        ex = conn.execute("SELECT id FROM user_profiles WHERE user_id = ?", (uid,)).fetchone()
        if ex:
            conn.execute("UPDATE user_profiles SET full_name=?, phone=? WHERE user_id=?", (full_name, phone, uid))
        else:
            conn.execute("INSERT INTO user_profiles (user_id, full_name, phone) VALUES (?,?,?)",
                         (uid, full_name, phone))
        conn.commit()
        conn.close()


class Position:
    @staticmethod
    def get_all():
        conn = get_db()
        positions = conn.execute("SELECT * FROM positions ORDER BY id").fetchall()
        conn.close()
        return positions

    @staticmethod
    def get_by_id(pid):
        conn = get_db()
        position = conn.execute("SELECT * FROM positions WHERE id = ?", (pid,)).fetchone()
        conn.close()
        return position

    @staticmethod
    def get_by_code(code):
        conn = get_db()
        position = conn.execute("SELECT * FROM positions WHERE code = ?", (code,)).fetchone()
        conn.close()
        return position

    @staticmethod
    def get_user_positions(uid):
        conn = get_db()
        positions = conn.execute('''
            SELECT p.* FROM positions p
            JOIN user_positions up ON p.id=up.position_id
            WHERE up.user_id=?
        ''', (uid,)).fetchall()
        conn.close()
        return positions

    @staticmethod
    def save(uid, pids):
        conn = get_db()
        conn.execute("DELETE FROM user_positions WHERE user_id = ?", (uid,))
        for pid in pids:
            try:
                conn.execute("INSERT INTO user_positions (user_id, position_id) VALUES (?,?)", (uid, int(pid)))
            except:
                pass
        conn.commit()
        conn.close()

    @staticmethod
    def count_users(pid):
        conn = get_db()
        cnt = conn.execute(
            "SELECT COUNT(*) as c FROM user_positions WHERE position_id = ?",
            (pid,)
        ).fetchone()['c']
        conn.close()
        return cnt


class PositionPermission:
    @staticmethod
    def get_for_position(position_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT permission_id FROM position_permissions WHERE position_id = ?",
            (position_id,)
        ).fetchall()
        conn.close()
        return [r['permission_id'] for r in rows]

    @staticmethod
    def set_for_position(position_id, permission_ids):
        conn = get_db()
        try:
            conn.execute("DELETE FROM position_permissions WHERE position_id = ?", (position_id,))
            for pid in permission_ids:
                try:
                    conn.execute(
                        "INSERT INTO position_permissions (position_id, permission_id) VALUES (?, ?)",
                        (position_id, int(pid))
                    )
                except:
                    pass
            conn.commit()
            return True, "Права роли сохранены"
        except Exception as e:
            conn.rollback()
            return False, f"Ошибка: {str(e)}"
        finally:
            conn.close()

    @staticmethod
    def get_permissions_for_user_via_positions(uid):
        conn = get_db()
        rows = conn.execute('''
            SELECT DISTINCT p.code
            FROM user_positions up
            JOIN position_permissions pp ON pp.position_id = up.position_id
            JOIN permissions p ON p.id = pp.permission_id
            WHERE up.user_id = ?
        ''', (uid,)).fetchall()
        conn.close()
        return [r['code'] for r in rows]


class Permission:
    @staticmethod
    def get_all():
        conn = get_db()
        permissions = conn.execute("SELECT * FROM permissions ORDER BY id").fetchall()
        conn.close()
        return permissions

    @staticmethod
    def get_personal_permissions(uid):
        conn = get_db()
        permissions = conn.execute('''
            SELECT p.code FROM permissions p
            JOIN user_permissions up ON p.id=up.permission_id
            WHERE up.user_id=?
        ''', (uid,)).fetchall()
        conn.close()
        return [p['code'] for p in permissions]

    @staticmethod
    def get_user_permissions(uid):
        personal = set(Permission.get_personal_permissions(uid))
        from_roles = set(PositionPermission.get_permissions_for_user_via_positions(uid))
        return sorted(personal | from_roles)

    @staticmethod
    def has_permission(uid, code):
        perms = Permission.get_user_permissions(uid)
        return code in perms

    @staticmethod
    def save(uid, pids):
        conn = get_db()
        conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (uid,))
        for pid in pids:
            try:
                conn.execute("INSERT INTO user_permissions (user_id, permission_id) VALUES (?,?)", (uid, int(pid)))
            except:
                pass
        conn.commit()
        conn.close()


class TeacherJournal:
    @staticmethod
    def assign(uid, gsid):
        conn = get_db()
        try:
            conn.execute("INSERT INTO teacher_journals (user_id, group_subject_id) VALUES (?,?)", (uid, gsid))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    @staticmethod
    def remove(uid, gsid):
        conn = get_db()
        conn.execute("DELETE FROM teacher_journals WHERE user_id=? AND group_subject_id=?", (uid, gsid))
        conn.commit()
        conn.close()

    @staticmethod
    def get_user_journals(uid):
        conn = get_db()
        journals = conn.execute('''
            SELECT gs.*, g.name as group_name, s.name as subject_name
            FROM teacher_journals tj
            JOIN group_subjects gs ON tj.group_subject_id=gs.id
            JOIN groups g ON gs.group_id=g.id
            JOIN subjects s ON gs.subject_id=s.id
            WHERE tj.user_id=?
            ORDER BY g.name, s.name
        ''', (uid,)).fetchall()
        conn.close()
        return journals


class Curator:
    @staticmethod
    def assign(uid, gid):
        conn = get_db()
        try:
            conn.execute("INSERT INTO curators (user_id, group_id) VALUES (?,?)", (uid, gid))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    @staticmethod
    def remove(uid, gid):
        conn = get_db()
        conn.execute("DELETE FROM curators WHERE user_id=? AND group_id=?", (uid, gid))
        conn.commit()
        conn.close()

    @staticmethod
    def get_user_groups(uid):
        conn = get_db()
        groups = conn.execute('''
            SELECT g.* FROM groups g
            JOIN curators c ON g.id=c.group_id
            WHERE c.user_id=?
        ''', (uid,)).fetchall()
        conn.close()
        return groups

    @staticmethod
    def is_curator(uid, gid):
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) as c FROM curators WHERE user_id=? AND group_id=?", (uid, gid)).fetchone()
        conn.close()
        return count['c'] > 0


class TeacherHours:
    @staticmethod
    def save(uid, gsid, semester, lh, ph, ih, eh):
        conn = get_db()
        ex = conn.execute(
            "SELECT id FROM teacher_hours WHERE user_id=? AND group_subject_id=? AND semester=?",
            (uid, gsid, semester)
        ).fetchone()
        if ex:
            conn.execute(
                "UPDATE teacher_hours SET lecture_hours=?, practice_hours=?, independent_hours=?, exam_hours=? WHERE id=?",
                (lh, ph, ih, eh, ex['id'])
            )
        else:
            conn.execute(
                "INSERT INTO teacher_hours (user_id, group_subject_id, semester, lecture_hours, practice_hours, independent_hours, exam_hours) VALUES (?,?,?,?,?,?,?)",
                (uid, gsid, semester, lh, ph, ih, eh)
            )
        conn.commit()
        conn.close()

    @staticmethod
    def save_with_conn(conn, uid, gsid, semester, lh, ph, ih, eh):
        ex = conn.execute(
            "SELECT id FROM teacher_hours WHERE user_id=? AND group_subject_id=? AND semester=?",
            (uid, gsid, semester)
        ).fetchone()
        if ex:
            conn.execute(
                "UPDATE teacher_hours SET lecture_hours=?, practice_hours=?, independent_hours=?, exam_hours=? WHERE id=?",
                (lh, ph, ih, eh, ex['id'])
            )
        else:
            conn.execute(
                "INSERT INTO teacher_hours (user_id, group_subject_id, semester, lecture_hours, practice_hours, independent_hours, exam_hours) VALUES (?,?,?,?,?,?,?)",
                (uid, gsid, semester, lh, ph, ih, eh)
            )

    @staticmethod
    def get(uid, gsid, semester=None):
        conn = get_db()
        if semester:
            hours = conn.execute(
                "SELECT * FROM teacher_hours WHERE user_id=? AND group_subject_id=? AND semester=?",
                (uid, gsid, semester)
            ).fetchone()
        else:
            hours = conn.execute(
                "SELECT * FROM teacher_hours WHERE user_id=? AND group_subject_id=? ORDER BY semester",
                (uid, gsid)
            ).fetchall()
        conn.close()
        return hours