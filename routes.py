from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, Response
from decorators import login_required
from models import Group, Subject, Student, GroupSubject, get_db, UserProfile, Permission, Position, TeacherJournal, \
    Curator, TeacherHours, User, SemesterGrade, PositionPermission
from journal_manager import JournalManager
from utils import import_students_from_xlsx, generate_report_chart, generate_student_chart
from config import Config
from werkzeug.security import generate_password_hash
from stats import get_user_weekly_avg, refresh_user_weekly_avg, get_teacher_stats
from activity import (
    log_activity,
    get_recent_activity,
    get_activity_filtered,
    get_activity_for_export,
    get_unique_actions,
    get_unique_users,
    get_unique_target_types,
    activity_to_csv,
    get_old_activity_stats,
    clear_old_activity,
)
from datetime import datetime
import os
import re

main_bp = Blueprint('main', __name__)


@main_bp.context_processor
def utility_processor():
    def has_permission(permission_code):
        if 'user_id' in session:
            return Permission.has_permission(session['user_id'], permission_code)
        return False

    def get_semesters(gsid):
        return GroupSubject.get_semesters(gsid)

    def get_hours(gsid, semester):
        return GroupSubject.get_hours(gsid, semester)

    return dict(
        has_permission=has_permission,
        get_semesters=get_semesters,
        get_hours=get_hours
    )


def has_emoji(text):
    if not text:
        return False
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u27BF\U0001F900-\U0001F9FF]+",
        flags=re.UNICODE)
    return bool(emoji_pattern.search(text))


# ============================================================
#                 ГЛАВНАЯ
# ============================================================

@main_bp.route('/')
@login_required
def dashboard():
    uid = session['user_id']

    groups_count = len(Group.get_all())
    subjects_count = len(Subject.get_all())
    students_count = len(Student.get_all())
    pairs_count = len(GroupSubject.get_all())

    weekly_avg = get_user_weekly_avg(uid, weeks=4)

    activity = None
    if Permission.has_permission(uid, 'manage_users'):
        activity = get_recent_activity(limit=20)

    teacher_stats = None
    has_journals = len(TeacherJournal.get_user_journals(uid)) > 0
    if has_journals:
        teacher_stats = get_teacher_stats(uid)

    return render_template(
        'dashboard.html',
        groups_count=groups_count,
        subjects_count=subjects_count,
        students_count=students_count,
        pairs_count=pairs_count,
        weekly_avg=weekly_avg,
        activity=activity,
        teacher_stats=teacher_stats,
    )


@main_bp.route('/dashboard/refresh-stats', methods=['POST'])
@login_required
def refresh_stats():
    uid = session['user_id']
    data = refresh_user_weekly_avg(uid, weeks=4)
    return jsonify({'success': True, 'data': data})


# ============================================================
#                 ЛОГ ДЕЙСТВИЙ
# ============================================================

ACTION_LABELS = {
    'login': 'Вход в систему',
    'logout': 'Выход из системы',
    'add_group': 'Создание группы',
    'edit_group': 'Редактирование группы',
    'delete_group': 'Удаление группы',
    'add_subject': 'Создание предмета',
    'edit_subject': 'Редактирование предмета',
    'delete_subject': 'Удаление предмета',
    'add_student': 'Добавление студента',
    'edit_student': 'Редактирование студента',
    'delete_student': 'Удаление студента',
    'import_students': 'Импорт студентов',
    'add_journal': 'Создание журнала',
    'delete_journal': 'Удаление журнала',
    'edit_hours': 'Изменение часов',
    'add_lesson': 'Добавление занятия',
    'delete_lesson': 'Удаление занятия',
    'edit_lesson_type': 'Изменение типа занятия',
    'set_semester_grade': 'Оценка за семестр',
    'add_user': 'Создание пользователя',
    'edit_user': 'Редактирование пользователя',
    'delete_user': 'Удаление пользователя',
    'assign_journals': 'Назначение журналов',
    'profile_edit': 'Обновление профиля',
    'password_change': 'Смена пароля',
    'activity_export': 'Экспорт лога',
    'activity_cleanup': 'Очистка лога',
    'edit_role': 'Изменение прав роли',
}

TARGET_TYPE_LABELS = {
    'user': 'Пользователь',
    'group': 'Группа',
    'subject': 'Предмет',
    'student': 'Студент',
    'journal': 'Журнал',
    'lesson': 'Занятие',
    'position': 'Роль',
}


def _parse_activity_filters():
    return {
        'user_id': request.args.get('user_id', type=int),
        'action': (request.args.get('action') or '').strip() or None,
        'target_type': (request.args.get('target_type') or '').strip() or None,
        'date_from': (request.args.get('date_from') or '').strip() or None,
        'date_to': (request.args.get('date_to') or '').strip() or None,
        'search': (request.args.get('search') or '').strip() or None,
    }


