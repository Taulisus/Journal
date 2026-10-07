# blueprints/journals.py
# -*- coding: utf-8 -*-
"""
Blueprint для журналов (пары Группа-Предмет, занятия, оценки, экспорт).
URL-префиксы: /group-subjects, /journal
"""

import os
import re
from datetime import datetime
from models_schedule import Teacher

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session, send_file,
)
from werkzeug.utils import secure_filename

from decorators import login_required, permission_required
from models import (
    Group, Subject, Student, GroupSubject, get_db,
    Permission, TeacherJournal, SemesterGrade,
    JournalPlan,
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
    from models_schedule import Teacher   # импорт сверху файла лучше

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
        all_teachers=Teacher.get_all(active_only=False),   # ← новое
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

@journals_bp.route('/group-subjects/<int:gsid>/copy-to-groups', methods=['POST'])
@permission_required('add_journal')
def copy_journal_to_groups(gsid):
    """
    Копирует базовый набор журнала (предмет + часы) в выбранные группы.

    POST-параметры:
      group_ids[]        — список id групп (обязательно)
      teacher_id         — id преподавателя из справочника teachers (опционально)
      copy_hours         — '1'/'0', копировать ли часы (по умолчанию '1')
    """
    uid = session['user_id']

    # Проверка доступа к исходному журналу
    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    source = GroupSubject.get_by_id(gsid)
    if not source:
        flash('Исходный журнал не найден', 'danger')
        return redirect(url_for('journals.index'))

    group_ids = request.form.getlist('group_ids')
    group_ids = [int(g) for g in group_ids if g.isdigit()]

    teacher_id = request.form.get('teacher_id', type=int) or None
    copy_hours = request.form.get('copy_hours', '1') == '1'

    if not group_ids:
        flash('Не выбрано ни одной группы', 'warning')
        return redirect(url_for('journals.index'))

    subject_id = source['subject_id']
    subject_name = source['subject_name']

    # Часы исходного журнала (по семестрам)
    source_semesters = GroupSubject.get_semesters(gsid)
    source_hours = {}
    if copy_hours:
        for sem in source_semesters:
            h = GroupSubject.get_hours(gsid, sem)
            source_hours[sem] = {
                'lecture': h.get('lecture_hours', 0),
                'practice': h.get('practice_hours', 0),
                'independent': h.get('independent_hours', 0),
                'exam': h.get('exam_hours', 0),
            }

    # Найти пользователя-преподавателя, если teacher_id задан
    teacher_user_id = None
    if teacher_id:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT id FROM users WHERE teacher_id = ? LIMIT 1",
                (teacher_id,)
            ).fetchone()
            if row:
                teacher_user_id = row['id']
        finally:
            conn.close()

    created = 0
    skipped = []
    errors = []

    for gid in group_ids:
        grp = Group.get_by_id(gid)
        if not grp:
            errors.append(f'Группа #{gid} не найдена')
            continue

        # Проверка: у группы уже есть журнал по этому предмету?
        conn = get_db()
        try:
            existing = conn.execute(
                "SELECT id FROM group_subjects WHERE group_id = ? AND subject_id = ?",
                (gid, subject_id)
            ).fetchone()
        finally:
            conn.close()

        if existing:
            skipped.append(f'{grp["name"]}: журнал по «{subject_name}» уже есть (сначала удалите его)')
            continue

        # Формируем данные семестров для нового журнала
        semesters_data = None
        if source_hours:
            semesters_data = []
            for sem, h in source_hours.items():
                semesters_data.append({
                    'semester': sem,
                    'lecture': h['lecture'],
                    'practice': h['practice'],
                    'independent': h['independent'],
                    'exam': h['exam'],
                })

        # Создаём журнал
        ok, msg, new_gsid = GroupSubject.create(gid, subject_id, semesters_data)
        if not ok:
            errors.append(f'{grp["name"]}: {msg}')
            continue

        # Назначаем преподавателя
        if teacher_user_id:
            try:
                TeacherJournal.assign(teacher_user_id, new_gsid)
            except Exception as e:
                errors.append(f'{grp["name"]}: не удалось назначить преподавателя — {e}')

        created += 1

    log_activity(
        uid, 'copy_journal',
        f'Копирование журнала «{source["group_name"]} / {subject_name}» '
        f'в {created} групп(ы); пропущено: {len(skipped)}; ошибок: {len(errors)}',
        'journal', gsid,
    )

    # Формируем сообщение
    parts = [f'Создано журналов: {created}']
    if skipped:
        parts.append(f'пропущено: {len(skipped)}')
    if errors:
        parts.append(f'ошибок: {len(errors)}')
    flash(' • '.join(parts), 'success' if created > 0 else 'warning')

    for s in skipped:
        flash(s, 'warning')
    for e in errors[:5]:
        flash(e, 'danger')

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

    # Все неиспользованные пункты плана (без фильтра по типу)
    plan_unused = JournalPlan.get_unused_for_journal(gsid)

    if request.method == 'POST':
        date = request.form['date']
        ti = request.form.get('time_interval', '').strip()
        topic = request.form.get('topic', '').strip()
        ltype = request.form['type']
        semester = int(request.form.get('semester', 1))
        plan_id = request.form.get('plan_id', type=int)

        if not ti:
            flash('Введите время занятия', 'danger')
            return redirect(url_for('journals.add_lesson', gsid=gsid, semester=semester))
        if not re.match(r'^\d{4}-\d{4}$', ti):
            flash('Формат: 0900-1030', 'danger')
            return redirect(url_for('journals.add_lesson', gsid=gsid, semester=semester))
        if not topic:
            flash('Введите тему занятия', 'danger')
            return redirect(url_for('journals.add_lesson', gsid=gsid, semester=semester))
        if len(topic) > 200:
            flash('Тема слишком длинная (макс. 200 символов)', 'danger')
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
            # Если был выбран пункт из плана — отметим его использованным
            if plan_id:
                # Найдём id первой созданной записи в журнале
                conn = get_db()
                try:
                    table_name = JournalManager.get_table_name(gsid)
                    row = conn.execute(
                        f"SELECT id FROM {table_name} "
                        f"WHERE date = ? AND time_interval = ? LIMIT 1",
                        (date, ti)
                    ).fetchone()
                    if row:
                        JournalPlan.mark_used(plan_id, row['id'])
                finally:
                    conn.close()

            log_activity(uid, 'add_lesson',
                         f'Добавлено занятие: {pair["group_name"]} / {pair["subject_name"]} '
                         f'({date}, {ti}, тема «{topic}»)',
                         'journal', gsid)
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
        plan_unused=plan_unused,
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


