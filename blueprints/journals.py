# blueprints/journals.py
# -*- coding: utf-8 -*-
"""
Blueprint для журналов (пары Группа-Предмет, занятия, оценки, экспорт).
URL-префиксы: /group-subjects, /journal
"""

import os
import re
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session, send_file,
)
from werkzeug.utils import secure_filename

from decorators import login_required, permission_required
from models import (
    Group, Subject, Student, GroupSubject, get_db,
    Permission, TeacherJournal, SemesterGrade,
)
from journal_manager import JournalManager
from utils import export_journal_to_excel
from config import Config
from activity import log_activity
from ._helpers import (
    has_emoji,
    _make_db_backup,
    _user_owns_journal,
    _require_journal_access,
    _require_journal_access_json,
)


journals_bp = Blueprint('journals', __name__)


# ============================================================
#                 ПАРЫ ГРУППА-ПРЕДМЕТ
# ============================================================

@journals_bp.route('/group-subjects')
@login_required
def index():
    uid = session['user_id']
    if Permission.has_permission(uid, 'manage_users'):
        pairs = GroupSubject.get_all()
    else:
        pairs = TeacherJournal.get_user_journals(uid)
    return render_template(
        'group_subjects.html',
        pairs=pairs,
        groups=Group.get_all(),
        subjects=Subject.get_all(),
    )


@journals_bp.route('/group-subjects/add', methods=['POST'])
@permission_required('add_journal')
def add_group_subject():
    gid = request.form['group_id']
    sid = request.form['subject_id']

    semesters_data = []
    for sem_num in [1, 2, 3]:
        lecture = int(request.form.get(f'semester_{sem_num}_lecture', 0) or 0)
        practice = int(request.form.get(f'semester_{sem_num}_practice', 0) or 0)
        independent = int(request.form.get(f'semester_{sem_num}_independent', 0) or 0)
        exam = int(request.form.get(f'semester_{sem_num}_exam', 0) or 0)

        if lecture > 0 or practice > 0 or independent > 0 or exam > 0:
            semesters_data.append({
                'semester': sem_num,
                'lecture': lecture,
                'practice': practice,
                'independent': independent,
                'exam': exam,
            })

    if not semesters_data:
        semesters_data = [{
            'semester': 1, 'lecture': 0, 'practice': 0,
            'independent': 0, 'exam': 0,
        }]

    s, m, new_id = GroupSubject.create(gid, sid, semesters_data)

    if s:
        grp = Group.get_by_id(gid)
        subj = Subject.get_by_id(sid)
        gname = grp['name'] if grp else f'#{gid}'
        sname = subj['name'] if subj else f'#{sid}'
        log_activity(
            session['user_id'], 'add_journal',
            f'Создан журнал «{gname}» / «{sname}»',
            'journal', new_id,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('journals.index'))


@journals_bp.route('/group-subjects/delete/<int:gsid>')
@permission_required('add_journal')
def delete_group_subject(gsid):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    pair = GroupSubject.get_by_id(gsid)
    pair_name = f'{pair["group_name"]} / {pair["subject_name"]}' if pair else f'#{gsid}'

    backup_path = _make_db_backup(prefix=f'del_journal_{gsid}')

    s, m = GroupSubject.delete(gsid)

    if s:
        log_activity(uid, 'delete_journal',
                     f'Удалён журнал «{pair_name}»', 'journal', gsid)
        if backup_path:
            flash(f'{m}. Бекап: {os.path.basename(backup_path)}', 'success')
        else:
            flash(f'{m} (бэкап не создан — проверьте права на backups/)', 'warning')
    else:
        flash(m, 'danger')

    return redirect(url_for('journals.index'))


@journals_bp.route('/group-subjects/get-hours/<int:gsid>')
@login_required
def get_group_subject_hours(gsid):
    semesters = GroupSubject.get_semesters(gsid)
    hours = {}
    for sem in semesters:
        h = GroupSubject.get_hours(gsid, sem)
        hours[sem] = {
            'lecture_hours': h.get('lecture_hours', 0),
            'practice_hours': h.get('practice_hours', 0),
            'independent_hours': h.get('independent_hours', 0),
            'exam_hours': h.get('exam_hours', 0),
        }
    return jsonify({'semesters': semesters, 'hours': hours})


