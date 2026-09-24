from functools import wraps

from flask import session, redirect, url_for, flash, jsonify, request

from models import Permission


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/journal/'):
                return jsonify({'success': False, 'message': 'Не авторизован'}), 401
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def permission_required(*permission_codes):
    """
    Декоратор: пропускает, если у пользователя есть ХОТЯ БЫ ОДНО из прав.
    Если permission_codes пуст — работает как login_required.

    Для JSON-эндпоинтов (request.is_json или путь /journal/*)
    возвращает JSON 401/403, для остальных — redirect с flash.
    """
    codes = list(permission_codes)

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.is_json or request.path.startswith('/journal/'):
                    return jsonify({'success': False, 'message': 'Не авторизован'}), 401
                flash('Пожалуйста, войдите в систему', 'warning')
                return redirect(url_for('auth.login'))

            if codes:
                uid = session['user_id']
                if not any(Permission.has_permission(uid, c) for c in codes):
                    if request.is_json or request.path.startswith('/journal/'):
                        return jsonify({'success': False, 'message': 'Недостаточно прав'}), 403
                    flash('Недостаточно прав для выполнения этого действия', 'danger')
                    return redirect(url_for('main.dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator