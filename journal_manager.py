from models import get_db
from datetime import datetime


class JournalManager:
    @staticmethod
    def get_table_name(gs_id):
        return f"journal_{gs_id}"

    @staticmethod
    def format_date(date_str):
        """Преобразует дату из YYYY-MM-DD в DD.MM.YYYY"""
        if not date_str:
            return ''
        try:
            parts = date_str.split('-')
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
        except:
            pass
        return date_str

    @staticmethod
    def format_date_short(date_str):
        """Преобразует дату в формат '17 сен'"""
        if not date_str:
            return ''

        months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
                  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

        try:
            parts = date_str.split('-')
            if len(parts) == 3:
                day = int(parts[2])
                month = int(parts[1]) - 1
                return f"{day} {months[month]}"
        except:
            pass
        return date_str

    @staticmethod
    def get_day_of_week(date_str):
        """Возвращает день недели для даты YYYY-MM-DD"""
        if not date_str:
            return ''

        days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return days[dt.weekday()]
        except:
            return ''

    @staticmethod
    def add_lesson(gs_id, date, time_interval, topic, lesson_type, semester, students_data):
        """
        Добавляет занятие для всех студентов группы.
        students_data = {
            student_id: {'attendance': 'present'/'absent', 'grade': '5'/'4'/.../None}
        }
        """
        conn = get_db()
        table_name = JournalManager.get_table_name(gs_id)

        # Проверяем, не пытаются ли добавить занятие после экзамена
        if lesson_type != 'exam':
            exam_exists = conn.execute(
                f"SELECT COUNT(*) as c FROM {table_name} WHERE semester=? AND type='exam'",
                (semester,)
            ).fetchone()
            if exam_exists['c'] > 0:
                conn.close()
                return False, "Нельзя добавить занятие после экзамена! Экзамен уже проведен в этом семестре."

        # Проверяем, не пытаются ли добавить второй экзамен
        if lesson_type == 'exam':
            exam_exists = conn.execute(
                f"SELECT COUNT(*) as c FROM {table_name} WHERE semester=? AND type='exam'",
                (semester,)
            ).fetchone()
            if exam_exists['c'] > 0:
                conn.close()
                return False, "Экзамен в этом семестре уже проведен! Нельзя добавить второй экзамен."

        for student_id, data in students_data.items():
            conn.execute(f'''
                INSERT INTO {table_name} (student_id, date, time_interval, semester, topic, type, attendance, grade)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                student_id, date, time_interval, semester, topic, lesson_type,
                data.get('attendance', 'present'),
                data.get('grade') if data.get('grade') else None
            ))
        conn.commit()
        conn.close()
        return True, "Занятие добавлено"

    @staticmethod
    def _parse_time(time_str):
        """Парсит время для сортировки."""
        if not time_str:
            return (99, 99)

        time_str = time_str.strip()

        if 'пара' in time_str.lower():
            try:
                para_num = int(''.join(filter(str.isdigit, time_str)))
                return (para_num, 0)
            except:
                return (99, 99)

        parts = time_str.split('-')[0].strip().split(':')
        try:
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            return (hours, minutes)
        except:
            return (99, 99)

    @staticmethod
    def get_journal(gs_id, semester=None):
        """Получает все записи журнала, структурированные по датам и времени"""
        conn = get_db()
        table_name = JournalManager.get_table_name(gs_id)

        if semester:
            entries = conn.execute(f'''
                SELECT * FROM {table_name} WHERE semester=? 
                ORDER BY 
                    CASE WHEN type='exam' THEN 1 ELSE 0 END,
                    date, 
                    id
            ''', (semester,)).fetchall()
        else:
            entries = conn.execute(f'''
                SELECT * FROM {table_name} 
                ORDER BY 
                    CASE WHEN type='exam' THEN 1 ELSE 0 END,
                    date, 
                    id
            ''').fetchall()
        conn.close()

        lessons_dict = {}
        for entry in entries:
            lesson_key = f"{entry['date']}_{entry['time_interval']}"
            if lesson_key not in lessons_dict:
                lessons_dict[lesson_key] = {
                    'date': entry['date'],
                    'date_formatted': JournalManager.format_date(entry['date']),
                    'date_short': JournalManager.format_date_short(entry['date']),
                    'day_of_week': JournalManager.get_day_of_week(entry['date']),
                    'time_interval': entry['time_interval'],
                    'semester': entry['semester'],
                    'topic': entry['topic'],
                    'type': entry['type'],
                    'entries': {}
                }
            lessons_dict[lesson_key]['entries'][entry['student_id']] = {
                'id': entry['id'],
                'attendance': entry['attendance'],
                'grade': entry['grade']
            }

        sorted_lessons = sorted(
            lessons_dict.values(),
            key=lambda x: (
                1 if x['type'] == 'exam' else 0,
                x['date'],
                JournalManager._parse_time(x['time_interval'])
            )
        )

        return sorted_lessons

    @staticmethod
    def update_entry(gs_id, entry_id, attendance, grade):
        """Обновляет запись о посещении и оценке"""
        conn = get_db()
        table_name = JournalManager.get_table_name(gs_id)
        conn.execute(f'''
            UPDATE {table_name} 
            SET attendance = ?, grade = ?
            WHERE id = ?
        ''', (attendance, grade if grade else None, entry_id))
        conn.commit()
        conn.close()
        return True, "Запись обновлена"

    @staticmethod
    def update_lesson_type(gs_id, date, time_interval, semester, new_type):
        """Изменяет тип занятия для всех записей с указанной датой и временем"""
        conn = get_db()
        table_name = JournalManager.get_table_name(gs_id)

        try:
            # Если меняем на exam - проверяем, нет ли уже экзамена
            if new_type == 'exam':
                exam_exists = conn.execute(
                    f"SELECT COUNT(*) as c FROM {table_name} WHERE semester=? AND type='exam' AND NOT (date=? AND time_interval=?)",
                    (semester, date, time_interval)
                ).fetchone()
                if exam_exists['c'] > 0:
                    conn.close()
                    return False, "Экзамен в этом семестре уже существует!"

            # Обновляем тип для всех записей с этой датой и временем
            conn.execute(f'''
                UPDATE {table_name} 
                SET type = ?
                WHERE date = ? AND time_interval = ? AND semester = ?
            ''', (new_type, date, time_interval, semester))

            conn.commit()
            conn.close()
            return True, "Тип занятия обновлен"
        except Exception as e:
            conn.close()
            return False, f"Ошибка: {str(e)}"

    @staticmethod
    def delete_lesson(gs_id, date, time_interval):
        """Удаляет все записи за определенную дату и время"""
        conn = get_db()
        table_name = JournalManager.get_table_name(gs_id)
        conn.execute(f"DELETE FROM {table_name} WHERE date = ? AND time_interval = ?",
                     (date, time_interval))
        conn.commit()
        conn.close()
        return True, "Занятие удалено"

    @staticmethod
    def get_statistics(gs_id, semester=None):
        """
        Получает общую статистику по журналу.
        Исключает из посещаемости типы: independent (С/Р) и dictation (под запись).
        """
        conn = get_db()
        table_name = JournalManager.get_table_name(gs_id)

        excluded_types = "('independent', 'dictation')"

        if semester:
            stats = conn.execute(f'''
                SELECT 
                    COUNT(DISTINCT date || time_interval) as total_lessons,
                    SUM(CASE WHEN attendance = 'absent' AND type NOT IN {excluded_types} THEN 1 ELSE 0 END) as total_absences,
                    AVG(CASE WHEN grade IS NOT NULL AND grade != 'passed' AND type NOT IN {excluded_types} THEN CAST(grade AS FLOAT) END) as avg_grade
                FROM {table_name}
                WHERE semester = ?
            ''', (semester,)).fetchone()

            students_stats = conn.execute(f'''
                SELECT 
                    student_id,
                    COUNT(CASE WHEN type NOT IN {excluded_types} THEN 1 END) as total_entries,
                    SUM(CASE WHEN attendance = 'absent' AND type NOT IN {excluded_types} THEN 1 ELSE 0 END) as absences,
                    SUM(CASE WHEN attendance = 'present' AND type NOT IN {excluded_types} THEN 1 ELSE 0 END) as attendances,
                    AVG(CASE WHEN grade IS NOT NULL AND grade != 'passed' AND type NOT IN {excluded_types} THEN CAST(grade AS FLOAT) END) as avg_grade
                FROM {table_name}
                WHERE semester = ?
                GROUP BY student_id
            ''', (semester,)).fetchall()
        else:
            stats = conn.execute(f'''
                SELECT 
                    COUNT(DISTINCT date || time_interval) as total_lessons,
                    SUM(CASE WHEN attendance = 'absent' AND type NOT IN {excluded_types} THEN 1 ELSE 0 END) as total_absences,
                    AVG(CASE WHEN grade IS NOT NULL AND grade != 'passed' AND type NOT IN {excluded_types} THEN CAST(grade AS FLOAT) END) as avg_grade
                FROM {table_name}
            ''').fetchone()

            students_stats = conn.execute(f'''
                SELECT 
                    student_id,
                    COUNT(CASE WHEN type NOT IN {excluded_types} THEN 1 END) as total_entries,
                    SUM(CASE WHEN attendance = 'absent' AND type NOT IN {excluded_types} THEN 1 ELSE 0 END) as absences,
                    SUM(CASE WHEN attendance = 'present' AND type NOT IN {excluded_types} THEN 1 ELSE 0 END) as attendances,
                    AVG(CASE WHEN grade IS NOT NULL AND grade != 'passed' AND type NOT IN {excluded_types} THEN CAST(grade AS FLOAT) END) as avg_grade
                FROM {table_name}
                GROUP BY student_id
            ''').fetchall()

        conn.close()
        return {
            'total_lessons': stats['total_lessons'] or 0,
            'total_absences': stats['total_absences'] or 0,
            'avg_grade': round(stats['avg_grade'] or 0, 2),
            'students': students_stats
        }

    @staticmethod
    def get_student_stats(gs_id, student_id):
        """
        Получает статистику конкретного студента по журналу.
        Исключает из посещаемости типы: independent (С/Р) и dictation (под запись).
        """
        conn = get_db()
        table_name = JournalManager.get_table_name(gs_id)

        excluded_types = "('independent', 'dictation')"

        try:
            # Статистика ТОЛЬКО по учитываемым типам
            stats = conn.execute(f'''
                SELECT 
                    COUNT(*) as total_lessons,
                    SUM(CASE WHEN attendance = 'absent' THEN 1 ELSE 0 END) as absences,
                    SUM(CASE WHEN attendance = 'present' THEN 1 ELSE 0 END) as attendances,
                    AVG(CASE WHEN grade IS NOT NULL AND grade != 'passed' THEN CAST(grade AS FLOAT) END) as avg_grade
                FROM {table_name}
                WHERE student_id = ? AND type NOT IN {excluded_types}
            ''', (student_id,)).fetchone()

            # Полный список ВСЕХ занятий для отображения
            grades = conn.execute(f'''
                SELECT date, time_interval, type, topic, grade, attendance, semester
                FROM {table_name}
                WHERE student_id = ?
                ORDER BY date, time_interval
            ''', (student_id,)).fetchall()

            conn.close()

            # Если нет ни одной записи
            if len(grades) == 0:
                return None

            # Считаем процент пропусков от учитываемых занятий
            considered = (stats['absences'] or 0) + (stats['attendances'] or 0)

            return {
                'total_lessons': stats['total_lessons'] or 0,
                'absences': stats['absences'] or 0,
                'attendances': stats['attendances'] or 0,
                'avg_grade': round(stats['avg_grade'] or 0, 2),
                'grades_list': grades,
                'absence_percent': round(
                    ((stats['absences'] or 0) / considered * 100) if considered > 0 else 0,
                    1
                )
            }
        except Exception as e:
            conn.close()
            print(f"Ошибка при получении статистики студента: {e}")
            return None

    @staticmethod
    def get_conducted_hours(gs_id, semester=None):
        """
        Подсчитывает фактически проведенные часы по типам занятий.
        Обычное занятие = 2 академических часа.
        Экзамен считается отдельно (часы из group_subject_hours).
        """
        conn = get_db()
        table_name = JournalManager.get_table_name(gs_id)

        try:
            if semester:
                hours = conn.execute(f'''
                    SELECT type, COUNT(DISTINCT date || time_interval) as lesson_count
                    FROM {table_name}
                    WHERE semester = ? AND type != 'exam'
                    GROUP BY type
                ''', (semester,)).fetchall()

                exam_count = conn.execute(f'''
                    SELECT COUNT(DISTINCT date || time_interval) as cnt 
                    FROM {table_name} 
                    WHERE semester = ? AND type = 'exam'
                ''', (semester,)).fetchone()

                exam_hours_from_db = conn.execute(
                    "SELECT exam_hours FROM group_subject_hours WHERE group_subject_id=? AND semester=?",
                    (gs_id, semester)
                ).fetchone()
            else:
                hours = conn.execute(f'''
                    SELECT type, COUNT(DISTINCT date || time_interval) as lesson_count
                    FROM {table_name}
                    WHERE type != 'exam'
                    GROUP BY type
                ''').fetchall()

                exam_count = conn.execute(f'''
                    SELECT COUNT(DISTINCT date || time_interval) as cnt 
                    FROM {table_name} 
                    WHERE type = 'exam'
                ''').fetchone()

                exam_hours_from_db = conn.execute(
                    "SELECT exam_hours FROM group_subject_hours WHERE group_subject_id=?",
                    (gs_id,)
                ).fetchone()

            conn.close()

            result = {
                'lecture': 0, 'practice': 0, 'independent': 0,
                'exam': 0, 'dictation': 0, 'diff_credit': 0, 'total': 0
            }

            for h in hours:
                count = h['lesson_count'] * 2
                if h['type'] in result:
                    result[h['type']] = count
                result['total'] += count

            # Экзамен
            if exam_count and exam_count['cnt'] > 0:
                if exam_hours_from_db:
                    result['exam'] = exam_hours_from_db['exam_hours']
                    result['total'] += exam_hours_from_db['exam_hours']
                else:
                    result['exam'] = exam_count['cnt'] * 2
                    result['total'] += exam_count['cnt'] * 2

            return result
        except Exception as e:
            conn.close()
            print(f"Ошибка при подсчете часов: {e}")
            return {
                'lecture': 0, 'practice': 0, 'independent': 0,
                'exam': 0, 'dictation': 0, 'diff_credit': 0, 'total': 0
            }