# blueprints/users.py
# -*- coding: utf-8 -*-
"""
Blueprint для пользователей, ролей, назначений журналов.
URL-префиксы: /users, /roles
"""

import re

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session,
)
from werkzeug.security import generate_password_hash

from decorators import login_required, permission_required
from models import (
    get_db, User, UserProfile, Permission, Position, PositionPermission,
    GroupSubject, Group, TeacherJournal, Curator, TeacherHours,
)
from activity import log_activity
from ._helpers import has_emoji


users_bp = Blueprint('users', __name__, url_prefix='/users')
roles_bp = Blueprint('roles', __name__, url_prefix='/roles')


# ============================================================
#                 ПОЛЬЗОВАТЕЛИ
# ============================================================

@users_bp.route('/', strict_slashes=False)
@permission_required('manage_users')
def index():
    from models_schedule import Teacher

    users_raw = User.get_all_with_teacher()
    positions = Position.get_all()
    permissions = Permission.get_all()
    teachers = Teacher.get_all(active_only=False)

    users_list = []
    for u in users_raw:
        user = dict(u)
        user['positions'] = Position.get_user_positions(user['id'])
        user['position_ids'] = [p['id'] for p in user['positions']]
        user['perms'] = Permission.get_user_permissions(user['id'])
        user['personal_perms'] = Permission.get_personal_permissions(user['id'])
        user['perm_ids'] = [
            p['id'] for p in permissions
            if p['code'] in user['personal_perms']
        ]
        users_list.append(user)

    return render_template(
        'users.html',
        users=users_list,
        positions=positions,
        permissions=permissions,
        teachers=teachers,
    )


@users_bp.route('/add', methods=['POST'])
@permission_required('manage_users')
def add():
    username = request.form['username'].strip()
    password = request.form['password'].strip()
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    position_ids = request.form.getlist('positions')
    permission_ids = request.form.getlist('permissions')
    teacher_id = request.form.get('teacher_id', type=int) or None

    if not username or not password:
        flash('Введите логин и пароль', 'danger')
        return redirect(url_for('users.index'))
    if len(password) < 6:
        flash('Пароль должен быть не менее 6 символов', 'danger')
        return redirect(url_for('users.index'))
    if has_emoji(username) or has_emoji(full_name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('users.index'))

    phone = re.sub(r'[^\d]', '', phone)[:11] if phone else ''

    s, m, new_id = User.create(
        username, password, full_name, phone, position_ids, permission_ids
    )

    if s:
        if teacher_id:
            User.set_teacher_id(new_id, teacher_id)

        log_activity(
            session['user_id'], 'add_user',
            f'Создан пользователь «{username}» ({full_name})',
            'user', new_id,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('users.index'))


@users_bp.route('/edit/<int:uid>', methods=['POST'])
@permission_required('manage_users')
def edit(uid):
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '').strip()
    position_ids = request.form.getlist('positions')
    permission_ids = request.form.getlist('permissions')
    teacher_id = request.form.get('teacher_id', type=int) or None

    if has_emoji(full_name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('users.index'))

    phone = re.sub(r'[^\d]', '', phone)[:11] if phone else ''

    if uid == session['user_id']:
        admin_pos = next(
            (p for p in Position.get_all() if p['code'] == 'admin'), None
        )
        if admin_pos and str(admin_pos['id']) not in position_ids:
            conn = get_db()
            cnt = conn.execute(
                "SELECT COUNT(*) as c FROM user_positions up "
                "JOIN positions p ON up.position_id=p.id "
                "WHERE p.code='admin'"
            ).fetchone()
            conn.close()
            if cnt['c'] <= 1:
                flash(
                    'Нельзя снять с себя должность администратора, '
                    'если вы единственный',
                    'danger'
                )
                return redirect(url_for('users.index'))

    conn = get_db()
    conn.execute(
        "UPDATE user_profiles SET full_name=?, phone=? WHERE user_id=?",
        (full_name, phone, uid),
    )
    if password and len(password) >= 6:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(password), uid),
        )
    conn.commit()
    conn.close()

    Position.save(uid, position_ids)
    Permission.save(uid, permission_ids)
    User.set_teacher_id(uid, teacher_id)

    log_activity(
        session['user_id'], 'edit_user',
        f'Изменён пользователь #{uid} ({full_name})',
        'user', uid,
    )

    flash('Данные обновлены', 'success')
    return redirect(url_for('users.index'))


