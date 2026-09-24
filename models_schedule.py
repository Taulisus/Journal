"""
Модели для расписания, преподавателей, аудиторий, учебных годов и алиасов групп.

Импортирует get_db из models, чтобы не дублировать подключение к БД.
"""

import sqlite3
from datetime import datetime, timedelta

from models import get_db


# ============================================================
#                 УЧЕБНЫЕ ГОДЫ
# ============================================================

class AcademicYear:
    @staticmethod
    def get_all():
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM academic_years ORDER BY start_date DESC"
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_by_id(year_id):
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM academic_years WHERE id = ?", (year_id,)
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def get_current():
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM academic_years WHERE is_current = 1 LIMIT 1"
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def create(name, start_date, end_date, is_current=False):
        conn = get_db()
        try:
            if is_current:
                conn.execute("UPDATE academic_years SET is_current = 0")
            cur = conn.execute(
                "INSERT INTO academic_years (name, start_date, end_date, is_current) "
                "VALUES (?, ?, ?, ?)",
                (name, start_date, end_date, 1 if is_current else 0),
            )
            conn.commit()
            new_id = cur.lastrowid
            return True, "Учебный год создан", new_id
        except sqlite3.IntegrityError:
            return False, "Такой учебный год уже существует", None
        finally:
            conn.close()

    @staticmethod
    def set_current(year_id):
        conn = get_db()
        try:
            conn.execute("UPDATE academic_years SET is_current = 0")
            conn.execute(
                "UPDATE academic_years SET is_current = 1 WHERE id = ?",
                (year_id,),
            )
            conn.commit()
            return True, "Текущий учебный год обновлён"
        except Exception as e:
            conn.rollback()
            return False, f"Ошибка: {e}"
        finally:
            conn.close()


# ============================================================
#                 ПРЕПОДАВАТЕЛИ
# ============================================================

class Teacher:
    @staticmethod
    def get_all(active_only=True):
        conn = get_db()
        if active_only:
            rows = conn.execute(
                "SELECT * FROM teachers WHERE is_active = 1 ORDER BY short_name, full_name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM teachers ORDER BY short_name, full_name"
            ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_by_id(tid):
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM teachers WHERE id = ?", (tid,)
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def get_by_full_name(full_name):
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM teachers WHERE full_name = ?", (full_name,)
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def find_by_short_name(short_name):
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM teachers WHERE short_name = ?", (short_name,)
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def create(full_name, short_name=None):
        if not full_name:
            return False, "ФИО не может быть пустым", None

        if not short_name:
            short_name = Teacher.make_short_name(full_name)

        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO teachers (full_name, short_name, is_active) "
                "VALUES (?, ?, 1)",
                (full_name, short_name),
            )
            conn.commit()
            new_id = cur.lastrowid
            return True, "Преподаватель добавлен", new_id
        except sqlite3.IntegrityError:
            return False, "Преподаватель с таким ФИО уже существует", None
        finally:
            conn.close()

    @staticmethod
    def update(tid, full_name, short_name=None, is_active=1):
        conn = get_db()
        try:
            if not short_name:
                short_name = Teacher.make_short_name(full_name)
            conn.execute(
                "UPDATE teachers SET full_name=?, short_name=?, is_active=? WHERE id=?",
                (full_name, short_name, int(is_active), tid),
            )
            conn.commit()
            return True, "Преподаватель обновлён"
        except sqlite3.IntegrityError:
            return False, "Преподаватель с таким ФИО уже существует"
        finally:
            conn.close()

    @staticmethod
    def delete(tid):
        conn = get_db()
        try:
            conn.execute("DELETE FROM teachers WHERE id = ?", (tid,))
            conn.commit()
            return True, "Преподаватель удалён"
        except Exception as e:
            conn.rollback()
            return False, f"Ошибка: {e}"
        finally:
            conn.close()

    @staticmethod
    def make_short_name(full_name):
        """
        'Ватолина Ольга Альбертовна' -> 'Ватолина О.А.'
        'Ватолина О.А.' -> 'Ватолина О.А.' (без изменений)
        """
        if not full_name:
            return ''
        parts = full_name.strip().split()
        if len(parts) < 2:
            return full_name

        surname = parts[0]
        initials = []
        for p in parts[1:]:
            if not p:
                continue
            # Если это уже инициал с точкой ('О.'), берём первую букву
            letter = p[0].upper()
            initials.append(letter)

        if not initials:
            return surname
        return f"{surname} {'.'.join(initials)}."

    @staticmethod
    def search(query, limit=20):
        """
        Поиск по подстроке в full_name или short_name.
        Используется для autocomplete.
        """
        if not query:
            return []
        q = f"%{query.strip().lower()}%"
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM teachers "
            "WHERE LOWER(full_name) LIKE ? OR LOWER(short_name) LIKE ? "
            "ORDER BY short_name LIMIT ?",
            (q, q, limit),
        ).fetchall()
        conn.close()
        return rows


