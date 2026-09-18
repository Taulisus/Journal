import pandas as pd
import openpyxl
from models import Student
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os


def import_students_from_xlsx(file, group_id):
    """
    Импорт студентов из Excel файла.
    Поддерживает .xlsx и .csv файлы.
    Ищет колонку с ФИО автоматически.
    """
    try:
        filename = file.filename.lower()

        if filename.endswith('.csv'):
            # Импорт из CSV
            df = pd.read_csv(file, encoding='utf-8-sig')
        elif filename.endswith(('.xlsx', '.xls')):
            # Импорт из Excel
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

        # Если не нашли, берем первую колонку
        if name_column is None:
            name_column = df.columns[0]
            print(f"Колонка с ФИО не найдена, использую первую: '{name_column}'")
        else:
            print(f"Найдена колонка с ФИО: '{name_column}'")

        imported_count = 0
        skipped_count = 0

        for _, row in df.iterrows():
            full_name = str(row[name_column]).strip()

            # Пропускаем пустые строки и заголовки
            if not full_name or full_name in ['nan', 'None', '', 'ФИО', 'Имя', 'Name', 'фио', 'имя']:
                continue

            # Проверяем, не существует ли уже такой студент в группе
            students = Student.get_by_group(group_id)
            exists = any(s['full_name'].lower() == full_name.lower() for s in students)

            if not exists:
                Student.create(group_id, full_name)
                imported_count += 1
            else:
                skipped_count += 1

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

        students = Student.get_by_group(group_id)

        for paragraph in doc.paragraphs:
            full_name = paragraph.text.strip()

            if not full_name:
                continue

            # Пропускаем заголовки
            if any(word in full_name.lower() for word in ['фио', 'имя', 'список', 'группа', 'студент']):
                continue

            # Проверяем на дубликаты
            exists = any(s['full_name'].lower() == full_name.lower() for s in students)

            if not exists:
                Student.create(group_id, full_name)
                imported_count += 1
            else:
                skipped_count += 1

        message = f"Импортировано из Word: {imported_count} студентов"
        if skipped_count > 0:
            message += f", пропущено: {skipped_count}"

        return True, message

    except Exception as e:
        return False, f"Ошибка импорта Word: {str(e)}"


def generate_report_chart(names, absences, avg_grades, save_path):
    """Генерирует график успеваемости группы"""
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


def generate_student_chart(student_name, subjects_stats, save_path):
    """Генерирует график успеваемости студента по предметам"""
    # Подготовка данных
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


def export_journal_to_excel(gs_id, pair_info, students, journal_data, save_path):
    """Экспорт журнала в Excel файл"""
    try:
        # Создаем словарь с данными
        data = {}
        data['Студент'] = [s['full_name'] for s in students]

        # Добавляем колонки для каждого занятия
        for i, lesson in enumerate(journal_data):
            col_name = f"{lesson['date']} {lesson['time_interval']}"

            # Колонка с посещаемостью
            attendance_col = f"{col_name} (посещение)"
            data[attendance_col] = []

            # Колонка с оценкой
            grade_col = f"{col_name} (оценка)"
            data[grade_col] = []

            for student in students:
                entry = lesson['entries'].get(student['id'])
                if entry:
                    data[attendance_col].append('+' if entry['attendance'] == 'present' else 'н')
                    data[grade_col].append(entry['grade'] if entry['grade'] else '')
                else:
                    data[attendance_col].append('')
                    data[grade_col].append('')

        # Создаем DataFrame и сохраняем в Excel
        df = pd.DataFrame(data)

        # Создаем writer для форматирования
        with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Журнал', index=False)

            # Получаем workbook и worksheet для форматирования
            workbook = writer.book
            worksheet = writer.sheets['Журнал']

            # Расширяем колонки
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

        return True, f"Журнал экспортирован в {save_path}"

    except Exception as e:
        return False, f"Ошибка экспорта: {str(e)}"


def create_backup(db_path, backup_path):
    """Создает резервную копию базы данных"""
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        return True, f"Резервная копия создана: {backup_path}"
    except Exception as e:
        return False, f"Ошибка создания резервной копии: {str(e)}"


def format_time_interval(time_str):
    """Форматирует время для отображения: 0900-1030 -> 09:00 - 10:30"""
    import re
    match = re.match(r'^(\d{2})(\d{2})-(\d{2})(\d{2})$', time_str)
    if match:
        return f"{match.group(1)}:{match.group(2)} - {match.group(3)}:{match.group(4)}"
    return time_str


def get_grade_color(grade):
    """Возвращает цвет для оценки"""
    if not grade:
        return '#6c757d'  # серый
    if grade == 'passed':
        return '#28a745'  # зеленый
    if grade == '5':
        return '#28a745'  # зеленый
    if grade == '4':
        return '#17a2b8'  # голубой
    if grade == '3':
        return '#ffc107'  # желтый
    if grade == '2':
        return '#dc3545'  # красный
    return '#6c757d'  # серый по умолчанию


def get_attendance_color(attendance):
    """Возвращает цвет для отметки посещения"""
    if attendance == 'present':
        return '#28a745'  # зеленый
    if attendance == 'absent':
        return '#dc3545'  # красный
    return '#6c757d'  # серый