@users_bp.route('/delete/<int:uid>', methods=['POST'])
@permission_required('manage_users')
def delete(uid):
    if uid == session.get('user_id'):
        flash('Нельзя удалить самого себя', 'danger')
        return redirect(url_for('users.index'))

    conn = get_db()
    cnt = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
    conn.close()

    if cnt['c'] <= 1:
        flash('Нельзя удалить последнего пользователя', 'danger')
        return redirect(url_for('users.index'))

    target = User.get_by_id(uid)
    uname = target['username'] if target else f'#{uid}'

    User.delete(uid)

    log_activity(
        session['user_id'], 'delete_user',
        f'Удалён пользователь «{uname}»',
        'user', uid,
    )

    flash('Пользователь удален', 'success')
    return redirect(url_for('users.index'))


# ============================================================
#                 НАЗНАЧЕНИЕ ЖУРНАЛОВ
# ============================================================

@users_bp.route('/assign-journals/<int:uid>', methods=['GET', 'POST'])
@permission_required('assign_teacher')
def assign_journals(uid):
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
                    conn.execute(
                        "INSERT INTO teacher_journals (user_id, group_subject_id) "
                        "VALUES (?,?)",
                        (uid, gsid),
                    )
                except Exception:
                    pass

                if gsid in hours_data:
                    for sem, h in hours_data[gsid].items():
                        TeacherHours.save_with_conn(
                            conn, uid, gsid, int(sem),
                            h.get('lecture', 0), h.get('practice', 0),
                            h.get('independent', 0), h.get('exam', 0),
                        )

            for gid in curator_gids:
                try:
                    conn.execute(
                        "INSERT INTO curators (user_id, group_id) VALUES (?,?)",
                        (uid, gid),
                    )
                except Exception:
                    pass

            conn.commit()

            log_activity(
                session['user_id'], 'assign_journals',
                f'Обновлены назначения для пользователя #{uid} '
                f'(журналов: {len(gs_ids)}, кураторство: {len(curator_gids)})',
                'user', uid,
            )

            flash('Назначения сохранены', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Ошибка сохранения: {str(e)}', 'danger')
        finally:
            conn.close()

        return redirect(url_for('users.index'))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()

    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('users.index'))

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
                    'exam_hours': th.get('exam_hours', 0),
                }
            else:
                default_hours = GroupSubject.get_hours(pair['id'], sem)
                hours_dict[pair_id_str][sem_str] = {
                    'lecture_hours': default_hours.get('lecture_hours', 0),
                    'practice_hours': default_hours.get('practice_hours', 0),
                    'independent_hours': default_hours.get('independent_hours', 0),
                    'exam_hours': default_hours.get('exam_hours', 0),
                }

    return render_template(
        'assign_journals.html',
        user=user,
        pairs=all_pairs,
        groups=all_groups,
        assigned_ids=assigned_ids,
        curator_ids=curator_ids,
        hours_dict=hours_dict,
        semesters_dict=semesters_dict,
    )


# ============================================================
#                 РОЛИ И ПРАВА
# ============================================================

@roles_bp.route('/', strict_slashes=False)
@login_required
def index():
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


@roles_bp.route('/<int:role_id>/save', methods=['POST'])
@login_required
def save_role(role_id):
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_permissions'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    pos = Position.get_by_id(role_id)
    if not pos:
        flash('Роль не найдена', 'danger')
        return redirect(url_for('roles.index'))

    permission_ids = request.form.getlist('permissions')
    permission_ids = [int(p) for p in permission_ids if p.isdigit()]

    s, m = PositionPermission.set_for_position(role_id, permission_ids)

    if s:
        log_activity(
            uid, 'edit_role',
            f'Изменены права роли «{pos["name"]}» ({len(permission_ids)} прав)',
            'position', role_id,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('roles.index'))