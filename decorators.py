from functools import wraps
from flask import session, redirect, url_for, flash
from models import Permission

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission_code):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Пожалуйста, войдите в систему', 'warning')
                return redirect(url_for('auth.login'))
            if not Permission.has_permission(session['user_id'], permission_code):
                flash('Недостаточно прав для выполнения этого действия', 'danger')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator