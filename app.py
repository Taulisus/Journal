import json
import os

from flask import Flask, session

from config import Config, FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from models import init_db, GroupSubject, Permission
from auth import auth_bp
from routes import main_bp
from blueprints.groups import groups_bp
from blueprints.subjects import subjects_bp
from blueprints.students import students_bp, student_card_bp
from blueprints.journals import journals_bp
from blueprints.users import users_bp, roles_bp
from routes_schedule import schedule_bp
from utils import format_time_interval, get_grade_color, get_attendance_color


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Создаём папки
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(Config.STATIC_FOLDER, 'charts'), exist_ok=True)
    os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'schedules'), exist_ok=True)
    os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'exports'), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(Config.DATABASE), 'backups'), exist_ok=True)

    # Инициализируем БД
    init_db()

    # Глобальные хелперы для всех шаблонов (доступны во всех Blueprint'ах)
    @app.context_processor
    def utility_processor():
        def has_permission(permission_code):
            if 'user_id' in session:
                return Permission.has_permission(session['user_id'], permission_code)
            return False

        def get_semesters(gsid):
            return GroupSubject.get_semesters(gsid)

        def get_hours(gsid, semester):
            return GroupSubject.get_hours(gsid, semester)

        def get_time_intervals(date_str):
            return Config.get_time_intervals(date_str)

        def get_time_intervals_for_today():
            from datetime import datetime
            return Config.get_time_intervals(datetime.now().strftime('%Y-%m-%d'))

        return dict(
            has_permission=has_permission,
            get_semesters=get_semesters,
            get_hours=get_hours,
            format_time=format_time_interval,
            grade_color=get_grade_color,
            attendance_color=get_attendance_color,
            get_time_intervals=get_time_intervals,
            get_time_intervals_for_today=get_time_intervals_for_today,
            # JSON со всеми интервалами по дням — для JS на страницах
            all_time_intervals=Config.intervals_as_json(),
            day_names_short=Config.DAY_NAMES_SHORT,
            day_names_full=Config.DAY_NAMES_FULL,
        )

    # Регистрируем blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(subjects_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(student_card_bp)
    app.register_blueprint(journals_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(roles_bp)
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)