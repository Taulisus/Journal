# blueprints/students.py
# -*- coding: utf-8 -*-
"""
Blueprint для студентов.
URL-префикс: /students (список, CRUD, импорт, массовый перевод)
            /student (карточка студента)
"""

import os
import re
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session,
)

from decorators import login_required, permission_required
from models import (
    Group, Student, GroupSubject, get_db, SemesterGrade,
)
from journal_manager import JournalManager
from utils import import_students_from_xlsx, generate_student_chart
from config import Config
from activity import log_activity
from ._helpers import has_emoji, _make_db_backup


# Два blueprint'а в одном файле: один с префиксом /students,
# другой — без префикса, для /student/<id>.
students_bp = Blueprint('students', __name__, url_prefix='/students')
student_card_bp = Blueprint('student_card', __name__, url_prefix='/student')


# ============================================================
#                 СПИСОК И CRUD
# ============================================================

@students_bp.route('/', strict_slashes=False)
@login_required
def index():
    all_groups = Group.get_all()

    group_id = request.args.get('group_id', type=int)
    if group_id:
        students_list = Student.get_by_group(group_id)
    else:
        students_list = Student.get_all()

    return render_template(
        'students.html',
        students=students_list,
        groups=all_groups,
        current_group_id=group_id,
    )


@students_bp.route('/add', methods=['POST'])
@permission_required('add_students')
def add():
    gid = request.form['group_id']
    name = request.form['full_name'].strip()
    if not name:
        flash('Введите ФИО студента', 'danger')
        return redirect(url_for('students.index'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('students.index'))

    s, m, new_id = Student.create(gid, name)

    if s:
        log_activity(
            session['user_id'], 'add_student',
            f'Добавлен студент «{name}»',
            'student', new_id,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('students.index'))


@students_bp.route('/edit/<int:sid>', methods=['POST'])
@permission_required('add_students')
def edit(sid):
    gid = request.form['group_id']
    name = request.form['full_name'].strip()
    if not name:
        flash('Введите ФИО студента', 'danger')
        return redirect(url_for('students.index'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('students.index'))

    s, m = Student.update(sid, gid, name)
    if s:
        log_activity(
            session['user_id'], 'edit_student',
            f'Изменён студент #{sid} → «{name}»',
            'student', sid,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('students.index'))


@students_bp.route('/delete/<int:sid>')
@permission_required('delete_student')
def delete(sid):
    st = Student.get_by_id(sid)
    st_name = st['full_name'] if st else f'#{sid}'

    s, m = Student.delete(sid)
    if s:
        log_activity(
            session['user_id'], 'delete_student',
            f'Удалён студент «{st_name}»',
            'student', sid,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('students.index'))


# ============================================================
#                 ИМПОРТ
# ============================================================

@students_bp.route('/import', methods=['POST'])
@permission_required('add_students')
def import_students():
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('students.index'))

    file = request.files['file']
    gid = request.form.get('group_id')

    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('students.index'))
    if not gid:
        flash('Выберите группу', 'danger')
        return redirect(url_for('students.index'))

    s, m = import_students_from_xlsx(file, gid)
    if s:
        log_activity(
            session['user_id'], 'import_students',
            f'Импорт студентов: {m}',
            'group', int(gid) if gid else None,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('students.index'))


# ============================================================
#                 МАССОВЫЙ ПЕРЕВОД
# ============================================================

@students_bp.route('/mass-transfer', methods=['POST'])
@permission_required('manage_users')
def mass_transfer():
    uid = session['user_id']

    student_ids = request.form.getlist('student_ids')
    student_ids = [int(s) for s in student_ids if s.isdigit()]

    new_group_id = request.form.get('new_group_id', type=int)
    transfer_date = (request.form.get('transfer_date') or '').strip()

    if not student_ids:
        flash('Не выбрано ни одного студента', 'danger')
        return redirect(url_for('students.index'))

    if not new_group_id:
        flash('Не выбрана группа-приёмник', 'danger')
        return redirect(url_for('students.index'))

    new_group = Group.get_by_id(new_group_id)
    if not new_group:
        flash('Группа-приёмник не найдена', 'danger')
        return redirect(url_for('students.index'))

    if not re.match(r'^\d{4}-\d{2}-\d{2}$', transfer_date):
        transfer_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM academic_years WHERE is_current = 1 LIMIT 1"
        ).fetchone()
        academic_year_id = row['id'] if row else None
    finally:
        conn.close()

    if not academic_year_id:
        flash('Не найден текущий учебный год', 'danger')
        return redirect(url_for('students.index'))

    backup_path = _make_db_backup(prefix='mass_transfer')

    stats = Student.mass_transfer(
        student_ids=student_ids,
        new_group_id=new_group_id,
        transfer_date=transfer_date,
        academic_year_id=academic_year_id,
    )

    log_activity(
        uid, 'mass_transfer',
        f'Массовый перевод: {stats["transferred"]} студ. → «{new_group["name"]}» '
        f'(пропущено: {stats["skipped_same"] + stats["skipped_dup"]}, '
        f'ошибок: {len(stats["errors"])})',
        'group', new_group_id,
    )

    parts = [f'Переведено: {stats["transferred"]}']
    if stats['skipped_same']:
        parts.append(f'уже в группе: {stats["skipped_same"]}')
    if stats['skipped_dup']:
        parts.append(f'дубликатов: {stats["skipped_dup"]}')
    if stats['errors']:
        parts.append(f'ошибок: {len(stats["errors"])}')

    msg = ' • '.join(parts)
    if backup_path:
        msg += f' • бекап: {os.path.basename(backup_path)}'

    category = 'success' if stats['transferred'] > 0 else 'warning'
    flash(msg, category)

    return redirect(url_for('students.index', group_id=new_group_id))