@main_bp.route('/activity')
@login_required
def activity_log_page():
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    filters = _parse_activity_filters()

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    if per_page not in (20, 50, 100, 200):
        per_page = 50

    data = get_activity_filtered(filters, page=page, per_page=per_page)

    all_users = get_unique_users()
    all_actions = get_unique_actions()
    all_target_types = get_unique_target_types()

    cleanup_stats = get_old_activity_stats(days=90)

    return render_template(
        'activity.html',
        data=data,
        filters=filters,
        all_users=all_users,
        all_actions=all_actions,
        all_target_types=all_target_types,
        action_labels=ACTION_LABELS,
        target_type_labels=TARGET_TYPE_LABELS,
        cleanup_stats=cleanup_stats,
        per_page=per_page,
    )


@main_bp.route('/activity/export.csv')
@login_required
def activity_export_csv():
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    filters = _parse_activity_filters()
    items = get_activity_for_export(filters, limit=10000)

    csv_content = activity_to_csv(items)
    csv_bytes = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')

    filename = f'activity_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    log_activity(uid, 'activity_export',
                 f'Экспорт лога в CSV ({len(items)} записей)',
                 'user', uid)

    return Response(
        csv_bytes,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        }
    )


@main_bp.route('/activity/cleanup', methods=['POST'])
@login_required
def activity_cleanup():
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    days = request.form.get('days', 90, type=int)
    if days not in (30, 60, 90, 180, 365):
        days = 90

    deleted, error = clear_old_activity(days=days)

    if error:
        flash(f'Ошибка очистки: {error}', 'danger')
    elif deleted == 0:
        flash(f'Нет записей старше {days} дней — нечего удалять', 'info')
    else:
        log_activity(uid, 'activity_cleanup',
                     f'Очищено {deleted} записей старше {days} дней',
                     'user', uid)
        flash(f'Удалено {deleted} записей старше {days} дней', 'success')

    return redirect(url_for('main.activity_log_page'))


# ============================================================
#                 РОЛИ И ПРАВА
# ============================================================

@main_bp.route('/roles')
@login_required
def roles():
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_permissions'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    positions = Position.get_all()
    permissions = Permission.get_all()

    roles_data = []
    for pos in positions:
        pos_dict = dict(pos)
        pos_dict['permissions'] = PositionPermission.get_for_position(pos['id'])
        pos_dict['users_count'] = Position.count_users(pos['id'])
        roles_data.append(pos_dict)

    return render_template(
        'roles.html',
        roles=roles_data,
        permissions=permissions,
    )


@main_bp.route('/roles/<int:role_id>/save', methods=['POST'])
@login_required
def update_role_permissions(role_id):
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_permissions'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    pos = Position.get_by_id(role_id)
    if not pos:
        flash('Роль не найдена', 'danger')
        return redirect(url_for('main.roles'))

    permission_ids = request.form.getlist('permissions')
    permission_ids = [int(p) for p in permission_ids if p.isdigit()]

    s, m = PositionPermission.set_for_position(role_id, permission_ids)

    if s:
        log_activity(uid, 'edit_role',
                     f'Изменены права роли «{pos["name"]}» '
                     f'({len(permission_ids)} прав)',
                     'position', role_id)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.roles'))


# ============================================================
#                 ПРОФИЛЬ
# ============================================================

@main_bp.route('/profile')
@login_required
def profile():
    uid = session['user_id']
    return _render_profile(uid, is_self=True)


@main_bp.route('/profile/<int:uid>')
@login_required
def profile_view(uid):
    current_uid = session['user_id']
    if not Permission.has_permission(current_uid, 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.profile'))

    if uid == current_uid:
        return redirect(url_for('main.profile'))

    target = User.get_by_id(uid)
    if not target:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('main.users'))

    return _render_profile(uid, is_self=False)


def _render_profile(uid, is_self):
    profile_data = User.get_profile(uid)
    if not profile_data:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('main.dashboard'))

    positions = Position.get_user_positions(uid)
    journals = TeacherJournal.get_user_journals(uid)
    weekly_avg = get_user_weekly_avg(uid, weeks=4)
    recent_activity = get_recent_activity(limit=10, user_id=uid)

    # Разделяем права: личные и от ролей
    perms_personal = Permission.get_personal_permissions(uid)
    perms_from_roles = PositionPermission.get_permissions_for_user_via_positions(uid)
    perms_all = Permission.get_user_permissions(uid)

    # Словарь: code → name (из БД)
    perms_dict = {}
    for p in Permission.get_all():
        perms_dict[p['code']] = p['name']

    # Для каждой роли — её права
    positions_with_perms = []
    for pos in positions:
        pos_perms_ids = PositionPermission.get_for_position(pos['id'])
        pos_perms_codes = []
        for p in Permission.get_all():
            if p['id'] in pos_perms_ids:
                pos_perms_codes.append(p['code'])
        positions_with_perms.append({
            'position': dict(pos),
            'permission_codes': pos_perms_codes,
        })

    return render_template(
        'profile.html',
        profile_user=profile_data,
        positions=positions,
        positions_with_perms=positions_with_perms,
        perms=perms_all,
        perms_personal=perms_personal,
        perms_from_roles=perms_from_roles,
        perms_dict=perms_dict,
        journals=journals,
        weekly_avg=weekly_avg,
        recent_activity=recent_activity,
        is_self=is_self,
    )


