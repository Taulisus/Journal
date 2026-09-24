# 📔 Электронный журнал преподавателя

> Локальное веб-приложение для ведения электронного журнала колледжа/техникума:
> группы, студенты, посещаемость, оценки, отчёты, расписание с импортом из PDF.

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-black?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

---

## ✨ Возможности

### 📚 Журнал
- Ведение **пары Группа-Предмет** (`group_subjects`) с динамическими таблицами `journal_<id>`
- Семестры 1–3 с часами по типам занятий: лекции, практика, С/Р, экзамен
- Отметки посещаемости и оценки (2, 3, 4, 5, «зачтено»)
- Оценки за семестр
- Карточка студента с графиком успеваемости и посещаемости
- Отчёты по группе с графиками (matplotlib)

### 📅 Расписание
- Blueprint `/schedule` — день/неделя, фильтры по группе, преподавателю, аудитории
- **Импорт PDF-расписания** через веб-интерфейс с предпросмотром и чекбоксами
- Fuzzy-матчинг преподавателей через `rapidfuzz` (`Тетенькин Д.А.` находит `Тетенькин Дмитрий Александрович`)
- Автосоздание групп, предметов, преподавателей, аудиторий при импорте
- Право `edit_schedule` — преподаватель редактирует только свои занятия
- Виджет «Расписание на неделю» на главной странице
- Справочники: преподаватели, аудитории, алиасы групп
- Свободные аудитории на заданное время

### 👥 Пользователи и роли
- Логин/пароль, хеширование через `werkzeug.security`
- 5 ролей: admin, teacher, curator, head_teacher, methodist
- 12 прав, назначаются роли и/или лично пользователю
- Связка «пользователь ↔ преподаватель» через UI

### 🎓 Учебный процесс
- Группы, предметы, студенты
- Импорт студентов из Excel/CSV
- Массовый перевод студентов между группами с сохранением истории
- Назначение преподавателя на журналы
- Статистика часов преподавателя (план/факт)

### 📊 Логи, бэкапы, экспорт
- Лог действий пользователей (`activity_log`) с фильтрами и экспортом CSV
- Резервные копии БД с ротацией (хранятся 30 последних)
- Экспорт журнала в Excel (`.xlsx`)
- Автобэкап перед опасными операциями

### 📱 UI
- Bootstrap 5, адаптивная вёрстка
- Оптимизировано под iPhone 12 mini (375px)
- Мобильное подменю с аккордеонами
- Drag-to-scroll в таблице журнала (десктоп)
- Быстрые отметки в мобильной версии

---

## 🚀 Установка и запуск

### Требования

- **Python 3.12+** (проверено на 3.14)
- pip
- Windows / Linux / macOS

### 1. Клонировать репозиторий

```bash
git clone https://github.com/Taulisus/Journal.git
cd Journal
```

### 2. Создать виртуальное окружение

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить `.env`

Создайте `.env` в корне проекта (скопируйте из `.env.example`):

```bash
copy .env.example .env    # Windows
cp .env.example .env      # Linux / macOS
```

Откройте `.env` и заполните:

```env
SECRET_KEY=<сюда длинную случайную строку>

# Опционально:
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=False

# Пароль для admin (если не указать — сгенерируется автоматически)
ADMIN_INITIAL_PASSWORD=ВашПароль123
```

**Сгенерировать `SECRET_KEY`:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Запустить

```bash
python app.py
```

Приложение будет доступно на `http://127.0.0.1:5000`.

### 6. Войти

- **Логин:** `admin`
- **Пароль:** из `ADMIN_INITIAL_PASSWORD` (или из консоли при первом запуске)

> ⚠️ Смените пароль сразу после первого входа!

---

## 🗂 Структура проекта

```text
Journal/
├── app.py                  фабрика приложения, регистрация blueprints
├── config.py               Config, интервалы пар, host/port
├── auth.py                 Blueprint auth (login/logout)
├── routes.py               Blueprint main (dashboard, профиль, отчёты, лог)
├── routes_schedule.py      Blueprint schedule
├── decorators.py           login_required, permission_required
├── models.py               все модели БД
├── models_schedule.py      модели расписания
├── journal_manager.py      работа с journal_<gsid>
├── stats.py                статистика, кэш
├── utils.py                импорт, графики, экспорт, бэкапы, цвета
├── activity.py             лог действий
├── requirements.txt
├── ПРОГРЕСС.md             история разработки
│
├── blueprints/             Blueprint'ы по доменам
│   ├── _helpers.py         общие хелперы
│   ├── groups.py           группы
│   ├── subjects.py         предметы
│   ├── students.py         студенты + карточка
│   ├── journals.py         журналы, уроки, оценки, экспорт
│   └── users.py            пользователи, роли, назначения
│
├── migrations/             миграции БД (v3–v6)
├── parsers/
│   └── pdf_schedule.py     парсер PDF-расписания
│
├── templates/              Jinja2-шаблоны
│   ├── base.html
│   ├── dashboard.html
│   ├── journal.html
│   ├── schedule/
│   └── ...
│
├── static/                 CSS, графики
├── uploads/                временные файлы (PDF, Excel)
├── backups/                резервные копии БД (не в git)
└── journal.db              SQLite-база (не в git)
```

