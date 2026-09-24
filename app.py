import os

from flask import Flask, session

from config import Config, FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from models import init_db, GroupSubject, Permission
from auth import auth_bp
from routes import main_bp
from routes_schedule import schedule_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Создаём папки
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(Config.STATIC_FOLDER, 'charts'), exist_ok=True)
    os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'schedules'), exist_ok=True)

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

        return dict(
            has_permission=has_permission,
            get_semesters=get_semesters,
            get_hours=get_hours,
        )

    # Регистрируем blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(schedule_bp)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)