# ============================================================
#                 АУДИТОРИИ
# ============================================================

class Room:
    @staticmethod
    def get_all():
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM rooms ORDER BY building, name"
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_by_id(rid):
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM rooms WHERE id = ?", (rid,)
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def get_by_name(name):
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM rooms WHERE name = ?", (name,)
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def create(name, building=None, capacity=None, room_type='classroom'):
        if not name:
            return False, "Название не может быть пустым", None
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO rooms (name, building, capacity, room_type) "
                "VALUES (?, ?, ?, ?)",
                (name, building, capacity, room_type),
            )
            conn.commit()
            new_id = cur.lastrowid
            return True, "Аудитория добавлена", new_id
        except sqlite3.IntegrityError:
            return False, "Аудитория с таким названием уже существует", None
        finally:
            conn.close()

    @staticmethod
    def update(rid, name, building=None, capacity=None, room_type='classroom'):
        conn = get_db()
        try:
            conn.execute(
                "UPDATE rooms SET name=?, building=?, capacity=?, room_type=? WHERE id=?",
                (name, building, capacity, room_type, rid),
            )
            conn.commit()
            return True, "Аудитория обновлена"
        except sqlite3.IntegrityError:
            return False, "Аудитория с таким названием уже существует"
        finally:
            conn.close()

    @staticmethod
    def delete(rid):
        conn = get_db()
        try:
            conn.execute("DELETE FROM rooms WHERE id = ?", (rid,))
            conn.commit()
            return True, "Аудитория удалена"
        except Exception as e:
            conn.rollback()
            return False, f"Ошибка: {e}"
        finally:
            conn.close()

    @staticmethod
    def find_or_create(name, building=None, room_type='classroom'):
        """
        Ищет аудиторию по имени, если нет — создаёт.
        Возвращает id (или None, если name пустой).
        """
        if not name:
            return None
        name = name.strip()
        existing = Room.get_by_name(name)
        if existing:
            return existing['id']
        ok, msg, new_id = Room.create(name, building=building, room_type=room_type)
        return new_id if ok else None


# ============================================================
#                 АЛИАСЫ ГРУПП
# ============================================================