@journals_bp.route('/group-subjects/edit-hours', methods=['POST'])
@permission_required('add_journal')
def edit_group_subject_hours():
    uid = session['user_id']
    gsid = request.form['gsid']

    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Журнал не найден', 'danger')
        return redirect(url_for('journals.index'))
    if not _user_owns_journal(uid, int(gsid)):
        flash('Журнал вам не назначен', 'danger')
        return redirect(url_for('journals.index'))

    semesters = GroupSubject.get_semesters(gsid)

    conn = get_db()
    try:
        for sem in semesters:
            lecture = int(request.form.get(f'hours_{sem}_lecture', 0) or 0)
            practice = int(request.form.get(f'hours_{sem}_practice', 0) or 0)
            independent = int(request.form.get(f'hours_{sem}_independent', 0) or 0)
            exam = int(request.form.get(f'hours_{sem}_exam', 0) or 0)

            conn.execute('''
                UPDATE group_subject_hours 
                SET lecture_hours=?, practice_hours=?, independent_hours=?, exam_hours=?
                WHERE group_subject_id=? AND semester=?
            ''', (lecture, practice, independent, exam, gsid, sem))

        conn.commit()
        log_activity(uid, 'edit_hours',
                     f'Изменены часы журнала #{gsid}', 'journal', int(gsid))
        flash('Часы обновлены', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('journals.index'))


# ============================================================
#                 ЖУРНАЛ
# ============================================================

@journals_bp.route('/journal/<int:gsid>')
@permission_required('view_journals')
def journal(gsid):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Пара не найдена', 'danger')
        return redirect(url_for('journals.index'))

    semesters = GroupSubject.get_semesters(gsid)
    if not semesters:
        flash('Нет настроенных семестров', 'danger')
        return redirect(url_for('journals.index'))

    current_semester = request.args.get('semester', semesters[0], type=int)
    if current_semester not in semesters:
        current_semester = semesters[0]

    students = Student.get_by_group(pair['group_id'])
    journal_data = JournalManager.get_journal(gsid, current_semester)

    semester_grades_list = SemesterGrade.get_grades(gsid, current_semester)
    semester_grades = {}
    for g in semester_grades_list:
        semester_grades[g['student_id']] = g['grade']

    return render_template(
        'journal.html',
        pair=pair,
        students=students,
        journal_data=journal_data,
        lesson_types=Config.LESSON_TYPES,
        grades=Config.GRADES,
        semesters=semesters,
        current_semester=current_semester,
        semester_grades=semester_grades,
    )


@journals_bp.route('/journal/<int:gsid>/add-lesson', methods=['GET', 'POST'])
@permission_required('view_journals')
def add_lesson(gsid):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Пара не найдена', 'danger')
        return redirect(url_for('journals.index'))

    students = Student.get_by_group(pair['group_id'])
    semesters = GroupSubject.get_semesters(gsid)
    current_semester = request.args.get('semester', semesters[0] if semesters else 1, type=int)

    if request.method == 'POST':
        date = request.form['date']
        ti = request.form.get('time_interval', '').strip()
        topic = request.form.get('topic', '').strip()
        ltype = request.form['type']
        semester = int(request.form.get('semester', 1))

        if not ti:
            flash('Введите время занятия', 'danger')
            return redirect(url_for('journals.add_lesson', gsid=gsid, semester=semester))
        if not re.match(r'^\d{4}-\d{4}$', ti):
            flash('Формат: 0900-1030', 'danger')
            return redirect(url_for('journals.add_lesson', gsid=gsid, semester=semester))
        if len(topic) > 50:
            flash('Тема не может быть длиннее 50 символов', 'danger')
            return redirect(url_for('journals.add_lesson', gsid=gsid, semester=semester))
        if has_emoji(topic):
            flash('Эмодзи запрещены в теме', 'danger')
            return redirect(url_for('journals.add_lesson', gsid=gsid, semester=semester))

        students_data = {}
        for st in students:
            sid = str(st['id'])
            students_data[st['id']] = {
                'attendance': request.form.get(f'attendance_{sid}', 'present'),
                'grade': request.form.get(f'grade_{sid}') or None,
            }

        s, m = JournalManager.add_lesson(gsid, date, ti, topic, ltype, semester, students_data)
        if s:
            log_activity(
                uid, 'add_lesson',
                f'Добавлено занятие: {pair["group_name"]} / {pair["subject_name"]} '
                f'({date}, {ti})',
                'journal', gsid,
            )
        flash(m, 'success' if s else 'danger')
        return redirect(url_for('journals.journal', gsid=gsid, semester=semester))

    return render_template(
        'add_lesson.html',
        pair=pair,
        students=students,
        lesson_types=Config.LESSON_TYPES,
        grades=Config.GRADES,
        semesters=semesters,
        current_semester=current_semester,
    )


