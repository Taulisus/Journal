from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import User

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
            flash('Вход выполнен успешно', 'success')
            return redirect(url_for('main.dashboard'))  # ← ИЗМЕНИТЬ ЗДЕСЬ
        else:
            flash('Неверный логин или пароль', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('auth.login'))