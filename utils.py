import os
import re
import shutil
import sqlite3
from datetime import datetime

import pandas as pd
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from config import Config
from models import Student


# ============================================================
#                 ИМПОРТ СТУДЕНТОВ
# ============================================================

def import_students_from_xlsx(file, group_id):
    """
    Импорт студентов из Excel/CSV файла.
    Ищет колонку с ФИО автоматически.
    """
    try:
        filename = file.filename.lower()

        if filename.endswith('.csv'):
            df = pd.read_csv(file, encoding='utf-8-sig')
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        else:
            return False, "Поддерживаются только .csv и .xlsx файлы"

        if df.empty:
            return False, "Файл пустой"

        # Ищем колонку с ФИО
        name_column = None
        possible_names = ['фио', 'имя', 'name', 'фамилия', 'студент', 'ф.и.о', 'fio', 'фи']

        for col in df.columns:
            col_lower = str(col).lower().strip()
            if any(name in col_lower for name in possible_names):
                name_column = col
                break

        if name_column is None:
            name_column = df.columns[0]
            print(f"Колонка с ФИО не найдена, использую первую: '{name_column}'")
        else:
            print(f"Найдена колонка с ФИО: '{name_column}'")

        # Загружаем существующих студентов ОДИН раз (устраняем N+1)
        existing_students = Student.get_by_group(group_id)
        existing_names = {s['full_name'].lower() for s in existing_students}

        imported_count = 0
        skipped_count = 0

        for _, row in df.iterrows():
            full_name = str(row[name_column]).strip()

            if not full_name or full_name in ['nan', 'None', '', 'ФИО', 'Имя', 'Name', 'фио', 'имя']:
                continue

            if full_name.lower() in existing_names:
                skipped_count += 1
                continue

            Student.create(group_id, full_name)
            existing_names.add(full_name.lower())
            imported_count += 1

        message = f"Импортировано: {imported_count} студентов"
        if skipped_count > 0:
            message += f", пропущено (уже есть): {skipped_count}"

        return True, message

    except Exception as e:
        return False, f"Ошибка импорта: {str(e)}"


def import_students_from_docx(file, group_id):
    """
    Импорт студентов из Word файла.
    Читает текст построчно.
    """
    try:
        from docx import Document

        doc = Document(file)

        imported_count = 0
        skipped_count = 0

        existing_students = Student.get_by_group(group_id)
        existing_names = {s['full_name'].lower() for s in existing_students}

        for paragraph in doc.paragraphs:
            full_name = paragraph.text.strip()

            if not full_name:
                continue

            if any(word in full_name.lower() for word in ['фио', 'имя', 'список', 'группа', 'студент']):
                continue

            if full_name.lower() in existing_names:
                skipped_count += 1
                continue

            Student.create(group_id, full_name)
            existing_names.add(full_name.lower())
            imported_count += 1

        message = f"Импортировано из Word: {imported_count} студентов"
        if skipped_count > 0:
            message += f", пропущено: {skipped_count}"

        return True, message

    except Exception as e:
        return False, f"Ошибка импорта Word: {str(e)}"


# ============================================================
#                 ГРАФИКИ
# ============================================================

def generate_report_chart(names, absences, avg_grades, save_path):
    """Генерирует график успеваемости группы."""
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        x = np.arange(len(names))
        width = 0.6

        # График пропусков
        bars1 = ax1.bar(x, absences, width, color='#e74c3c')
        ax1.set_xlabel('Студенты')
        ax1.set_ylabel('Количество пропусков')
        ax1.set_title('Посещаемость')
        ax1.set_xticks(x)
        ax1.set_xticklabels(names, rotation=45, ha='right')

        for bar, val in zip(bars1, absences):
            if val > 0:
                ax1.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.1,
                         str(val), ha='center', va='bottom')

        # График средних оценок
        bars2 = ax2.bar(x, avg_grades, width, color='#2ecc71')
        ax2.set_xlabel('Студенты')
        ax2.set_ylabel('Средний балл')
        ax2.set_title('Успеваемость')
        ax2.set_xticks(x)
        ax2.set_xticklabels(names, rotation=45, ha='right')
        ax2.set_ylim(0, 5.5)

        for bar, val in zip(bars2, avg_grades):
            if val > 0:
                ax2.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.05,
                         f'{val:.1f}', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(save_path, dpi=100, bbox_inches='tight')
        plt.close()
        print(f"График сохранен: {save_path}")
    except Exception as e:
        print(f"[report_chart] Ошибка: {e}")
        try:
            plt.close('all')
        except Exception:
            pass


def generate_student_chart(student_name, subjects_stats, save_path):
    """Генерирует график успеваемости студента по предметам."""
    try:
        subjects = [s['subject_name'] for s in subjects_stats]
        avg_grades = [s['avg_grade'] for s in subjects_stats]
        absence_percents = [s['absence_percent'] for s in subjects_stats]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle(f'Успеваемость студента: {student_name}', fontsize=14, fontweight='bold')

        x = np.arange(len(subjects))
        width = 0.6

        # График средних оценок
        colors_grades = ['#2ecc71' if g >= 4 else '#f39c12' if g >= 3 else '#e74c3c' for g in avg_grades]
        bars1 = ax1.bar(x, avg_grades, width, color=colors_grades)
        ax1.set_xlabel('Предметы')
        ax1.set_ylabel('Средний балл')
        ax1.set_title('Средний балл по предметам')
        ax1.set_xticks(x)
        ax1.set_xticklabels(subjects, rotation=45, ha='right')
        ax1.set_ylim(0, 5.5)
        ax1.axhline(y=4, color='green', linestyle='--', alpha=0.3, label='Хорошо (4)')
        ax1.axhline(y=3, color='orange', linestyle='--', alpha=0.3, label='Удовл. (3)')
        ax1.legend()

        for bar, val in zip(bars1, avg_grades):
            if val > 0:
                ax1.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.1,
                         f'{val:.1f}', ha='center', va='bottom', fontweight='bold')

        # График процента пропусков
        colors_abs = ['#2ecc71' if p <= 10 else '#f39c12' if p <= 25 else '#e74c3c' for p in absence_percents]
        bars2 = ax2.bar(x, absence_percents, width, color=colors_abs)
        ax2.set_xlabel('Предметы')
        ax2.set_ylabel('Процент пропусков')
        ax2.set_title('Посещаемость по предметам')
        ax2.set_xticks(x)
        ax2.set_xticklabels(subjects, rotation=45, ha='right')
        ax2.set_ylim(0, 100)
        ax2.axhline(y=10, color='green', linestyle='--', alpha=0.3, label='Норма (10%)')
        ax2.axhline(y=25, color='red', linestyle='--', alpha=0.3, label='Критично (25%)')
        ax2.legend()

        for bar, val in zip(bars2, absence_percents):
            if val > 0:
                ax2.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 1,
                         f'{val:.0f}%', ha='center', va='bottom', fontweight='bold')

        plt.tight_layout()
        plt.savefig(save_path, dpi=100, bbox_inches='tight')
        plt.close()
    except Exception as e:
        print(f"[student_chart] Ошибка: {e}")
        try:
            plt.close('all')
        except Exception:
            pass


# ============================================================
#                 ЭКСПОРТ ЖУРНАЛА В EXCEL
# ============================================================