@journals_bp.route('/journal/<int:gsid>/update-entry', methods=['POST'])
@permission_required('view_journals')
def update_entry(gsid):
    uid = session['user_id']

    resp = _require_journal_access_json(uid, gsid)
    if resp:
        return resp

    entry_id_raw = request.form.get('entry_id')
    if not entry_id_raw or not str(entry_id_raw).isdigit():
        return jsonify({'success': False, 'message': 'Некорректный entry_id'}), 400

    entry_id = int(entry_id_raw)

    entry = JournalManager.get_entry(gsid, entry_id)
    if not entry:
        return jsonify({'success': False, 'message': 'Запись не найдена в этом журнале'}), 404

    attendance = request.form.get('attendance', 'present')
    if attendance not in ('present', 'absent'):
        return jsonify({'success': False, 'message': 'Некорректное посещение'}), 400

    grade = request.form.get('grade') or None
    if grade not in (None, '', '2', '3', '4', '5', 'passed'):
        return jsonify({'success': False, 'message': 'Некорректная оценка'}), 400

    s, m = JournalManager.update_entry(gsid, entry_id, attendance, grade)

    if s:
        log_activity(
            uid, 'edit_entry',
            f'Изменена запись #{entry_id} (журнал #{gsid}): '
            f'{attendance}, оценка {grade or "—"}',
            'journal', gsid,
        )

    return jsonify({'success': s, 'message': m})


@journals_bp.route('/journal/update-lesson-type', methods=['POST'])
@permission_required('view_journals')
def update_lesson_type():
    uid = session['user_id']

    gsid_raw = request.form.get('gsid')
    if not gsid_raw or not str(gsid_raw).isdigit():
        return jsonify({'success': False, 'message': 'Некорректный gsid'}), 400
    gsid = int(gsid_raw)

    resp = _require_journal_access_json(uid, gsid)
    if resp:
        return resp

    date = request.form['date']
    time_interval = request.form['time_interval']
    semester = request.form['semester']
    new_type = request.form['type']

    conn = get_db()
    table_name = JournalManager.get_table_name(gsid)

    try:
        if new_type == 'exam':
            exam_exists = conn.execute(
                f"SELECT COUNT(*) as c FROM {table_name} "
                f"WHERE semester=? AND type='exam' "
                f"AND NOT (date=? AND time_interval=?)",
                (semester, date, time_interval),
            ).fetchone()
            if exam_exists['c'] > 0:
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'Экзамен в этом семестре уже существует!',
                })

        conn.execute(f'''
            UPDATE {table_name} 
            SET type = ?
            WHERE date = ? AND time_interval = ? AND semester = ?
        ''', (new_type, date, time_interval, semester))

        conn.commit()
        conn.close()

        log_activity(
            uid, 'edit_lesson_type',
            f'Изменён тип занятия: журнал #{gsid}, {date} {time_interval} → {new_type}',
            'journal', gsid,
        )

        return jsonify({'success': True, 'message': 'Тип занятия обновлен'})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'})


@journals_bp.route('/journal/<int:gsid>/delete-lesson/<date>/<ti>')
@permission_required('view_journals')
def delete_lesson(gsid, date, ti):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    semester = request.args.get('semester', 1, type=int)
    s, m = JournalManager.delete_lesson(gsid, date, ti)
    if s:
        log_activity(uid, 'delete_lesson',
                     f'Удалено занятие: журнал #{gsid}, {date} {ti}',
                     'journal', gsid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('journals.journal', gsid=gsid, semester=semester))


# ============================================================
#                 ИЗМЕНЕНИЕ ВРЕМЕНИ ЗАНЯТИЯ
# ============================================================