---

## 🧩 Стек

| Компонент | Версия | Назначение |
|---|---|---|
| Python | 3.12+ | язык |
| Flask | 3.1 | веб-фреймворк |
| SQLite | 3 | база данных |
| Bootstrap | 5.3 | UI |
| Bootstrap Icons | 1.10 | иконки |
| pandas | 2.3 | импорт Excel/CSV |
| openpyxl | 3.1 | экспорт в Excel |
| matplotlib | 3.11 | графики |
| PyMuPDF | 1.24 | парсинг PDF |
| RapidFuzz | 3.10 | fuzzy-матчинг преподавателей |
| python-dotenv | 1.1 | `.env` |

---

## ⚙️ Команды

```bash
# Запуск приложения
python app.py

# Миграция БД (идемпотентная)
python migrations/migration_v6.py

# Импорт преподавателей из Excel
python import_teachers.py

# Управление пользователями через CLI
python create_user.py list
python create_user.py add ivanov 123456
python create_user.py reset admin НовыйПароль123
python create_user.py delete ivanov

# Отладка PDF-парсера
python -m parsers.pdf_schedule "расписание.pdf" 1           # дамп координат стр. 1
python -m parsers.pdf_schedule "расписание.pdf" --summary   # сводка
```

---

## 🔐 Безопасность

- Пароли — `werkzeug.security` (PBKDF2-SHA256)
- `SECRET_KEY` — только в `.env`, не в git
- Права проверяются декоратором `@permission_required`
- Проверка владения журналом / занятием на мутирующих роутах
- Автобэкап БД перед `DROP TABLE` и массовым переводом
- Защита от эмодзи в вводимых полях (валидация на бэке)

### Что планируется

- CSRF-защита (Flask-WTF)
- Rate-limit на логине (Flask-Limiter)
- Локальные Bootstrap-ассеты (offline-режим)

---

## 📦 Бэкапы

Резервные копии БД создаются автоматически и вручную:

- **Автоматически** — перед массовым переводом студентов, перед удалением журнала.
- **Вручную** — через UI: `/activity` → «Создать бэкап».

Файлы сохраняются в `backups/journal_YYYYMMDD_HHMMSS_<prefix>.db`.
Хранятся последние **30** копий, старые удаляются автоматически.

### Восстановление

```bash
# Остановить приложение
# Заменить журнал:
copy backups\journal_YYYYMMDD_HHMMSS_manual.db journal.db
# Запустить приложение
python app.py
```

---

## 🤝 Contributing

Проект локальный, но если хотите помочь:

1. Форкните репозиторий
2. Создайте ветку: `git checkout -b feature/my-feature`
3. Закоммитьте: `git commit -am 'Add my feature'`
4. Запушьте: `git push origin feature/my-feature`
5. Откройте pull request

---

## 📝 Лицензия

MIT — см. [LICENSE](./LICENSE).

---

## 🎯 Roadmap

- [x] Авторизация, пользователи, роли
- [x] Группы, предметы, студенты
- [x] Журналы с посещаемостью и оценками
- [x] Отчёты и графики
- [x] Массовый перевод студентов
- [x] Лог действий + бэкапы
- [x] Расписание (CRUD, справочники)
- [x] Импорт расписания из PDF
- [x] Виджет «Расписание на неделю» на главной
- [x] Право `edit_schedule` для преподавателей
- [x] Связка «пользователь ↔ преподаватель» через UI
- [x] Разбиение на Blueprints
- [ ] CSRF-защита
- [ ] Rate-limit на логине
- [ ] Подсказки из расписания в журнале
- [ ] Тесты (pytest)
- [ ] Локальные Bootstrap-ассеты (offline)

---

## 📸 Скриншоты

> 💡 Добавьте свои скриншоты в папку `docs/screenshots/` и вставьте сюда.

| Главная | Журнал |
|---|---|
| _screenshots/dashboard.png_ | _screenshots/journal.png_ |

| Расписание | Карточка студента |
|---|---|
| _screenshots/schedule.png_ | _screenshots/student_card.png_ |

---

## 👤 Автор

- GitHub: [@Taulisus](https://github.com/Taulisus)

---

⭐ Если проект был полезен — поставьте звёздочку!