def export_journal_to_excel(gs_id, pair_info, students, journal_data, save_path):
    """
    Экспорт журнала в Excel файл.

    Параметры:
      gs_id        — id журнала (группа-предмет)
      pair_info    — dict с 'group_name' и 'subject_name'
      students     — список студентов (sqlite3.Row или dict)
      journal_data — список занятий из JournalManager.get_journal()
      save_path    — путь для сохранения .xlsx

    Возвращает (True, message) или (False, error).
    """
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = 'Журнал'

        # --- Стили ---
        header_font = Font(bold=True, color='FFFFFF', size=10)
        header_fill = PatternFill('solid', fgColor='4472C4')
        subheader_fill = PatternFill('solid', fgColor='D9E1F2')
        exam_fill = PatternFill('solid', fgColor='FCE4E4')
        center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        left = Alignment(horizontal='left', vertical='center', wrap_text=True)
        thin = Side(border_style='thin', color='999999')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        total_cols = 2 + len(journal_data) * 2

        # --- Заголовок журнала ---
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
        title_cell = ws.cell(row=1, column=1)
        title_cell.value = f"{pair_info['group_name']} — {pair_info['subject_name']}"
        title_cell.font = Font(bold=True, size=14)
        title_cell.alignment = center

        # --- Шапка таблицы ---
        row = 2
        ws.cell(row=row, column=1, value='Студент')
        ws.cell(row=row, column=2, value='За семестр')

        col = 3
        for lesson in journal_data:
            ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)

            cell = ws.cell(row=row, column=col)
            date_str = lesson.get('date_formatted', lesson.get('date', ''))
            time_str = lesson.get('time_interval', '')
            type_name = lesson.get('type', '')
            topic = lesson.get('topic', '') or ''

            cell.value = f"{date_str}\n{time_str}\n{type_name}"
            if topic:
                cell.value += f"\n{topic}"
            cell.font = header_font
            cell.fill = exam_fill if lesson.get('type') == 'exam' else header_fill
            cell.alignment = center
            cell.border = border

            sub_row = row + 1
            c1 = ws.cell(row=sub_row, column=col, value='Посещ.')
            c2 = ws.cell(row=sub_row, column=col + 1, value='Оценка')
            for c in (c1, c2):
                c.fill = subheader_fill
                c.font = Font(bold=True, size=9)
                c.alignment = center
                c.border = border

            col += 2

        # Стили для шапки «Студент» / «За семестр»
        for c in (1, 2):
            cell = ws.cell(row=row, column=c)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            cell.border = border
            # Вторая строка шапки
            cell2 = ws.cell(row=row + 1, column=c)
            cell2.fill = subheader_fill
            cell2.border = border

        # --- Данные ---
        data_start = row + 2
        for i, student in enumerate(students):
            r = data_start + i
            sid = student['id']

            ws.cell(row=r, column=1, value=student['full_name']).alignment = left
            ws.cell(row=r, column=2, value='').alignment = center

            col = 3
            for lesson in journal_data:
                entry = lesson.get('entries', {}).get(sid)
                if entry:
                    attendance = '+' if entry['attendance'] == 'present' else 'н'
                    grade = entry['grade'] or ''
                    if grade == 'passed':
                        grade = 'зач'
                else:
                    attendance = ''
                    grade = ''

                ws.cell(row=r, column=col, value=attendance).alignment = center
                ws.cell(row=r, column=col + 1, value=grade).alignment = center

                if lesson.get('type') == 'exam':
                    ws.cell(row=r, column=col).fill = exam_fill
                    ws.cell(row=r, column=col + 1).fill = exam_fill

                col += 2

            for c in range(1, col):
                ws.cell(row=r, column=c).border = border

        # --- Ширина колонок ---
        ws.column_dimensions['A'].width = 32
        ws.column_dimensions['B'].width = 12
        for c in range(3, 3 + len(journal_data) * 2):
            ws.column_dimensions[get_column_letter(c)].width = 8

        # --- Freeze panes ---
        ws.freeze_panes = ws.cell(row=data_start, column=3)

        # --- Автофильтр ---
        last_row = data_start + len(students) - 1
        if last_row >= data_start:
            ws.auto_filter.ref = f"A{row}:{get_column_letter(total_cols)}{last_row}"

        wb.save(save_path)
        return True, f"Журнал экспортирован в {os.path.basename(save_path)}"

    except Exception as e:
        return False, f"Ошибка экспорта: {str(e)}"


# ============================================================
#                 БЭКАП БД
# ============================================================