@journals_bp.route('/journal/<int:gsid>/update-lesson-time', methods=['POST'])
@permission_required('view_journals')
def update_lesson_time(gsid):
    uid = session['user_id']

    resp = _require_journal_access_json(uid, gsid)
    if resp:
        return resp

    date = request.form.get('date', '').strip()
    old_time = request.form.get('old_time', '').strip()
    new_time = request.form.get('new_time', '').strip()
    semester = request.form.get('semester', type=int)

    if not date or not old_time or not new_time:
        return jsonify({'success': False, 'message': 'Не указаны обязательные поля'}), 400

    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        return jsonify({'success': False, 'message': 'Некорректная дата'}), 400

    if not re.match(r'^\d{4}-\d{4}$', new_time):
        return jsonify({'success': False, 'message': 'Формат времени: 0900-1030'}), 400

    if old_time == new_time:
        return jsonify({'success': False, 'message': 'Новое время совпадает со старым'}), 400

    conn = get_db()
    table_name = JournalManager.get_table_name(gsid)
    try:
        conflict = conn.execute(
            f"SELECT COUNT(*) as c FROM {table_name} "
            f"WHERE date = ? AND time_interval = ? AND semester = ?",
            (date, new_time, semester),
        ).fetchone()
        if conflict['c'] > 0:
            return jsonify({
                'success': False,
                'message': 'Занятие с таким временем уже существует в этот день',
            }), 409

        cur = conn.execute(
            f"UPDATE {table_name} SET time_interval = ? "
            f"WHERE date = ? AND time_interval = ? AND semester = ?",
            (new_time, date, old_time, semester),
        )
        affected = cur.rowcount
        conn.commit()

        log_activity(
            uid, 'edit_lesson_time',
            f'Изменено время занятия: журнал #{gsid}, '
            f'{date} {old_time} → {new_time} ({affected} записей)',
            'journal', gsid,
        )

        return jsonify({
            'success': True,
            'affected': affected,
            'message': f'Время обновлено ({affected} записей)',
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Ошибка: {e}'}), 500
    finally:
        conn.close()


# ============================================================
#                 ЭКСПОРТ ЖУРНАЛА В EXCEL
# ============================================================

@journals_bp.route('/journal/<int:gsid>/export')
@permission_required('create_report')
def export_journal(gsid):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Пара не найдена', 'danger')
        return redirect(url_for('journals.index'))

    semester = request.args.get('semester', None, type=int)
    journal_data = JournalManager.get_journal(gsid, semester)
    students = Student.get_by_group(pair['group_id'])

    if not journal_data:
        flash('Нет данных для экспорта', 'warning')
        return redirect(url_for('journals.journal', gsid=gsid, semester=semester or 1))

    filename = f"journal_{gsid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    tmp_dir = os.path.join(Config.UPLOAD_FOLDER, 'exports')
    os.makedirs(tmp_dir, exist_ok=True)
    save_path = os.path.join(tmp_dir, secure_filename(filename))

    ok, msg = export_journal_to_excel(
        gs_id=gsid,
        pair_info={
            'group_name': pair['group_name'],
            'subject_name': pair['subject_name'],
        },
        students=students,
        journal_data=journal_data,
        save_path=save_path,
    )

    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('journals.journal', gsid=gsid, semester=semester or 1))

    log_activity(
        uid, 'export_journal',
        f'Экспорт журнала «{pair["group_name"]} / {pair["subject_name"]}» в Excel',
        'journal', gsid,
    )

    return send_file(
        save_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


# ============================================================
#                 ОЦЕНКА ЗА СЕМЕСТР
# ============================================================

@journals_bp.route('/journal/<int:gsid>/set-semester-grade', methods=['POST'])
@permission_required('set_semester_grade')
def set_semester_grade(gsid):
    uid = session['user_id']

    resp = _require_journal_access_json(uid, gsid)
    if resp:
        return resp

    student_id = request.form['student_id']
    semester = int(request.form['semester'])
    grade = request.form.get('grade', None)

    SemesterGrade.set_grade(student_id, gsid, semester, grade)

    log_activity(
        uid, 'set_semester_grade',
        f'Выставлена оценка за семестр: журнал #{gsid}, студент #{student_id}, '
        f'семестр {semester}, оценка {grade or "—"}',
        'journal', gsid,
    )

    return jsonify({'success': True})