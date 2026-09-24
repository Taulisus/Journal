# blueprints/groups.py
# -*- coding: utf-8 -*-
"""
Blueprint для групп.
URL-префикс: /groups
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session,
)

from decorators import login_required, permission_required
from models import Group
from activity import log_activity
from ._helpers import has_emoji


groups_bp = Blueprint('groups', __name__, url_prefix='/groups')


@groups_bp.route('/')
@login_required
def index():
    return render_template('groups.html', groups=Group.get_all())


@groups_bp.route('/add', methods=['POST'])
@permission_required('manage_users')
def add():
    name = request.form['name'].strip()
    if not name:
        flash('Введите название группы', 'danger')
        return redirect(url_for('groups.index'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('groups.index'))

    s, m, new_id = Group.create(name)

    if s:
        log_activity(
            session['user_id'], 'add_group',
            f'Создана группа «{name}»',
            'group', new_id,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('groups.index'))


@groups_bp.route('/edit/<int:gid>', methods=['POST'])
@permission_required('manage_users')
def edit(gid):
    name = request.form['name'].strip()
    if not name:
        flash('Введите название группы', 'danger')
        return redirect(url_for('groups.index'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('groups.index'))

    s, m = Group.update(gid, name)
    if s:
        log_activity(
            session['user_id'], 'edit_group',
            f'Переименована группа #{gid} → «{name}»',
            'group', gid,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('groups.index'))


@groups_bp.route('/delete/<int:gid>')
@permission_required('manage_users')
def delete(gid):
    grp = Group.get_by_id(gid)
    grp_name = grp['name'] if grp else f'#{gid}'

    s, m = Group.delete(gid)
    if s:
        log_activity(
            session['user_id'], 'delete_group',
            f'Удалена группа «{grp_name}»',
            'group', gid,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('groups.index'))