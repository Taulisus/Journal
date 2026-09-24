# blueprints/subjects.py
# -*- coding: utf-8 -*-
"""
Blueprint для предметов.
URL-префикс: /subjects
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session,
)

from decorators import login_required, permission_required
from models import Subject
from activity import log_activity
from ._helpers import has_emoji


subjects_bp = Blueprint('subjects', __name__, url_prefix='/subjects')


@subjects_bp.route('/', strict_slashes=False)
@login_required
def index():
    return render_template('subjects.html', subjects=Subject.get_all())


@subjects_bp.route('/add', methods=['POST'])
@permission_required('manage_users')
def add():
    name = request.form['name'].strip()
    if not name:
        flash('Введите название предмета', 'danger')
        return redirect(url_for('subjects.index'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('subjects.index'))

    s, m, new_id = Subject.create(name)

    if s:
        log_activity(
            session['user_id'], 'add_subject',
            f'Создан предмет «{name}»',
            'subject', new_id,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('subjects.index'))


@subjects_bp.route('/edit/<int:sid>', methods=['POST'])
@permission_required('manage_users')
def edit(sid):
    name = request.form['name'].strip()
    if not name:
        flash('Введите название предмета', 'danger')
        return redirect(url_for('subjects.index'))
    if has_emoji(name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('subjects.index'))

    s, m = Subject.update(sid, name)
    if s:
        log_activity(
            session['user_id'], 'edit_subject',
            f'Переименован предмет #{sid} → «{name}»',
            'subject', sid,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('subjects.index'))


@subjects_bp.route('/delete/<int:sid>')
@permission_required('manage_users')
def delete(sid):
    subj = Subject.get_by_id(sid)
    subj_name = subj['name'] if subj else f'#{sid}'

    s, m = Subject.delete(sid)
    if s:
        log_activity(
            session['user_id'], 'delete_subject',
            f'Удалён предмет «{subj_name}»',
            'subject', sid,
        )

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('subjects.index'))