@journals_bp.route('/journal/<int:gsid>/update-grades-batch', methods=['POST'])
@permission_required('view_journals')
def update_grades_batch(gsid):
    """
    Массовое обновление оценок в журнале.

    Ожидает JSON:
    {
        "updates": [
            {"entry_id": 1, "attendance": "present", "grade": "5"},
            {"entry_id": 2, "attendance": "absent", "grade": null}
        ]
    }
    """
    uid = session['user_id']

    resp = _require_journal_access_json(uid, gsid)
    if resp:
        return resp

    data = request.get_json(silent=True) or {}
    updates = data.get('updates') or []

    if not isinstance(updates, list):
        return jsonify({'success': False, 'message': 'Некорректный формат'}), 400

    # Проверяем, что все entry_id принадлежат этому журналу
    for item in updates:
        entry_id = item.get('entry_id')
        if not entry_id:
            continue
        entry = JournalManager.get_entry(gsid, entry_id)
        if not entry:
            return jsonify({
                'success': False,
                'message': f'Запись #{entry_id} не найдена в этом журнале'
            }), 404

    ok, msg, count = JournalManager.update_grades_batch(gsid, updates)

    if ok:
        log_activity(
            uid, 'edit_entry',
            f'Массовая оценка: журнал #{gsid}, обновлено {count} записей',
            'journal', gsid,
        )

    return jsonify({
        'success': ok,
        'message': msg,
        'updated': count,
    })


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

# ============================================================
#                 ТЕМАТИЧЕСКИЙ ПЛАН (КТП)
# ============================================================

@journals_bp.route('/group-subjects/<int:gsid>/plan')
@permission_required('view_journals')
def plan_view(gsid):
    """Страница тематического плана журнала."""
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Журнал не найден', 'danger')
        return redirect(url_for('journals.index'))

    plan = JournalPlan.get_for_journal(gsid)

    # Для селектов
    lesson_types = Config.LESSON_TYPES

    # Сколько пунктов уже использовано
    used_count = sum(1 for p in plan if p.get('used_lesson_id'))

    return render_template(
        'journal_plan.html',
        pair=pair,
        plan=plan,
        lesson_types=lesson_types,
        used_count=used_count,
    )


@journals_bp.route('/group-subjects/<int:gsid>/plan/add', methods=['POST'])
@permission_required('add_journal')
def plan_add(gsid):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    order_number = request.form.get('order_number', type=int)
    topic = (request.form.get('topic') or '').strip()
    hours = request.form.get('hours', 2, type=int) or 2
    lesson_type = request.form.get('lesson_type', 'lecture')

    if not topic:
        flash('Введите название темы', 'danger')
        return redirect(url_for('journals.plan_view', gsid=gsid))

    ok, msg, new_id = JournalPlan.create(gsid, order_number, topic, hours, lesson_type)
    flash(msg, 'success' if ok else 'danger')

    return redirect(url_for('journals.plan_view', gsid=gsid))


@journals_bp.route('/group-subjects/<int:gsid>/plan/<int:plan_id>/edit', methods=['POST'])
@permission_required('add_journal')
def plan_edit(gsid, plan_id):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    order_number = request.form.get('order_number', type=int)
    topic = (request.form.get('topic') or '').strip()
    hours = request.form.get('hours', 2, type=int) or 2
    lesson_type = request.form.get('lesson_type', 'lecture')

    if not topic:
        flash('Введите название темы', 'danger')
        return redirect(url_for('journals.plan_view', gsid=gsid))

    ok, msg = JournalPlan.update(plan_id, order_number, topic, hours, lesson_type)
    flash(msg, 'success' if ok else 'danger')

    return redirect(url_for('journals.plan_view', gsid=gsid))


@journals_bp.route('/group-subjects/<int:gsid>/plan/<int:plan_id>/delete', methods=['POST'])
@permission_required('add_journal')
def plan_delete(gsid, plan_id):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    ok, msg = JournalPlan.delete(plan_id)
    flash(msg, 'success' if ok else 'danger')

    return redirect(url_for('journals.plan_view', gsid=gsid))


@journals_bp.route('/group-subjects/<int:gsid>/plan/clear', methods=['POST'])
@permission_required('add_journal')
def plan_clear(gsid):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    ok, msg, count = JournalPlan.delete_all_for_journal(gsid)
    if ok:
        log_activity(uid, 'plan_clear',
                     f'Очищен план журнала #{gsid} ({count} пунктов)',
                     'journal', gsid)
    flash(msg, 'success' if ok else 'danger')

    return redirect(url_for('journals.plan_view', gsid=gsid))


# ============================================================
#                 ИМПОРТ ПЛАНА ИЗ WORD / EXCEL
# ============================================================

