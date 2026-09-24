import os
import warnings

from dotenv import load_dotenv

# Загружаем .env из корня проекта (если файла нет — тихо игнорируем)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    # SECRET_KEY: обязателен в .env. Fallback — только для локальной разработки.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        warnings.warn(
            "SECRET_KEY не задан в .env — используется небезопасный дефолт. "
            "Создайте .env (см. .env) и задайте SECRET_KEY.",
            RuntimeWarning,
        )
        SECRET_KEY = 'insecure-dev-key-change-me'

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # SESSION_COOKIE_SECURE = True  # включите, если работает только по HTTPS

    DATABASE = os.path.join(BASE_DIR, 'journal.db')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')

    # Типы занятий
    LESSON_TYPES = [
        ('lecture', 'Лекция'),
        ('practice', 'Практическая'),
        ('independent', 'С/Р (самостоятельная)'),
        ('dictation', 'Под запись'),
        ('exam', 'Экзамен'),
        ('diff_credit', 'Дифф. зачет')
    ]

    # Оценки
    GRADES = [
        ('', 'Без оценки'),
        ('5', '5'),
        ('4', '4'),
        ('3', '3'),
        ('2', '2'),
        ('passed', 'Зачтено (з)')
    ]


# Хосты/порт/дебаг для app.py
FLASK_HOST = os.getenv('FLASK_HOST', '192.168.3.5')
FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))
FLASK_DEBUG = _env_bool('FLASK_DEBUG', False)