from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import User
from activity import log_activity

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.find_by_username(username)
        if user and User.check_password(user, password):
            session['user_id'] = user['id']
            session['username'] = user['username']

            # === ЛОГ ===
            log_activity(
                user_id=user['id'],
                action='login',
                description=f'Вход в систему ({user["username"]})',
                target_type='user',
                target_id=user['id'],
            )

            flash('Вход выполнен успешно', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Неверный логин или пароль', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    uid = session.get('user_id')
    uname = session.get('username')

    if uid:
        # === ЛОГ ===
        log_activity(
            user_id=uid,
            action='logout',
            description=f'Выход из системы ({uname})',
            target_type='user',
            target_id=uid,
        )

    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('auth.login'))