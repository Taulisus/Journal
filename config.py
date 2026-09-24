import os
import warnings
from datetime import datetime

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
            "Создайте .env (см. .env.example) и задайте SECRET_KEY.",
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

    # ============================================================
    #                 ИНТЕРВАЛЫ ПАР ПО ДНЯМ НЕДЕЛИ
    # ============================================================
    # Ключ — день недели (0=Пн, 1=Вт, ..., 5=Сб).
    # Значение — список кортежей (value, label), где value — код вида '0830-1000'.
    #
    # Пн и Сб идут по 1 академическому часу (45–60 мин), Вт-Пт — по 2.

    TIME_INTERVALS_BY_DAY = {
        0: [  # Понедельник
            ('0830-0930', '1 пара (08:30–09:30)'),
            ('1000-1100', '2 пара (10:00–11:00)'),
            ('1110-1210', '3 пара (11:10–12:10)'),
            ('1340-1440', '4 пара (13:40–14:40)'),
            ('1510-1610', '5 пара (15:10–16:10)'),
            ('1620-1720', '6 пара (16:20–17:20)'),
            ('1730-1830', '7 пара (17:30–18:30)'),
        ],
        1: [  # Вторник
            ('0830-1000', '1 пара (08:30–10:00)'),
            ('1030-1200', '2 пара (10:30–12:00)'),
            ('1210-1340', '3 пара (12:10–13:40)'),
            ('1350-1520', '4 пара (13:50–15:20)'),
            ('1550-1720', '5 пара (15:50–17:20)'),
            ('1730-1900', '6 пара (17:30–19:00)'),
            ('1910-2040', '7 пара (19:10–20:40)'),
        ],
        2: [  # Среда
            ('0830-1000', '1 пара (08:30–10:00)'),
            ('1030-1200', '2 пара (10:30–12:00)'),
            ('1210-1340', '3 пара (12:10–13:40)'),
            ('1350-1520', '4 пара (13:50–15:20)'),
            ('1550-1720', '5 пара (15:50–17:20)'),
            ('1730-1900', '6 пара (17:30–19:00)'),
            ('1910-2040', '7 пара (19:10–20:40)'),
        ],
        3: [  # Четверг
            ('0830-1000', '1 пара (08:30–10:00)'),
            ('1030-1200', '2 пара (10:30–12:00)'),
            ('1210-1340', '3 пара (12:10–13:40)'),
            ('1350-1520', '4 пара (13:50–15:20)'),
            ('1550-1720', '5 пара (15:50–17:20)'),
            ('1730-1900', '6 пара (17:30–19:00)'),
            ('1910-2040', '7 пара (19:10–20:40)'),
        ],
        4: [  # Пятница
            ('0830-1000', '1 пара (08:30–10:00)'),
            ('1030-1200', '2 пара (10:30–12:00)'),
            ('1210-1340', '3 пара (12:10–13:40)'),
            ('1350-1520', '4 пара (13:50–15:20)'),
            ('1550-1720', '5 пара (15:50–17:20)'),
            ('1730-1900', '6 пара (17:30–19:00)'),
            ('1910-2040', '7 пара (19:10–20:40)'),
        ],
        5: [  # Суббота
            ('0830-0930', '1 пара (08:30–09:30)'),
            ('0945-1045', '2 пара (09:45–10:45)'),
            ('1055-1155', '3 пара (10:55–11:55)'),
            ('1205-1305', '4 пара (12:05–13:05)'),
            ('1320-1420', '5 пара (13:20–14:20)'),
            ('1430-1530', '6 пара (14:30–15:30)'),
            ('1540-1640', '7 пара (15:40–16:40)'),
        ],
    }

    # Воскресенье (6) — выходной. Если вдруг что-то вводится на Вс,
    # отдаём интервалы как для Вт (по умолчанию).
    DEFAULT_DAY_FOR_INTERVALS = 1  # Вт

    # Перерывы (не пары) — для парсера PDF, чтобы их отбрасывать.
    BREAK_INTERVALS = [
        '1210-1255',  # Пн, перерыв
        '1255-1340',  # Пн, перерыв
    ]

    # Имена дней недели (0=Пн)
    DAY_NAMES_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    DAY_NAMES_FULL = [
        'Понедельник', 'Вторник', 'Среда', 'Четверг',
        'Пятница', 'Суббота', 'Воскресенье',
    ]

    # ============================================================
    #                 ХЕЛПЕРЫ
    # ============================================================

    @classmethod
    def get_time_intervals(cls, date_str):
        """
        Возвращает список интервалов для конкретной даты.

        date_str: 'YYYY-MM-DD'

        Возвращает список кортежей (value, label).
        Для воскресенья (6) — отдаёт интервалы дня по умолчанию.
        При ошибке парсинга даты — тоже отдаёт день по умолчанию.
        """
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            weekday = dt.weekday()  # 0=Пн, 5=Сб, 6=Вс
        except (ValueError, TypeError):
            weekday = cls.DEFAULT_DAY_FOR_INTERVALS

        return cls.TIME_INTERVALS_BY_DAY.get(
            weekday,
            cls.TIME_INTERVALS_BY_DAY[cls.DEFAULT_DAY_FOR_INTERVALS],
        )

    @classmethod
    def get_weekday(cls, date_str):
        """0=Пн .. 6=Вс или None при ошибке."""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').weekday()
        except (ValueError, TypeError):
            return None

    @classmethod
    def get_day_name_short(cls, date_str):
        wd = cls.get_weekday(date_str)
        if wd is None:
            return ''
        return cls.DAY_NAMES_SHORT[wd]

    @classmethod
    def get_day_name_full(cls, date_str):
        wd = cls.get_weekday(date_str)
        if wd is None:
            return ''
        return cls.DAY_NAMES_FULL[wd]

    @classmethod
    def is_valid_interval_for_date(cls, date_str, interval):
        """
        True, если интервал входит в список разрешённых для этой даты
        (или входит в BREAK_INTERVALS — тогда False).
        """
        if interval in cls.BREAK_INTERVALS:
            return False
        valid = {v for v, _ in cls.get_time_intervals(date_str)}
        return interval in valid

    @classmethod
    def intervals_as_json(cls):
        """
        Возвращает все интервалы в виде dict {weekday: [[value, label], ...]}.
        Удобно для прокидывания в JS через json_script.
        """
        return {
            str(day): [[v, label] for v, label in pairs]
            for day, pairs in cls.TIME_INTERVALS_BY_DAY.items()
        }


# ============================================================
#                 FLASK HOST / PORT / DEBUG
# ============================================================

FLASK_HOST = os.getenv('FLASK_HOST', '192.168.3.5')
FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))
FLASK_DEBUG = _env_bool('FLASK_DEBUG', False)