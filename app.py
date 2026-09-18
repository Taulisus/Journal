from flask import Flask
from config import Config
from models import init_db
from auth import auth_bp
from routes import main_bp
import os


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Создаем папки
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(Config.STATIC_FOLDER, 'charts'), exist_ok=True)

    # Инициализируем БД
    init_db()

    # Регистрируем blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='192.168.3.5', port=5000)