@main_bp.route('/profile/edit', methods=['POST'])
@login_required
def profile_edit():
    uid = session['user_id']

    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()

    if has_emoji(username) or has_emoji(full_name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.profile'))

    phone = re.sub(r'[^\d]', '', phone)[:11] if phone else ''

    s, m = User.update_profile(uid, username, full_name, phone)

    if s:
        session['username'] = username
        log_activity(uid, 'profile_edit',
                     f'Обновлён профиль (логин: {username})',
                     'user', uid)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.profile'))


@main_bp.route('/profile/change-password', methods=['POST'])
@login_required
def profile_change_password():
    uid = session['user_id']

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    new_password2 = request.form.get('new_password2', '')

    s, m = User.change_password(uid, current_password, new_password, new_password2)

    if s:
        log_activity(uid, 'password_change',
                     'Пароль изменён',
                     'user', uid)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.profile'))


# ============ Группы ============
@main_bp.route('/groups')
@login_required
def groups():
    return render_template('groups.html', groups=Group.get_all())


@main_bp.route('/groups/add', methods=['POST'])
@login_required
def add_group():
    name = request.form['name'].strip()
    if not name:
        flash('Введите название группы', 'danger')
        return redirect(url_for('main.groups'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.groups'))

    s, m, new_id = Group.create(name)

    if s:
        log_activity(session['user_id'], 'add_group',
                     f'Создана группа «{name}»',
                     'group', new_id)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.groups'))


@main_bp.route('/groups/edit/<int:gid>', methods=['POST'])
@login_required
def edit_group(gid):
    name = request.form['name'].strip()
    if not name:
        flash('Введите название группы', 'danger')
        return redirect(url_for('main.groups'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.groups'))
    s, m = Group.update(gid, name)
    if s:
        log_activity(session['user_id'], 'edit_group',
                     f'Переименована группа #{gid} → «{name}»', 'group', gid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.groups'))


@main_bp.route('/groups/delete/<int:gid>')
@login_required
def delete_group(gid):
    grp = Group.get_by_id(gid)
    grp_name = grp['name'] if grp else f'#{gid}'
    s, m = Group.delete(gid)
    if s:
        log_activity(session['user_id'], 'delete_group',
                     f'Удалена группа «{grp_name}»', 'group', gid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.groups'))


# ============ Предметы ============
@main_bp.route('/subjects')
@login_required
def subjects():
    return render_template('subjects.html', subjects=Subject.get_all())


@main_bp.route('/subjects/add', methods=['POST'])
@login_required
def add_subject():
    name = request.form['name'].strip()
    if not name:
        flash('Введите название предмета', 'danger')
        return redirect(url_for('main.subjects'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.subjects'))

    s, m, new_id = Subject.create(name)

    if s:
        log_activity(session['user_id'], 'add_subject',
                     f'Создан предмет «{name}»',
                     'subject', new_id)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.subjects'))


@main_bp.route('/subjects/edit/<int:sid>', methods=['POST'])
@login_required
def edit_subject(sid):
    name = request.form['name'].strip()
    if not name:
        flash('Введите название предмета', 'danger')
        return redirect(url_for('main.subjects'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.subjects'))
    s, m = Subject.update(sid, name)
    if s:
        log_activity(session['user_id'], 'edit_subject',
                     f'Переименован предмет #{sid} → «{name}»', 'subject', sid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.subjects'))


@main_bp.route('/subjects/delete/<int:sid>')
@login_required
def delete_subject(sid):
    subj = Subject.get_by_id(sid)
    subj_name = subj['name'] if subj else f'#{sid}'
    s, m = Subject.delete(sid)
    if s:
        log_activity(session['user_id'], 'delete_subject',
                     f'Удалён предмет «{subj_name}»', 'subject', sid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.subjects'))


# ============ Студенты ============
@main_bp.route('/students')
@login_required
def students():
    return render_template('students.html', students=Student.get_all(), groups=Group.get_all())


@main_bp.route('/students/add', methods=['POST'])
@login_required
def add_student():
    gid = request.form['group_id']
    name = request.form['full_name'].strip()
    if not name:
        flash('Введите ФИО студента', 'danger')
        return redirect(url_for('main.students'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.students'))

    s, m, new_id = Student.create(gid, name)

    if s:
        log_activity(session['user_id'], 'add_student',
                     f'Добавлен студент «{name}»',
                     'student', new_id)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.students'))


@main_bp.route('/students/edit/<int:sid>', methods=['POST'])
@login_required
def edit_student(sid):
    gid = request.form['group_id']
    name = request.form['full_name'].strip()
    if not name:
        flash('Введите ФИО студента', 'danger')
        return redirect(url_for('main.students'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.students'))
    s, m = Student.update(sid, gid, name)
    if s:
        log_activity(session['user_id'], 'edit_student',
                     f'Изменён студент #{sid} → «{name}»', 'student', sid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.students'))


@main_bp.route('/students/delete/<int:sid>')
@login_required
def delete_student(sid):
    if not Permission.has_permission(session['user_id'], 'delete_student'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.students'))
    st = Student.get_by_id(sid)
    st_name = st['full_name'] if st else f'#{sid}'
    s, m = Student.delete(sid)
    if s:
        log_activity(session['user_id'], 'delete_student',
                     f'Удалён студент «{st_name}»', 'student', sid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.students'))


@main_bp.route('/students/import', methods=['POST'])
@login_required
def import_students():
    if not Permission.has_permission(session['user_id'], 'add_students'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.students'))
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('main.students'))
    file = request.files['file']
    gid = request.form.get('group_id')
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('main.students'))
    if not gid:
        flash('Выберите группу', 'danger')
        return redirect(url_for('main.students'))
    s, m = import_students_from_xlsx(file, gid)
    if s:
        log_activity(session['user_id'], 'import_students',
                     f'Импорт студентов: {m}', 'group', int(gid) if gid else None)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.students'))


# ============ Пары Группа-Предмет ============
@main_bp.route('/group-subjects')
@login_required
def group_subjects():
    uid = session['user_id']
    if Permission.has_permission(uid, 'manage_users'):
        pairs = GroupSubject.get_all()
    else:
        pairs = TeacherJournal.get_user_journals(uid)
    return render_template('group_subjects.html', pairs=pairs, groups=Group.get_all(), subjects=Subject.get_all())


@main_bp.route('/group-subjects/add', methods=['POST'])
@login_required
def add_group_subject():
    if not Permission.has_permission(session['user_id'], 'add_journal'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.group_subjects'))

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
                'exam': exam
            })

    if not semesters_data:
        semesters_data = [{'semester': 1, 'lecture': 0, 'practice': 0, 'independent': 0, 'exam': 0}]

    s, m, new_id = GroupSubject.create(gid, sid, semesters_data)

    if s:
        grp = Group.get_by_id(gid)
        subj = Subject.get_by_id(sid)
        gname = grp['name'] if grp else f'#{gid}'
        sname = subj['name'] if subj else f'#{sid}'
        log_activity(session['user_id'], 'add_journal',
                     f'Создан журнал «{gname}» / «{sname}»',
                     'journal', new_id)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.group_subjects'))


@main_bp.route('/group-subjects/delete/<int:gsid>')
@login_required
def delete_group_subject(gsid):
    pair = GroupSubject.get_by_id(gsid)
    pair_name = f'{pair["group_name"]} / {pair["subject_name"]}' if pair else f'#{gsid}'
    s, m = GroupSubject.delete(gsid)
    if s:
        log_activity(session['user_id'], 'delete_journal',
                     f'Удалён журнал «{pair_name}»', 'journal', gsid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.group_subjects'))


# ============ API: Получение часов пары ============
@main_bp.route('/group-subjects/get-hours/<int:gsid>')
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
            'exam_hours': h.get('exam_hours', 0)
        }
    return jsonify({'semesters': semesters, 'hours': hours})


# ============ Сохранение часов пары ============
@main_bp.route('/group-subjects/edit-hours', methods=['POST'])
@login_required
def edit_group_subject_hours():
    if not Permission.has_permission(session['user_id'], 'add_journal'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.group_subjects'))

    gsid = request.form['gsid']
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
        log_activity(session['user_id'], 'edit_hours',
                     f'Изменены часы журнала #{gsid}', 'journal', int(gsid))
        flash('Часы обновлены', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('main.group_subjects'))


# ============ Журнал ============
@main_bp.route('/journal/<int:gsid>')
@login_required
def journal(gsid):
    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Пара не найдена', 'danger')
        return redirect(url_for('main.group_subjects'))

    semesters = GroupSubject.get_semesters(gsid)
    if not semesters:
        flash('Нет настроенных семестров', 'danger')
        return redirect(url_for('main.group_subjects'))

    current_semester = request.args.get('semester', semesters[0], type=int)
    if current_semester not in semesters:
        current_semester = semesters[0]

    students = Student.get_by_group(pair['group_id'])
    journal_data = JournalManager.get_journal(gsid, current_semester)

    semester_grades_list = SemesterGrade.get_grades(gsid, current_semester)
    semester_grades = {}
    for g in semester_grades_list:
        semester_grades[g['student_id']] = g['grade']

    return render_template('journal.html', pair=pair, students=students,
                           journal_data=journal_data, lesson_types=Config.LESSON_TYPES,
                           grades=Config.GRADES, semesters=semesters,
                           current_semester=current_semester, semester_grades=semester_grades)


@main_bp.route('/journal/<int:gsid>/add-lesson', methods=['GET', 'POST'])
@login_required
def add_lesson(gsid):
    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Пара не найдена', 'danger')
        return redirect(url_for('main.group_subjects'))

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
            return redirect(url_for('main.add_lesson', gsid=gsid, semester=semester))
        if not re.match(r'^\d{4}-\d{4}$', ti):
            flash('Формат: 0900-1030', 'danger')
            return redirect(url_for('main.add_lesson', gsid=gsid, semester=semester))
        if len(topic) > 50:
            flash('Тема не может быть длиннее 50 символов', 'danger')
            return redirect(url_for('main.add_lesson', gsid=gsid, semester=semester))
        if has_emoji(topic):
            flash('Эмодзи запрещены в теме', 'danger')
            return redirect(url_for('main.add_lesson', gsid=gsid, semester=semester))

        students_data = {}
        for st in students:
            sid = str(st['id'])
            students_data[st['id']] = {
                'attendance': request.form.get(f'attendance_{sid}', 'present'),
                'grade': request.form.get(f'grade_{sid}') or None
            }

        s, m = JournalManager.add_lesson(gsid, date, ti, topic, ltype, semester, students_data)
        if s:
            log_activity(session['user_id'], 'add_lesson',
                         f'Добавлено занятие: {pair["group_name"]} / {pair["subject_name"]} '
                         f'({date}, {ti})',
                         'journal', gsid)
        flash(m, 'success' if s else 'danger')
        return redirect(url_for('main.journal', gsid=gsid, semester=semester))

    return render_template('add_lesson.html', pair=pair, students=students,
                           lesson_types=Config.LESSON_TYPES, grades=Config.GRADES,
                           semesters=semesters, current_semester=current_semester)


@main_bp.route('/journal/<int:gsid>/update-entry', methods=['POST'])
@login_required
def update_entry(gsid):
    entry_id = request.form['entry_id']
    attendance = request.form['attendance']
    grade = request.form.get('grade', None)
    s, m = JournalManager.update_entry(gsid, entry_id, attendance, grade)
    return jsonify({'success': s, 'message': m})


@main_bp.route('/journal/update-lesson-type', methods=['POST'])
@login_required
def update_lesson_type():
    gsid = request.form['gsid']
    date = request.form['date']
    time_interval = request.form['time_interval']
    semester = request.form['semester']
    new_type = request.form['type']

    if not Permission.has_permission(session['user_id'], 'view_journals'):
        return jsonify({'success': False, 'message': 'Недостаточно прав'})

    conn = get_db()
    table_name = JournalManager.get_table_name(gsid)

    try:
        if new_type == 'exam':
            exam_exists = conn.execute(
                f"SELECT COUNT(*) as c FROM {table_name} WHERE semester=? AND type='exam' AND NOT (date=? AND time_interval=?)",
                (semester, date, time_interval)
            ).fetchone()
            if exam_exists['c'] > 0:
                conn.close()
                return jsonify({'success': False, 'message': 'Экзамен в этом семестре уже существует!'})

        conn.execute(f'''
            UPDATE {table_name} 
            SET type = ?
            WHERE date = ? AND time_interval = ? AND semester = ?
        ''', (new_type, date, time_interval, semester))

        conn.commit()
        conn.close()

        log_activity(session['user_id'], 'edit_lesson_type',
                     f'Изменён тип занятия: журнал #{gsid}, {date} {time_interval} → {new_type}',
                     'journal', int(gsid))

        return jsonify({'success': True, 'message': 'Тип занятия обновлен'})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'})


@main_bp.route('/journal/<int:gsid>/delete-lesson/<date>/<ti>')
@login_required
def delete_lesson(gsid, date, ti):
    semester = request.args.get('semester', 1, type=int)
    s, m = JournalManager.delete_lesson(gsid, date, ti)
    if s:
        log_activity(session['user_id'], 'delete_lesson',
                     f'Удалено занятие: журнал #{gsid}, {date} {ti}',
                     'journal', gsid)
    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.journal', gsid=gsid, semester=semester))


# ============ Оценка за семестр ============
@main_bp.route('/journal/<int:gsid>/set-semester-grade', methods=['POST'])
@login_required
def set_semester_grade(gsid):
    if not Permission.has_permission(session['user_id'], 'set_semester_grade'):
        return jsonify({'success': False, 'message': 'Недостаточно прав'})

    student_id = request.form['student_id']
    semester = int(request.form['semester'])
    grade = request.form.get('grade', None)

    SemesterGrade.set_grade(student_id, gsid, semester, grade)

    log_activity(session['user_id'], 'set_semester_grade',
                 f'Выставлена оценка за семестр: журнал #{gsid}, студент #{student_id}, '
                 f'семестр {semester}, оценка {grade or "—"}',
                 'journal', int(gsid))

    return jsonify({'success': True})


# ============ Карточка студента ============
@main_bp.route('/student/<int:sid>')
@login_required
def student_card(sid):
    student = Student.get_by_id(sid)
    if not student:
        flash('Студент не найден', 'danger')
        return redirect(url_for('main.students'))

    group = Group.get_by_id(student['group_id'])

    conn = get_db()
    pairs = conn.execute(
        "SELECT gs.*, s.name as subject_name FROM group_subjects gs JOIN subjects s ON gs.subject_id=s.id WHERE gs.group_id=? ORDER BY s.name",
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
                'semester_grades': semester_grades
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
            (total_absences / (total_absences + total_attendances) * 100) if (
                                                                                         total_absences + total_attendances) > 0 else 0,
            1
        ),
        'overall_avg_grade': round(sum(total_grades) / len(total_grades), 2) if total_grades else 0
    }

    cf = f'student_{sid}_chart.png'
    cp = os.path.join(Config.STATIC_FOLDER, 'charts', cf)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    if subjects_stats:
        generate_student_chart(student['full_name'], subjects_stats, cp)

    return render_template('student_card.html', student=student, group=group,
                           subjects_stats=subjects_stats, overall_stats=overall,
                           chart_filename=f'charts/{cf}' if subjects_stats else None)


# ============ Отчеты ============
@main_bp.route('/reports')
@login_required
def reports():
    uid = session['user_id']
    if Permission.has_permission(uid, 'manage_users'):
        pairs = GroupSubject.get_all()
    else:
        pairs = TeacherJournal.get_user_journals(uid)
    return render_template('reports.html', pairs=pairs)


@main_bp.route('/reports/<int:gsid>')
@login_required
def view_report(gsid):
    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Пара не найдена', 'danger')
        return redirect(url_for('main.reports'))

    semester = request.args.get('semester', None, type=int)
    stats = JournalManager.get_statistics(gsid, semester)
    students = Student.get_by_group(pair['group_id'])

    student_stats = {}
    for s in stats['students']:
        st = Student.get_by_id(s['student_id'])
        if st:
            total_considered = (s['absences'] or 0) + (s['attendances'] or 0)

            student_stats[s['student_id']] = {
                'name': st['full_name'],
                'absences': s['absences'],
                'attendances': s['attendances'],
                'total': total_considered,
                'avg_grade': round(s['avg_grade'] or 0, 2),
                'absence_percent': round(
                    ((s['absences'] or 0) / total_considered * 100) if total_considered > 0 else 0,
                    1
                )
            }

    cf = f'report_{gsid}.png'
    cp = os.path.join(Config.STATIC_FOLDER, 'charts', cf)
    os.makedirs(os.path.dirname(cp), exist_ok=True)

    names = [s['full_name'] for s in students]
    absences = [student_stats.get(s['id'], {}).get('absences', 0) for s in students]
    avg_grades = [student_stats.get(s['id'], {}).get('avg_grade', 0) for s in students]

    generate_report_chart(names, absences, avg_grades, cp)

    return render_template('report_detail.html', pair=pair, stats=stats,
                           student_stats=student_stats, chart_filename=f'charts/{cf}')


# ============ Статистика часов преподавателя ============
@main_bp.route('/teacher/hours-stats')
@login_required
def teacher_hours_stats():
    uid = session['user_id']
    journals = TeacherJournal.get_user_journals(uid)

    stats = []
    total_planned = {'lecture': 0, 'practice': 0, 'independent': 0, 'exam': 0, 'total': 0}
    total_actual = {'lecture': 0, 'practice': 0, 'independent': 0, 'exam': 0, 'total': 0}

    for j in journals:
        semesters = GroupSubject.get_semesters(j['id'])
        for sem in semesters:
            planned_row = TeacherHours.get(uid, j['id'], sem)
            if planned_row:
                planned = dict(planned_row)
            else:
                planned = {'lecture_hours': 0, 'practice_hours': 0, 'independent_hours': 0, 'exam_hours': 0}

            actual = JournalManager.get_conducted_hours(j['id'], sem)

            pt = (planned.get('lecture_hours', 0) + planned.get('practice_hours', 0) +
                  planned.get('independent_hours', 0) + planned.get('exam_hours', 0))

            stats.append({
                'group_name': j['group_name'],
                'subject_name': j['subject_name'],
                'gs_id': j['id'],
                'semester': sem,
                'planned': {
                    'lecture': planned.get('lecture_hours', 0),
                    'practice': planned.get('practice_hours', 0),
                    'independent': planned.get('independent_hours', 0),
                    'exam': planned.get('exam_hours', 0),
                    'total': pt
                },
                'actual': {
                    'lecture': actual.get('lecture', 0),
                    'practice': actual.get('practice', 0),
                    'independent': actual.get('independent', 0),
                    'exam': actual.get('exam', 0),
                    'total': actual.get('total', 0)
                }
            })

            total_planned['lecture'] += planned.get('lecture_hours', 0)
            total_planned['practice'] += planned.get('practice_hours', 0)
            total_planned['independent'] += planned.get('independent_hours', 0)
            total_planned['exam'] += planned.get('exam_hours', 0)
            total_planned['total'] += pt

            total_actual['lecture'] += actual.get('lecture', 0)
            total_actual['practice'] += actual.get('practice', 0)
            total_actual['independent'] += actual.get('independent', 0)
            total_actual['exam'] += actual.get('exam', 0)
            total_actual['total'] += actual.get('total', 0)

    return render_template('teacher_hours.html', stats=stats,
                           total_planned=total_planned, total_actual=total_actual)


# ============ Пользователи ============
@main_bp.route('/users')
@login_required
def users():
    if not Permission.has_permission(session['user_id'], 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    users_raw = User.get_all()
    positions = Position.get_all()
    permissions = Permission.get_all()

    users_list = []
    for u in users_raw:
        user = dict(u)
        user['positions'] = Position.get_user_positions(user['id'])
        user['position_ids'] = [p['id'] for p in user['positions']]
        user['perms'] = Permission.get_user_permissions(user['id'])  # итоговые (личные + роли)
        user['personal_perms'] = Permission.get_personal_permissions(user['id'])
        user['perm_ids'] = [p['id'] for p in permissions if p['code'] in user['personal_perms']]
        users_list.append(user)

    return render_template('users.html', users=users_list, positions=positions, permissions=permissions)


@main_bp.route('/users/add', methods=['POST'])
@login_required
def add_user():
    if not Permission.has_permission(session['user_id'], 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    username = request.form['username'].strip()
    password = request.form['password'].strip()
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    position_ids = request.form.getlist('positions')
    permission_ids = request.form.getlist('permissions')

    if not username or not password:
        flash('Введите логин и пароль', 'danger')
        return redirect(url_for('main.users'))
    if len(password) < 6:
        flash('Пароль должен быть не менее 6 символов', 'danger')
        return redirect(url_for('main.users'))
    if has_emoji(username) or has_emoji(full_name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.users'))

    phone = re.sub(r'[^\d]', '', phone)[:11] if phone else ''

    s, m, new_id = User.create(username, password, full_name, phone, position_ids, permission_ids)

    if s:
        log_activity(session['user_id'], 'add_user',
                     f'Создан пользователь «{username}» ({full_name})',
                     'user', new_id)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.users'))


@main_bp.route('/users/edit/<int:uid>', methods=['POST'])
@login_required
def edit_user(uid):
    if not Permission.has_permission(session['user_id'], 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '').strip()
    position_ids = request.form.getlist('positions')
    permission_ids = request.form.getlist('permissions')

    if has_emoji(full_name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.users'))

    phone = re.sub(r'[^\d]', '', phone)[:11] if phone else ''

    if uid == session['user_id']:
        admin_pos = next((p for p in Position.get_all() if p['code'] == 'admin'), None)
        if admin_pos and str(admin_pos['id']) not in position_ids:
            conn = get_db()
            cnt = conn.execute(
                "SELECT COUNT(*) as c FROM user_positions up JOIN positions p ON up.position_id=p.id WHERE p.code='admin'").fetchone()
            conn.close()
            if cnt['c'] <= 1:
                flash('Нельзя снять с себя должность администратора, если вы единственный', 'danger')
                return redirect(url_for('main.users'))

    conn = get_db()
    conn.execute("UPDATE user_profiles SET full_name=?, phone=? WHERE user_id=?", (full_name, phone, uid))
    if password and len(password) >= 6:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(password), uid))
    conn.commit()
    conn.close()

    Position.save(uid, position_ids)
    Permission.save(uid, permission_ids)

    log_activity(session['user_id'], 'edit_user',
                 f'Изменён пользователь #{uid} ({full_name})', 'user', uid)

    flash('Данные обновлены', 'success')
    return redirect(url_for('main.users'))


@main_bp.route('/users/delete/<int:uid>', methods=['POST'])
@login_required
def delete_user(uid):
    if not Permission.has_permission(session['user_id'], 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    if uid == session.get('user_id'):
        flash('Нельзя удалить самого себя', 'danger')
        return redirect(url_for('main.users'))

    conn = get_db()
    cnt = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
    conn.close()

    if cnt['c'] <= 1:
        flash('Нельзя удалить последнего пользователя', 'danger')
        return redirect(url_for('main.users'))

    target = User.get_by_id(uid)
    uname = target['username'] if target else f'#{uid}'

    User.delete(uid)

    log_activity(session['user_id'], 'delete_user',
                 f'Удалён пользователь «{uname}»', 'user', uid)

    flash('Пользователь удален', 'success')
    return redirect(url_for('main.users'))


# ============ Назначение журналов ============
@main_bp.route('/users/assign-journals/<int:uid>', methods=['GET', 'POST'])
@login_required
def assign_journals(uid):
    if not Permission.has_permission(session['user_id'], 'assign_teacher'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        gs_ids = request.form.getlist('journals')
        curator_gids = request.form.getlist('curator_groups')

        hours_data = {}
        for key in request.form:
            if key.startswith('hours_'):
                parts = key.split('_')
                if len(parts) == 4:
                    gsid = parts[1]
                    sem = parts[2]
                    htype = parts[3]
                    if gsid not in hours_data:
                        hours_data[gsid] = {}
                    if sem not in hours_data[gsid]:
                        hours_data[gsid][sem] = {}
                    hours_data[gsid][sem][htype] = int(request.form[key] or 0)

        conn = get_db()
        try:
            conn.execute("DELETE FROM teacher_journals WHERE user_id=?", (uid,))
            conn.execute("DELETE FROM curators WHERE user_id=?", (uid,))
            conn.execute("DELETE FROM teacher_hours WHERE user_id=?", (uid,))

            for gsid in gs_ids:
                try:
                    conn.execute("INSERT INTO teacher_journals (user_id, group_subject_id) VALUES (?,?)", (uid, gsid))
                except:
                    pass

                if gsid in hours_data:
                    for sem, h in hours_data[gsid].items():
                        TeacherHours.save_with_conn(conn, uid, gsid, int(sem),
                                                    h.get('lecture', 0), h.get('practice', 0),
                                                    h.get('independent', 0), h.get('exam', 0))

            for gid in curator_gids:
                try:
                    conn.execute("INSERT INTO curators (user_id, group_id) VALUES (?,?)", (uid, gid))
                except:
                    pass

            conn.commit()

            log_activity(session['user_id'], 'assign_journals',
                         f'Обновлены назначения для пользователя #{uid} '
                         f'(журналов: {len(gs_ids)}, кураторство: {len(curator_gids)})',
                         'user', uid)

            flash('Назначения сохранены', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Ошибка сохранения: {str(e)}', 'danger')
        finally:
            conn.close()

        return redirect(url_for('main.users'))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()

    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('main.users'))

    all_pairs = GroupSubject.get_all()
    all_groups = Group.get_all()
    assigned = TeacherJournal.get_user_journals(uid)
    assigned_ids = [j['id'] for j in assigned]

    curator_groups = Curator.get_user_groups(uid)
    curator_ids = [g['id'] for g in curator_groups]

    hours_dict = {}
    semesters_dict = {}

    for pair in all_pairs:
        pair_id_str = str(pair['id'])
        semesters = GroupSubject.get_semesters(pair['id'])
        semesters_dict[pair_id_str] = semesters
        hours_dict[pair_id_str] = {}

        for sem in semesters:
            sem_str = str(sem)
            teacher_hours_row = TeacherHours.get(uid, pair['id'], sem)

            if teacher_hours_row:
                th = dict(teacher_hours_row)
                hours_dict[pair_id_str][sem_str] = {
                    'lecture_hours': th.get('lecture_hours', 0),
                    'practice_hours': th.get('practice_hours', 0),
                    'independent_hours': th.get('independent_hours', 0),
                    'exam_hours': th.get('exam_hours', 0)
                }
            else:
                default_hours = GroupSubject.get_hours(pair['id'], sem)
                hours_dict[pair_id_str][sem_str] = {
                    'lecture_hours': default_hours.get('lecture_hours', 0),
                    'practice_hours': default_hours.get('practice_hours', 0),
                    'independent_hours': default_hours.get('independent_hours', 0),
                    'exam_hours': default_hours.get('exam_hours', 0)
                }

    return render_template('assign_journals.html', user=user, pairs=all_pairs,
                           groups=all_groups, assigned_ids=assigned_ids,
                           curator_ids=curator_ids, hours_dict=hours_dict,
                           semesters_dict=semesters_dict)