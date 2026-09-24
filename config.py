import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'journal.db')
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    STATIC_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

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