class GroupAlias:
    @staticmethod
    def get_all():
        conn = get_db()
        rows = conn.execute(
            "SELECT ga.*, g.name AS group_name "
            "FROM group_aliases ga JOIN groups g ON ga.group_id = g.id "
            "ORDER BY ga.alias"
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_for_group(group_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM group_aliases WHERE group_id = ? ORDER BY alias",
            (group_id,),
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def resolve(alias):
        """
        Возвращает group_id по алиасу, или None.
        Сравнение без учёта регистра и пробелов.
        """
        if not alias:
            return None
        key = alias.strip().lower()
        conn = get_db()
        row = conn.execute(
            "SELECT group_id FROM group_aliases WHERE LOWER(alias) = ?",
            (key,),
        ).fetchone()
        conn.close()
        return row['group_id'] if row else None

    @staticmethod
    def add(group_id, alias):
        if not alias:
            return False, "Алиас не может быть пустым", None
        alias = alias.strip()
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO group_aliases (group_id, alias) VALUES (?, ?)",
                (group_id, alias),
            )
            conn.commit()
            new_id = cur.lastrowid
            return True, "Алиас добавлен", new_id
        except sqlite3.IntegrityError:
            return False, "Такой алиас уже существует", None
        finally:
            conn.close()

    @staticmethod
    def delete(alias_id):
        conn = get_db()
        try:
            conn.execute("DELETE FROM group_aliases WHERE id = ?", (alias_id,))
            conn.commit()
            return True, "Алиас удалён"
        except Exception as e:
            conn.rollback()
            return False, f"Ошибка: {e}"
        finally:
            conn.close()


# ============================================================
#                 РАСПИСАНИЕ
# ============================================================

class ScheduleLesson:
    """
    Одно занятие в расписании — конкретная дата, пара, группа, предмет,
    преподаватель, аудитория.
    """

    # Дни недели: 0 = Пн, 6 = Вс (совпадает с datetime.weekday())
    DAY_NAMES_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    DAY_NAMES_FULL = [
        'Понедельник', 'Вторник', 'Среда', 'Четверг',
        'Пятница', 'Суббота', 'Воскресенье',
    ]

    @staticmethod
    def get_by_id(lesson_id):
        conn = get_db()
        row = conn.execute('''
            SELECT sl.*,
                   g.name AS group_name,
                   s.name AS subject_name,
                   t.full_name AS teacher_full_name,
                   t.short_name AS teacher_short_name,
                   r.name AS room_resolved_name,
                   r.building AS room_building
            FROM schedule_lessons sl
            LEFT JOIN groups g ON sl.group_id = g.id
            LEFT JOIN subjects s ON sl.subject_id = s.id
            LEFT JOIN teachers t ON sl.teacher_id = t.id
            LEFT JOIN rooms r ON sl.room_id = r.id
            WHERE sl.id = ?
        ''', (lesson_id,)).fetchone()
        conn.close()
        return row

    @staticmethod
    def get_for_date(date_str, group_id=None, teacher_id=None, room_id=None):
        """
        Расписание на конкретную дату (YYYY-MM-DD).
        Все фильтры опциональны.
        """
        where = ["sl.date = ?"]
        params = [date_str]

        if group_id:
            where.append("sl.group_id = ?")
            params.append(group_id)
        if teacher_id:
            where.append("sl.teacher_id = ?")
            params.append(teacher_id)
        if room_id:
            where.append("sl.room_id = ?")
            params.append(room_id)

        sql = f'''
            SELECT sl.*,
                   g.name AS group_name,
                   s.name AS subject_name,
                   t.full_name AS teacher_full_name,
                   t.short_name AS teacher_short_name,
                   r.name AS room_resolved_name,
                   r.building AS room_building
            FROM schedule_lessons sl
            LEFT JOIN groups g ON sl.group_id = g.id
            LEFT JOIN subjects s ON sl.subject_id = s.id
            LEFT JOIN teachers t ON sl.teacher_id = t.id
            LEFT JOIN rooms r ON sl.room_id = r.id
            WHERE {" AND ".join(where)}
            ORDER BY sl.pair_number, sl.time_start, g.name
        '''

        conn = get_db()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_for_date_range(date_from, date_to, group_id=None,
                           teacher_id=None, room_id=None):
        """
        Расписание за диапазон дат (включительно).
        """
        where = ["sl.date >= ?", "sl.date <= ?"]
        params = [date_from, date_to]

        if group_id:
            where.append("sl.group_id = ?")
            params.append(group_id)
        if teacher_id:
            where.append("sl.teacher_id = ?")
            params.append(teacher_id)
        if room_id:
            where.append("sl.room_id = ?")
            params.append(room_id)

        sql = f'''
            SELECT sl.*,
                   g.name AS group_name,
                   s.name AS subject_name,
                   t.full_name AS teacher_full_name,
                   t.short_name AS teacher_short_name,
                   r.name AS room_resolved_name,
                   r.building AS room_building
            FROM schedule_lessons sl
            LEFT JOIN groups g ON sl.group_id = g.id
            LEFT JOIN subjects s ON sl.subject_id = s.id
            LEFT JOIN teachers t ON sl.teacher_id = t.id
            LEFT JOIN rooms r ON sl.room_id = r.id
            WHERE {" AND ".join(where)}
            ORDER BY sl.date, sl.pair_number, sl.time_start, g.name
        '''

        conn = get_db()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_week(start_date):
        """
        Расписание на неделю, начиная с start_date (понедельник).
        Возвращает dict: {date_str: [lessons]}.
        """
        if isinstance(start_date, str):
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start = start_date

        # Если start_date не понедельник — сдвигаем к понедельнику
        start = start - timedelta(days=start.weekday())
        end = start + timedelta(days=6)

        lessons = ScheduleLesson.get_for_date_range(
            start.isoformat(), end.isoformat()
        )

        # Группируем по датам, включая пустые дни
        week = {}
        current = start
        while current <= end:
            week[current.isoformat()] = []
            current += timedelta(days=1)

        for lesson in lessons:
            d = lesson['date']
            if d in week:
                week[d].append(lesson)

        return week, start, end

    @staticmethod
    def get_today(group_id=None, teacher_id=None, room_id=None):
        return ScheduleLesson.get_for_date(
            datetime.now().strftime('%Y-%m-%d'),
            group_id=group_id,
            teacher_id=teacher_id,
            room_id=room_id,
        )

    @staticmethod
    def create(academic_year_id, date, pair_number, time_start, time_end,
               group_id, subject_id, teacher_id=None, teacher_name_raw=None,
               room_id=None, room_name_raw=None, lesson_type='lecture',
               original_group_name=None, source_file=None):
        """
        Создаёт одно занятие.
        day_of_week вычисляется автоматически из date.
        """
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
            day_of_week = dt.weekday()
        except (ValueError, TypeError):
            return False, "Некорректная дата (ожидается YYYY-MM-DD)", None

        conn = get_db()
        try:
            cur = conn.execute('''
                INSERT INTO schedule_lessons
                (academic_year_id, date, day_of_week, pair_number,
                 time_start, time_end, group_id, subject_id,
                 teacher_id, teacher_name_raw, room_id, room_name_raw,
                 lesson_type, original_group_name, source_file, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                academic_year_id, date, day_of_week, pair_number,
                time_start, time_end, group_id, subject_id,
                teacher_id, teacher_name_raw, room_id, room_name_raw,
                lesson_type, original_group_name, source_file,
                datetime.now().isoformat(timespec='seconds'),
            ))
            conn.commit()
            new_id = cur.lastrowid
            return True, "Занятие добавлено в расписание", new_id
        except sqlite3.IntegrityError as e:
            return False, f"Ошибка целостности: {e}", None
        except Exception as e:
            conn.rollback()
            return False, f"Ошибка: {e}", None
        finally:
            conn.close()

    @staticmethod
    def update(lesson_id, **fields):
        """
        Обновляет поля занятия.
        Допустимые ключи: date, pair_number, time_start, time_end,
        group_id, subject_id, teacher_id, room_id, lesson_type.
        """
        allowed = {
            'date', 'pair_number', 'time_start', 'time_end',
            'group_id', 'subject_id', 'teacher_id', 'room_id',
            'lesson_type',
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False, "Нечего обновлять"

        # Если меняется date — пересчитываем day_of_week
        if 'date' in updates:
            try:
                dt = datetime.strptime(updates['date'], '%Y-%m-%d')
                updates['day_of_week'] = dt.weekday()
            except (ValueError, TypeError):
                return False, "Некорректная дата"
            allowed.add('day_of_week')

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [lesson_id]

        conn = get_db()
        try:
            conn.execute(
                f"UPDATE schedule_lessons SET {set_clause} WHERE id = ?",
                params,
            )
            conn.commit()
            return True, "Занятие обновлено"
        except Exception as e:
            conn.rollback()
            return False, f"Ошибка: {e}"
        finally:
            conn.close()

    @staticmethod
    def delete(lesson_id):
        conn = get_db()
        try:
            conn.execute("DELETE FROM schedule_lessons WHERE id = ?", (lesson_id,))
            conn.commit()
            return True, "Занятие удалено из расписания"
        except Exception as e:
            conn.rollback()
            return False, f"Ошибка: {e}"
        finally:
            conn.close()

    @staticmethod
    def delete_for_date(date_str):
        """Удаляет все занятия на дату (для повторного импорта)."""
        conn = get_db()
        try:
            cur = conn.execute(
                "DELETE FROM schedule_lessons WHERE date = ?", (date_str,)
            )
            deleted = cur.rowcount
            conn.commit()
            return True, deleted
        except Exception as e:
            conn.rollback()
            return False, 0
        finally:
            conn.close()

    @staticmethod
    def delete_week(start_date):
        """Удаляет все занятия за неделю (для повторного импорта)."""
        if isinstance(start_date, str):
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start = start_date
        start = start - timedelta(days=start.weekday())
        end = start + timedelta(days=6)

        conn = get_db()
        try:
            cur = conn.execute(
                "DELETE FROM schedule_lessons WHERE date >= ? AND date <= ?",
                (start.isoformat(), end.isoformat()),
            )
            deleted = cur.rowcount
            conn.commit()
            return True, deleted
        except Exception as e:
            conn.rollback()
            return False, 0
        finally:
            conn.close()

    @staticmethod
    def get_free_rooms_now(date_str, time_start, time_end):
        """
        Возвращает список аудиторий, которые НЕ заняты в указанное время.
        Учитываем только аудитории, у которых room_type != 'none'.
        """
        conn = get_db()
        try:
            busy = conn.execute('''
                SELECT DISTINCT room_id FROM schedule_lessons
                WHERE date = ?
                  AND room_id IS NOT NULL
                  AND NOT (time_end <= ? OR time_start >= ?)
            ''', (date_str, time_start, time_end)).fetchall()

            busy_ids = {r['room_id'] for r in busy}

            all_rooms = conn.execute(
                "SELECT * FROM rooms WHERE room_type != 'none' ORDER BY building, name"
            ).fetchall()

            return [r for r in all_rooms if r['id'] not in busy_ids]
        finally:
            conn.close()

    @staticmethod
    def get_teacher_lessons_for_date(teacher_id, date_str):
        return ScheduleLesson.get_for_date(date_str, teacher_id=teacher_id)

    @staticmethod
    def get_group_lessons_for_date(group_id, date_str):
        return ScheduleLesson.get_for_date(date_str, group_id=group_id)

    @staticmethod
    def count_for_date_range(date_from, date_to):
        """Сколько занятий в диапазоне — для статистики импорта."""
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM schedule_lessons "
                "WHERE date >= ? AND date <= ?",
                (date_from, date_to),
            ).fetchone()
            return row['c'] if row else 0
        finally:
            conn.close()

    @staticmethod
    def get_dates_with_lessons(limit=50):
        """Список дат, по которым есть расписание (для навигации)."""
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT DISTINCT date FROM schedule_lessons "
                "ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [r['date'] for r in rows]
        finally:
            conn.close()