@students_bp.route('/transfer-info/<int:new_group_id>')
@permission_required('manage_users')
def transfer_info(new_group_id):
    """API для предпросмотра массового перевода."""
    ids_param = request.args.get('ids', '')
    student_ids = [int(s) for s in ids_param.split(',') if s.strip().isdigit()]

    new_group = Group.get_by_id(new_group_id)
    if not new_group:
        return jsonify({'success': False, 'message': 'Группа не найдена'})

    if not student_ids:
        return jsonify({
            'success': True,
            'data': {'total': 0, 'same_group': 0, 'duplicates': 0, 'ok': 0},
        })

    conn = get_db()
    try:
        placeholders = ','.join('?' for _ in student_ids)

        rows = conn.execute(f'''
            SELECT id, full_name, group_id FROM students
            WHERE id IN ({placeholders})
        ''', student_ids).fetchall()

        existing_in_new = {
            r['lname'] for r in conn.execute(
                "SELECT LOWER(full_name) AS lname FROM students WHERE group_id = ?",
                (new_group_id,)
            ).fetchall()
        }

        same_group = 0
        duplicates = 0
        ok = 0

        for r in rows:
            if r['group_id'] == new_group_id:
                same_group += 1
            elif r['full_name'].lower() in existing_in_new:
                duplicates += 1
            else:
                ok += 1

        return jsonify({
            'success': True,
            'data': {
                'total': len(rows),
                'same_group': same_group,
                'duplicates': duplicates,
                'ok': ok,
            }
        })
    finally:
        conn.close()


# ============================================================
#                 КАРТОЧКА СТУДЕНТА (отдельный Blueprint без префикса)
# ============================================================

@student_card_bp.route('/<int:sid>')
@permission_required('view_student_card')
def card(sid):
    student = Student.get_by_id(sid)
    if not student:
        flash('Студент не найден', 'danger')
        return redirect(url_for('students.index'))

    group = Group.get_by_id(student['group_id'])

    conn = get_db()
    pairs = conn.execute(
        "SELECT gs.*, s.name as subject_name FROM group_subjects gs "
        "JOIN subjects s ON gs.subject_id=s.id "
        "WHERE gs.group_id=? ORDER BY s.name",
        (student['group_id'],)
    ).fetchall()
    conn.close()

    subjects_stats = []
    total_absences = 0
    total_lessons = 0
    total_attendances = 0
    total_grades = []

    for pair in pairs:
        stats = JournalManager.get_student_stats(pair['id'], sid)
        if stats:
            semesters = GroupSubject.get_semesters(pair['id'])
            semester_grades = {}
            for sem in semesters:
                grade = SemesterGrade.get_student_grade(sid, pair['id'], sem)
                if grade:
                    semester_grades[sem] = grade

            subjects_stats.append({
                'subject_name': pair['subject_name'],
                'gs_id': pair['id'],
                'total_lessons': stats['total_lessons'],
                'absences': stats['absences'],
                'attendances': stats['attendances'],
                'avg_grade': stats['avg_grade'],
                'grades_list': stats['grades_list'],
                'absence_percent': stats['absence_percent'],
                'semester_grades': semester_grades,
            })

            total_absences += stats['absences']
            total_lessons += stats['total_lessons']
            total_attendances += stats['attendances']
            if stats['avg_grade'] > 0:
                total_grades.append(stats['avg_grade'])

    overall = {
        'total_subjects': len(subjects_stats),
        'total_lessons': total_lessons,
        'total_absences': total_absences,
        'total_attendances': total_attendances,
        'overall_absence_percent': round(
            (total_absences / (total_absences + total_attendances) * 100)
            if (total_absences + total_attendances) > 0 else 0,
            1
        ),
        'overall_avg_grade': round(sum(total_grades) / len(total_grades), 2)
        if total_grades else 0,
    }

    cf = f'student_{sid}_chart.png'
    cp = os.path.join(Config.STATIC_FOLDER, 'charts', cf)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    if subjects_stats:
        generate_student_chart(student['full_name'], subjects_stats, cp)

    return render_template(
        'student_card.html',
        student=student,
        group=group,
        subjects_stats=subjects_stats,
        overall_stats=overall,
        chart_filename=f'charts/{cf}' if subjects_stats else None,
    )