def create_backup(db_path=None, backup_dir=None, prefix='manual', max_backups=30):
    """
    Создаёт резервную копию БД.

    Параметры:
      db_path     — путь к БД (по умолчанию Config.DATABASE)
      backup_dir  — папка для бэкапов (по умолчанию <директория БД>/backups)
      prefix      — префикс имени файла
      max_backups — сколько последних бэкапов оставлять (ротация)

    Возвращает (True, path, size_kb) или (False, error, 0).
    """
    try:
        if db_path is None:
            db_path = Config.DATABASE
        if backup_dir is None:
            backup_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'backups')

        if not os.path.exists(db_path):
            return False, f"БД не найдена: {db_path}", 0

        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'journal_{timestamp}_{prefix}.db'
        backup_path = os.path.join(backup_dir, filename)

        shutil.copy2(db_path, backup_path)

        # Проверка: копия не пустая
        size = os.path.getsize(backup_path)
        if size == 0:
            try:
                os.remove(backup_path)
            except OSError:
                pass
            return False, "Копия получилась пустой — операция отменена", 0

        # Проверка: копия открывается как SQLite
        try:
            test_conn = sqlite3.connect(backup_path)
            test_conn.execute("SELECT COUNT(*) FROM sqlite_master")
            test_conn.close()
        except sqlite3.DatabaseError as e:
            try:
                os.remove(backup_path)
            except OSError:
                pass
            return False, f"Копия повреждена: {e}", 0

        # Ротация
        if max_backups > 0:
            _rotate_backups(backup_dir, prefix='journal_', keep=max_backups)

        size_kb = size / 1024
        return True, backup_path, size_kb

    except Exception as e:
        return False, f"Ошибка создания бэкапа: {str(e)}", 0


def _rotate_backups(backup_dir, prefix='journal_', keep=30):
    """Удаляет старые бэкапы, оставляя последние `keep` штук."""
    try:
        files = [
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.startswith(prefix) and f.endswith('.db')
        ]
        if len(files) <= keep:
            return

        files.sort(key=os.path.getmtime)
        for old in files[:-keep]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception:
        pass


# ============================================================
#                 ФОРМАТИРОВАНИЕ
# ============================================================

def format_time_interval(time_str):
    """
    Форматирует время для отображения.

    Примеры:
      '0900-1030'   → '09:00 – 10:30'
      '9:00-10:30'  → '09:00 – 10:30'
      '0900'        → '09:00'
      ''            → ''
    """
    if not time_str:
        return ''

    s = str(time_str).strip()

    # Уже с двоеточиями — нормализуем тире
    if ':' in s:
        s = re.sub(r'\s*[-–—]\s*', ' – ', s)
        return s

    # '0900-1030'
    m = re.match(r'^(\d{3,4})\s*[-–—]\s*(\d{3,4})$', s)
    if m:
        t1 = _fmt_hhmm(m.group(1))
        t2 = _fmt_hhmm(m.group(2))
        if t1 and t2:
            return f"{t1} – {t2}"

    # Одиночное '0900'
    m = re.match(r'^(\d{3,4})$', s)
    if m:
        t = _fmt_hhmm(m.group(1))
        if t:
            return t

    return s


def _fmt_hhmm(raw):
    """'900' → '09:00', '0900' → '09:00', '1030' → '10:30'."""
    raw = raw.strip()
    if len(raw) == 3:
        raw = '0' + raw
    if len(raw) != 4 or not raw.isdigit():
        return None
    hh, mm = raw[:2], raw[2:]
    if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        return None
    return f"{hh}:{mm}"


# ============================================================
#                 ЦВЕТА ОЦЕНОК И ПОСЕЩЕНИЙ
# ============================================================

def get_grade_color(grade, mode='class'):
    """
    Возвращает цвет для оценки.

    mode='class' → Bootstrap-классы ('success', 'info', ...)
    mode='hex'   → hex-цвета
    """
    mapping = {
        '5':      ('success',   '#28a745'),
        'passed': ('success',   '#28a745'),
        '4':      ('info',      '#17a2b8'),
        '3':      ('warning',   '#ffc107'),
        '2':      ('danger',    '#dc3545'),
        None:     ('secondary', '#6c757d'),
        '':       ('secondary', '#6c757d'),
    }

    cls, hex_color = mapping.get(grade, ('secondary', '#6c757d'))
    return cls if mode == 'class' else hex_color


def get_attendance_color(attendance, mode='class'):
    """
    Возвращает цвет для отметки посещения.

    mode='class' → Bootstrap-классы
    mode='hex'   → hex-цвета
    """
    mapping = {
        'present': ('success',  '#28a745'),
        'absent':  ('danger',   '#dc3545'),
        None:      ('secondary', '#6c757d'),
        '':        ('secondary', '#6c757d'),
    }

    cls, hex_color = mapping.get(attendance, ('secondary', '#6c757d'))
    return cls if mode == 'class' else hex_color