def _parse_plan_tsv(text):
    """
    Разбирает TSV-текст (Word/Excel → Ctrl+C → вставка в textarea).

    Формат: строки, разделённые \\n, колонки — \\t.
    Шапка может быть многострочной (merged cells в Word).
    Ищем заголовки накопительно по первым ~15 строкам.

    Возвращает список dict-ов.
    """
    if not text:
        return []

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    raw_lines = text.split('\n')
    lines = []
    for line in raw_lines:
        cols = line.split('\t')
        if not any(c.strip() for c in cols):
            continue
        lines.append(cols)

    if not lines:
        return []

    # ============================================================
    #  1. Определяем индексы колонок
    # ============================================================
    # Пройдём по первым 15 строкам. Каждое «правильное» значение
    # заголовка ищем в отдельной ячейке. Найденное запоминаем.
    # Это нужно, потому что в merged-шапке Word заголовки в
    # разных строках и разных колонках.

    header_map = {}
    header_row_idx = None

    def _norm(s):
        """Нормализует текст: lower, убирает дефисы, лишние пробелы."""
        s = str(s).strip().lower()
        s = s.replace('-', '').replace('–', '').replace('—', '')
        s = ' '.join(s.split())
        return s

    # Шапка может быть до 15 строк
    for i in range(min(15, len(lines))):
        cols = lines[i]
        found_here = 0

        for j, cell in enumerate(cols):
            cell_norm = _norm(cell)
            if not cell_norm:
                continue

            # № п/п
            if 'order_number' not in header_map:
                if cell_norm in ('№', '№ п/п', 'п/п', 'n', '№п/п'):
                    header_map['order_number'] = j
                    found_here += 1

            # Тема / наименование
            if 'topic' not in header_map:
                if 'наименование' in cell_norm and ('тем' in cell_norm or 'раздел' in cell_norm):
                    header_map['topic'] = j
                    found_here += 1

            # Часы
            if 'hours' not in header_map:
                if 'количество' in cell_norm and 'час' in cell_norm:
                    header_map['hours'] = j
                    found_here += 1
                # Если слово "часов" отдельно — тоже подходит
                elif cell_norm == 'часов' or cell_norm.startswith('часов'):
                    header_map.setdefault('hours', j)
                    found_here += 1

            # Вид занятия
            if 'lesson_type' not in header_map:
                if 'вид' in cell_norm and 'занят' in cell_norm:
                    header_map['lesson_type'] = j
                    found_here += 1

        # Если на этой строке нашли хотя бы что-то новое — запоминаем
        # её как «начало» шапки (для определения data_start).
        if found_here > 0:
            if header_row_idx is None:
                header_row_idx = i
            # Продолжаем сканировать дальше, чтобы накопить все колонки

        # Если нашли все 4 — выходим
        if all(k in header_map for k in ('order_number', 'topic', 'hours', 'lesson_type')):
            break

    # Если хоть одну колонку не нашли — используем fallback по самой
    # длинной строке таблицы (обычно это строка данных).
    if 'topic' not in header_map or 'lesson_type' not in header_map:
        # Ищем «эталонную» строку данных — где 4+ колонки, и они «наполнены».
        for i, cols in enumerate(lines):
            if len(cols) < 4:
                continue
            # Первая колонка — число, вторая — длинный текст,
            # третья — число, четвёртая — текст с «урок»/«занятие»/«подготовка»
            if not cols[0].strip():
                continue

            c0 = cols[0].strip().lstrip('+-').rstrip('.').strip()
            if not c0.isdigit():
                continue

            topic_text = cols[1].strip() if len(cols) > 1 else ''
            if len(topic_text) < 10:
                continue

            hours_text = cols[2].strip() if len(cols) > 2 else ''
            if not hours_text.isdigit():
                continue

            type_text = cols[3].strip().lower() if len(cols) > 3 else ''
            if any(w in type_text for w in ['урок', 'занятие', 'подготовк', 'работа']):
                header_map.setdefault('order_number', 0)
                header_map.setdefault('topic', 1)
                header_map.setdefault('hours', 2)
                header_map.setdefault('lesson_type', 3)
                header_row_idx = i - 1 if i > 0 else -1
                break

    # Если совсем не разобрались — стандартные 0/1/2/3
    for k, v in (('order_number', 0), ('topic', 1), ('hours', 2), ('lesson_type', 3)):
        header_map.setdefault(k, v)

    # data_start — следующая строка после шапки
    if header_row_idx is None:
        data_start = 0
    else:
        data_start = header_row_idx + 1

        # Пропускаем ещё строки, если они выглядят как часть шапки:
        # без номера, без длинного текста.
        while data_start < len(lines):
            cols = lines[data_start]
            first = cols[0].strip().lstrip('+-').rstrip('.').strip() if cols else ''
            if first.isdigit():
                break
            # Если в первой ячейке пусто, а во второй — короткий текст
            # без точки — это ещё шапка.
            second = cols[1].strip() if len(cols) > 1 else ''
            if not first and len(second) < 25:
                data_start += 1
                continue
            break

    # ============================================================
    #  2. Парсим строки данных
    # ============================================================

    parsed = []
    last_order = 0

    for i in range(data_start, len(lines)):
        cols = lines[i]

        def get_cell(key):
            col = header_map.get(key)
            if col is None or col >= len(cols):
                return None
            return cols[col]

        topic_raw = get_cell('topic')
        if topic_raw is None:
            candidates = [c for c in cols if c.strip() and len(c.strip()) > 3]
            if not candidates:
                continue
            topic = max(candidates, key=len).strip()
        else:
            topic = topic_raw.strip()

        if not topic or len(topic) < 3:
            continue

        # Номер (убираем + / - и точку)
        order_raw = get_cell('order_number')
        order_number = None
        if order_raw:
            cleaned = str(order_raw).strip().lstrip('+-').rstrip('.').strip()
            if cleaned.isdigit():
                order_number = int(cleaned)

        # Часы
        hours_raw = get_cell('hours')
        hours = None
        if hours_raw:
            h_clean = str(hours_raw).strip()
            if h_clean.isdigit():
                hours = int(h_clean)
        if hours is None or hours <= 0:
            hours = 2

        # Тип занятия
        raw_type = get_cell('lesson_type')
        raw_type_str = str(raw_type).strip() if raw_type else ''

        lt_lower = raw_type_str.lower()
        if 'практическ' in lt_lower or 'практик' in lt_lower:
            lesson_type = 'practice'
        elif 'экзамен' in lt_lower:
            lesson_type = 'exam'
        elif 'самостоятельн' in lt_lower or 'с/р' in lt_lower:
            lesson_type = 'independent'
        elif 'под запись' in lt_lower or 'диктант' in lt_lower:
            lesson_type = 'dictation'
        elif 'зачёт' in lt_lower or 'зачет' in lt_lower or 'дифф' in lt_lower:
            lesson_type = 'diff_credit'
        else:
            lesson_type = 'lecture'

        # Определяем skip
        topic_lower = topic.lower()
        skip = False

        # Раздел / Тема — заголовки
        if topic_lower.startswith('раздел ') or topic_lower.startswith('тема '):
            skip = True

        # Объединённая ячейка шапки
        if topic_lower in ('обязательная учебная нагрузка/самостоятельная работа',
                           'обязательная учебная нагрузка',
                           'самостоятельная работа'):
            skip = True

        # Одиночные цифры как тема («2», «3») — мусор
        if topic.strip().isdigit():
            skip = True

        # Если нет номера и нет вида занятия и нет длинного текста — пропуск
        if order_number is None and not raw_type_str and len(topic) < 20:
            skip = True

        # Если нет вида занятия, но есть номер — оставляем галочку
        # (пользователь сам решит: это тема без типа или дубликат)
        # Специально НЕ ставим skip.

        # Номер
        if order_number is None:
            if not skip:
                last_order += 1
                order_number = last_order
        else:
            if not skip:
                last_order = order_number

        parsed.append({
            'order_number': order_number,
            'topic': topic,
            'hours': hours,
            'lesson_type': lesson_type,
            'raw_type': raw_type_str,
            'skip': skip,
        })

    return parsed

def _parse_plan_xlsx(file):
    """
    Разбирает Excel-файл и возвращает список строк в том же формате,
    что _parse_plan_tsv.
    """
    import pandas as pd

    df = pd.read_excel(file, header=None)

    if df.empty:
        return []

    # Превращаем DataFrame в текстовое представление TSV и парсим общим парсером.
    lines = []
    for _, row in df.iterrows():
        cells = []
        for v in row:
            if pd.isna(v):
                cells.append('')
            else:
                cells.append(str(v))
        lines.append('\t'.join(cells))

    return _parse_plan_tsv('\n'.join(lines))


@journals_bp.route('/group-subjects/<int:gsid>/plan/import', methods=['GET', 'POST'])
@permission_required('add_journal')
def plan_import(gsid):
    """
    Импорт плана.

    GET  — форма: вкладка «Вставить из Word/Excel» и вкладка «Загрузить .xlsx».
    POST — с параметром source:
        source=paste → берём textarea
        source=file  → берём файл .xlsx
    """
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Журнал не найден', 'danger')
        return redirect(url_for('journals.index'))

    if request.method == 'GET':
        return render_template(
            'journal_plan_import.html',
            pair=pair,
            step='upload',
            parsed=None,
        )

    # POST — разбор
    source = request.form.get('source', 'paste')
    parsed = []
    filename = ''

    if source == 'paste':
        text = (request.form.get('paste_text') or '').strip()
        if not text:
            flash('Вставьте таблицу из Word или Excel', 'danger')
            return redirect(url_for('journals.plan_import', gsid=gsid))
        parsed = _parse_plan_tsv(text)
        filename = 'вставка из буфера'
    else:
        # source == 'file'
        if 'file' not in request.files:
            flash('Файл не выбран', 'danger')
            return redirect(url_for('journals.plan_import', gsid=gsid))

        file = request.files['file']
        if not file.filename:
            flash('Файл не выбран', 'danger')
            return redirect(url_for('journals.plan_import', gsid=gsid))

        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            flash('Поддерживаются только .xlsx и .xls', 'danger')
            return redirect(url_for('journals.plan_import', gsid=gsid))

        try:
            parsed = _parse_plan_xlsx(file)
            filename = file.filename
        except Exception as e:
            flash(f'Ошибка разбора файла: {e}', 'danger')
            return redirect(url_for('journals.plan_import', gsid=gsid))

    if not parsed:
        flash('Не найдено ни одной строки с данными. '
              'Проверьте, что скопирована таблица целиком, '
              'включая шапку и все строки.', 'warning')
        return redirect(url_for('journals.plan_import', gsid=gsid))

    # Если совсем мало данных — предупредим
    if len(parsed) < 3:
        flash(f'Найдено только {len(parsed)} строк(и). '
              'Проверьте, что таблица скопирована целиком.', 'warning')

    return render_template(
        'journal_plan_import.html',
        pair=pair,
        step='preview',
        parsed=parsed,
        filename=filename,
    )


@journals_bp.route('/group-subjects/<int:gsid>/plan/import/commit', methods=['POST'])
@permission_required('add_journal')
def plan_import_commit(gsid):
    """Сохраняет пункты плана после предпросмотра."""
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Журнал не найден', 'danger')
        return redirect(url_for('journals.index'))

    indices = set()
    for key in request.form:
        if key.startswith('row_') and key.endswith('_include'):
            try:
                idx = int(key.split('_')[1])
                indices.add(idx)
            except (ValueError, IndexError):
                pass

    created = 0
    errors = []

    for idx in sorted(indices):
        include = request.form.get(f'row_{idx}_include')
        if include != '1':
            continue

        topic = (request.form.get(f'row_{idx}_topic') or '').strip()
        if not topic:
            continue

        order_raw = request.form.get(f'row_{idx}_order', '')
        try:
            order_number = int(order_raw) if order_raw else None
        except ValueError:
            order_number = None

        hours_raw = request.form.get(f'row_{idx}_hours', '2')
        try:
            hours = int(hours_raw) if hours_raw else 2
        except ValueError:
            hours = 2

        lesson_type = request.form.get(f'row_{idx}_type', 'lecture')

        ok, msg, new_id = JournalPlan.create(
            gsid, order_number, topic, hours, lesson_type
        )
        if ok:
            created += 1
        else:
            errors.append(f'Строка {idx + 1}: {msg}')

    log_activity(
        uid, 'plan_import',
        f'Импорт плана: журнал #{gsid}, добавлено {created} пунктов',
        'journal', gsid,
    )

    parts = [f'Добавлено пунктов: {created}']
    if errors:
        parts.append(f'ошибок: {len(errors)}')
    flash(' • '.join(parts), 'success' if created else 'warning')

    for e in errors[:5]:
        flash(e, 'danger')

    return redirect(url_for('journals.plan_view', gsid=gsid))