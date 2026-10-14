"""
Blueprint для расписания.
Префикс: /schedule
"""

import os
import uuid as _uuid
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session, current_app,
)
from werkzeug.utils import secure_filename

from decorators import login_required, permission_required
from models import Group, Subject, get_db, Permission, User
from models_schedule import (
    ScheduleLesson, Teacher, Room, AcademicYear, GroupAlias,
)
from activity import log_activity


schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')


# ============================================================
#                 ХРАНИЛИЩЕ ПРЕДПРОСМОТРА ИМПОРТА
# ============================================================

_import_previews = {}
_IMPORT_PREVIEW_LIMIT = 50


def _register_preview(preview_id, data):
    if len(_import_previews) >= _IMPORT_PREVIEW_LIMIT:
        oldest = next(iter(_import_previews))
        _import_previews.pop(oldest, None)
    _import_previews[preview_id] = data


# ============================================================
#                 ПРОВЕРКА ДОСТУПА К ЗАНЯТИЮ
# ============================================================

def _can_edit_schedule(uid):
    return (
        Permission.has_permission(uid, 'manage_users')
        or Permission.has_permission(uid, 'edit_schedule')
    )


def _can_edit_lesson(uid, lesson):
    if Permission.has_permission(uid, 'manage_users'):
        return True
    if not Permission.has_permission(uid, 'edit_schedule'):
        return False
    teacher_id = User.get_teacher_id(uid)
    if not teacher_id:
        return False
    try:
        return lesson['teacher_id'] == teacher_id
    except (KeyError, TypeError):
        return False


# ============================================================
#                 УЧЕБНЫЙ ГОД
# ============================================================

def _current_year_range():
    """
    Возвращает (start_date_str, end_date_str) текущего учебного года
    или (None, None), если год не найден.
    """
    year = AcademicYear.get_current()
    if not year:
        return None, None
    try:
        return year['start_date'], year['end_date']
    except (KeyError, TypeError):
        return None, None


def _date_in_current_year(date_str):
    """True, если date_str (YYYY-MM-DD) входит в текущий учебный год."""
    start, end = _current_year_range()
    if not start or not end:
        return True  # нет года — не мешаем (лучше, чем совсем заблокировать)
    return start <= date_str <= end


# ============================================================
#                 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _parse_date(value, default=None):
    if not value:
        return default
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return value
    except (ValueError, TypeError):
        return default


def _today_str():
    return datetime.now().strftime('%Y-%m-%d')


def _week_start(date_str):
    if not date_str:
        date_str = _today_str()
    dt = datetime.strptime(date_str, '%Y-%m-%d').date()
    monday = dt - timedelta(days=dt.weekday())
    return monday.isoformat()


def _get_filters(uid=None):
    """
    Фильтры из query string.
    Для не-админа: если teacher_id не указан — ставим его самого.
    """
    f = {
        'group_id': request.args.get('group_id', type=int),
        'teacher_id': request.args.get('teacher_id', type=int),
        'room_id': request.args.get('room_id', type=int),
    }
    if uid is not None and f['teacher_id'] is None:
        if not Permission.has_permission(uid, 'manage_users'):
            # Если есть право edit_schedule (препод) — фильтруем на себя.
            if Permission.has_permission(uid, 'edit_schedule'):
                try:
                    my_tid = User.get_teacher_id(uid)
                    if my_tid:
                        f['teacher_id'] = my_tid
                except Exception:
                    pass
    return f


def _week_days(monday_str):
    monday = datetime.strptime(monday_str, '%Y-%m-%d').date()
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


def _day_label(date_str):
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    short = ScheduleLesson.DAY_NAMES_SHORT[dt.weekday()]
    full = ScheduleLesson.DAY_NAMES_FULL[dt.weekday()]
    return dt.strftime('%d.%m.%Y'), short, full


def _get_lesson_types():
    return [
        ('lecture', 'Лекция'),
        ('practice', 'Практическая'),
        ('independent', 'С/Р'),
        ('dictation', 'Под запись'),
        ('exam', 'Экзамен'),
        ('diff_credit', 'Дифф. зачёт'),
    ]


# ============================================================
#                 ГЛАВНАЯ СТРАНИЦА РАСПИСАНИЯ
# ============================================================

@schedule_bp.route('/')
@permission_required('view_journals')
def index():
    view = request.args.get('view', 'day')
    if view not in ('day', 'week'):
        view = 'day'

    date_str = _parse_date(request.args.get('date'), _today_str())

    uid = session['user_id']
    filters = _get_filters(uid=uid)

    groups = Group.get_all()
    teachers = Teacher.get_all()
    rooms = Room.get_all()

    can_edit_any = _can_edit_schedule(uid)
    my_teacher_id = User.get_teacher_id(uid)

    context = {
        'view': view,
        'date': date_str,
        'filters': filters,
        'groups': groups,
        'teachers': teachers,
        'rooms': rooms,
        'can_edit_any': can_edit_any,
        'my_teacher_id': my_teacher_id,
    }

    if view == 'week':
        monday = _week_start(date_str)
        week, start, end = ScheduleLesson.get_week(monday)

        days = []
        for d in _week_days(monday):
            label, short, full = _day_label(d)
            days.append({
                'date': d,
                'label': label,
                'day_short': short,
                'day_full': full,
                'is_today': d == _today_str(),
                'lessons': week.get(d, []),
            })

        context.update({
            'week_start': monday,
            'week_end': end.isoformat(),
            'week_days': days,
            'prev_week': (datetime.strptime(monday, '%Y-%m-%d').date()
                          - timedelta(days=7)).isoformat(),
            'next_week': (datetime.strptime(monday, '%Y-%m-%d').date()
                          + timedelta(days=7)).isoformat(),
        })
    else:
        lessons = ScheduleLesson.get_for_date(
            date_str,
            group_id=filters['group_id'],
            teacher_id=filters['teacher_id'],
            room_id=filters['room_id'],
        )

        lessons_editable = {l['id']: _can_edit_lesson(uid, l) for l in lessons}

        label, short, full = _day_label(date_str)
        context.update({
            'lessons': lessons,
            'lessons_editable': lessons_editable,
            'day_label': label,
            'day_short': short,
            'day_full': full,
            'is_today': date_str == _today_str(),
            'prev_day': (datetime.strptime(date_str, '%Y-%m-%d').date()
                         - timedelta(days=1)).isoformat(),
            'next_day': (datetime.strptime(date_str, '%Y-%m-%d').date()
                         + timedelta(days=1)).isoformat(),
        })

    return render_template('schedule/index.html', **context)


@schedule_bp.route('/today')
@permission_required('view_journals')
def today():
    uid = session['user_id']
    f = _get_filters(uid=uid)
    return redirect(url_for(
        'schedule.index',
        view='day',
        date=_today_str(),
        **{k: v for k, v in f.items() if v},
    ))


# ============================================================
#                 РЕДАКТИРОВАНИЕ
# ============================================================

@schedule_bp.route('/lesson/<int:lesson_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_lesson(lesson_id):
    uid = session['user_id']

    lesson = ScheduleLesson.get_by_id(lesson_id)
    if not lesson:
        flash('Занятие не найдено', 'danger')
        return redirect(url_for('schedule.index'))

    if not _can_edit_lesson(uid, lesson):
        flash('Недостаточно прав для редактирования этого занятия', 'danger')
        return redirect(url_for('schedule.index'))

    is_admin = Permission.has_permission(uid, 'manage_users')
    my_teacher_id = User.get_teacher_id(uid)

    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        pair_number = request.form.get('pair_number', type=int)
        time_start = request.form.get('time_start', '').strip()
        time_end = request.form.get('time_end', '').strip()
        group_id = request.form.get('group_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        room_id = request.form.get('room_id', type=int) or None
        lesson_type = request.form.get('lesson_type', 'lecture')

        # Задача 3: не-админ не может поставить чужого — форма игнорируется.
        if is_admin:
            teacher_id = request.form.get('teacher_id', type=int) or None
        else:
            teacher_id = my_teacher_id

        if not date or not _parse_date(date):
            flash('Некорректная дата', 'danger')
            return redirect(url_for('schedule.edit_lesson', lesson_id=lesson_id))

        # Задача 4: дата должна входить в текущий учебный год.
        if not _date_in_current_year(date):
            start, end = _current_year_range()
            flash(f'Дата вне текущего учебного года ({start} … {end})', 'danger')
            return redirect(url_for('schedule.edit_lesson', lesson_id=lesson_id))

        if not pair_number or pair_number < 1:
            flash('Некорректный номер пары', 'danger')
            return redirect(url_for('schedule.edit_lesson', lesson_id=lesson_id))
        if not group_id or not subject_id:
            flash('Выберите группу и предмет', 'danger')
            return redirect(url_for('schedule.edit_lesson', lesson_id=lesson_id))

        ok, msg = ScheduleLesson.update(
            lesson_id,
            date=date,
            pair_number=pair_number,
            time_start=time_start,
            time_end=time_end,
            group_id=group_id,
            subject_id=subject_id,
            teacher_id=teacher_id,
            room_id=room_id,
            lesson_type=lesson_type,
        )

        if ok:
            log_activity(
                uid, 'edit_schedule_lesson',
                f'Изменено занятие расписания #{lesson_id} ({date}, пара {pair_number})',
                'schedule_lesson', lesson_id,
            )
            flash(msg, 'success')
            return redirect(url_for('schedule.index', view='day', date=date))

        flash(msg, 'danger')
        return redirect(url_for('schedule.edit_lesson', lesson_id=lesson_id))

    groups = Group.get_all()
    subjects = Subject.get_all()
    teachers = Teacher.get_all()
    rooms = Room.get_all()
    year_start, year_end = _current_year_range()

    return render_template(
        'schedule/edit_lesson.html',
        lesson=lesson,
        groups=groups,
        subjects=subjects,
        teachers=teachers,
        rooms=rooms,
        lesson_types=_get_lesson_types(),
        is_admin=is_admin,
        my_teacher_id=my_teacher_id,
        year_start=year_start,
        year_end=year_end,
    )


@schedule_bp.route('/lesson/<int:lesson_id>/delete', methods=['POST'])
@login_required
def delete_lesson(lesson_id):
    uid = session['user_id']

    lesson = ScheduleLesson.get_by_id(lesson_id)
    if not lesson:
        flash('Занятие не найдено', 'danger')
        return redirect(url_for('schedule.index'))

    if not _can_edit_lesson(uid, lesson):
        flash('Недостаточно прав для удаления этого занятия', 'danger')
        return redirect(url_for('schedule.index'))

    date = lesson['date']
    ok, msg = ScheduleLesson.delete(lesson_id)

    if ok:
        log_activity(
            uid, 'delete_schedule_lesson',
            f'Удалено занятие расписания #{lesson_id} ({date})',
            'schedule_lesson', lesson_id,
        )

    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.index', view='day', date=date))


# ============================================================
#                 СОЗДАНИЕ ВРУЧНУЮ
# ============================================================

@schedule_bp.route('/lesson/new', methods=['GET', 'POST'])
@login_required
def new_lesson():
    uid = session['user_id']

    if not _can_edit_schedule(uid):
        flash('Недостаточно прав для создания занятия', 'danger')
        return redirect(url_for('schedule.index'))

    is_admin = Permission.has_permission(uid, 'manage_users')
    my_teacher_id = None

    if not is_admin:
        teacher_id, was_created, err = User.find_or_create_teacher(uid)
        if err:
            flash(err, 'warning')
        else:
            my_teacher_id = teacher_id
            if was_created:
                flash(
                    'Преподаватель создан автоматически из вашего профиля. '
                    'Проверьте ФИО в справочнике преподавателей.',
                    'info'
                )
    else:
        my_teacher_id = User.get_teacher_id(uid)

    year_start, year_end = _current_year_range()

    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        pair_number = request.form.get('pair_number', type=int)
        time_start = request.form.get('time_start', '').strip()
        time_end = request.form.get('time_end', '').strip()
        group_id = request.form.get('group_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        room_id = request.form.get('room_id', type=int) or None
        lesson_type = request.form.get('lesson_type', 'lecture')

        # Задача 3: не-админ не может поставить чужого.
        if is_admin:
            teacher_id = request.form.get('teacher_id', type=int) or None
        else:
            teacher_id = my_teacher_id

        if not date or not _parse_date(date):
            flash('Некорректная дата', 'danger')
            return redirect(url_for('schedule.new_lesson'))

        # Задача 4: дата в текущем учебном году.
        if not _date_in_current_year(date):
            flash(f'Дата вне текущего учебного года ({year_start} … {year_end})', 'danger')
            return redirect(url_for('schedule.new_lesson'))

        if not pair_number or pair_number < 1:
            flash('Некорректный номер пары', 'danger')
            return redirect(url_for('schedule.new_lesson'))
        if not group_id or not subject_id:
            flash('Выберите группу и предмет', 'danger')
            return redirect(url_for('schedule.new_lesson'))

        year = AcademicYear.get_current()
        if not year:
            flash('Не найден текущий учебный год', 'danger')
            return redirect(url_for('schedule.index'))

        ok, msg, new_id = ScheduleLesson.create(
            academic_year_id=year['id'],
            date=date,
            pair_number=pair_number,
            time_start=time_start,
            time_end=time_end,
            group_id=group_id,
            subject_id=subject_id,
            teacher_id=teacher_id,
            room_id=room_id,
            lesson_type=lesson_type,
        )

        if ok:
            log_activity(
                uid, 'add_schedule_lesson',
                f'Добавлено занятие расписания ({date}, пара {pair_number})',
                'schedule_lesson', new_id,
            )
            flash(msg, 'success')
            return redirect(url_for('schedule.index', view='day', date=date))

        flash(msg, 'danger')
        return redirect(url_for('schedule.new_lesson'))

    groups = Group.get_all()
    subjects = Subject.get_all()
    teachers = Teacher.get_all()
    rooms = Room.get_all()
    default_date = _parse_date(request.args.get('date'), _today_str())
    default_group_id = request.args.get('group_id', type=int)

    return render_template(
        'schedule/edit_lesson.html',
        lesson=None,
        default_date=default_date,
        default_group_id=default_group_id,
        groups=groups,
        subjects=subjects,
        teachers=teachers,
        rooms=rooms,
        lesson_types=_get_lesson_types(),
        is_admin=is_admin,
        my_teacher_id=my_teacher_id,
        year_start=year_start,
        year_end=year_end,
    )


# ============================================================
#                 СВОБОДНЫЕ АУДИТОРИИ
# ============================================================

@schedule_bp.route('/free-rooms')
@permission_required('view_journals')
def free_rooms():
    date_str = _parse_date(request.args.get('date'), _today_str())
    time_start = request.args.get('time_start', '').strip()
    time_end = request.args.get('time_end', '').strip()

    rooms = []
    if time_start and time_end:
        rooms = ScheduleLesson.get_free_rooms_now(date_str, time_start, time_end)

    return render_template(
        'schedule/free_rooms.html',
        date=date_str,
        time_start=time_start,
        time_end=time_end,
        rooms=rooms,
        all_rooms=Room.get_all(),
    )


# ============================================================
#                 API: JSON ДЛЯ AJAX
# ============================================================

@schedule_bp.route('/api/day')
@permission_required('view_journals')
def api_day():
    date_str = _parse_date(request.args.get('date'), _today_str())
    uid = session['user_id']
    filters = _get_filters(uid=uid)

    lessons = ScheduleLesson.get_for_date(
        date_str,
        group_id=filters['group_id'],
        teacher_id=filters['teacher_id'],
        room_id=filters['room_id'],
    )

    return jsonify({
        'success': True,
        'date': date_str,
        'lessons': [dict(l) for l in lessons],
    })


@schedule_bp.route('/api/week')
@permission_required('view_journals')
def api_week():
    date_str = _parse_date(request.args.get('date'), _today_str())
    monday = _week_start(date_str)
    week, start, end = ScheduleLesson.get_week(monday)

    return jsonify({
        'success': True,
        'week_start': start.isoformat(),
        'week_end': end.isoformat(),
        'days': {d: [dict(l) for l in lessons] for d, lessons in week.items()},
    })


@schedule_bp.route('/api/teachers/search')
@permission_required('view_journals')
def api_teachers_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'success': True, 'items': []})

    rows = Teacher.search(q, limit=20)
    return jsonify({
        'success': True,
        'items': [
            {'id': r['id'], 'full_name': r['full_name'], 'short_name': r['short_name']}
            for r in rows
        ],
    })


@schedule_bp.route('/api/rooms/search')
@permission_required('view_journals')
def api_rooms_search():
    q = request.args.get('q', '').strip().lower()
    rooms = Room.get_all()
    if q:
        rooms = [r for r in rooms if q in (r['name'] or '').lower()
                 or q in (r['building'] or '').lower()]

    return jsonify({
        'success': True,
        'items': [
            {'id': r['id'], 'name': r['name'], 'building': r['building']}
            for r in rooms
        ],
    })


@schedule_bp.route('/api/free-rooms')
@permission_required('view_journals')
def api_free_rooms():
    date_str = _parse_date(request.args.get('date'), _today_str())
    time_start = request.args.get('time_start', '').strip()
    time_end = request.args.get('time_end', '').strip()

    if not time_start or not time_end:
        return jsonify({'success': False, 'message': 'Укажите время'}), 400

    rooms = ScheduleLesson.get_free_rooms_now(date_str, time_start, time_end)
    return jsonify({
        'success': True,
        'date': date_str,
        'time_start': time_start,
        'time_end': time_end,
        'rooms': [dict(r) for r in rooms],
    })


# ============================================================
#                 СПРАВОЧНИКИ
# ============================================================

@schedule_bp.route('/teachers')
@permission_required('manage_users')
def teachers_list():
    teachers = Teacher.get_all(active_only=False)
    return render_template('schedule/teachers.html', teachers=teachers)


@schedule_bp.route('/teachers/add', methods=['POST'])
@permission_required('manage_users')
def teacher_add():
    full_name = request.form.get('full_name', '').strip()
    short_name = request.form.get('short_name', '').strip() or None

    if not full_name:
        flash('Введите ФИО', 'danger')
        return redirect(url_for('schedule.teachers_list'))

    ok, msg, new_id = Teacher.create(full_name, short_name)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.teachers_list'))


@schedule_bp.route('/teachers/<int:tid>/edit', methods=['POST'])
@permission_required('manage_users')
def teacher_edit(tid):
    full_name = request.form.get('full_name', '').strip()
    short_name = request.form.get('short_name', '').strip() or None
    is_active = 1 if request.form.get('is_active') else 0

    ok, msg = Teacher.update(tid, full_name, short_name, is_active)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.teachers_list'))


@schedule_bp.route('/teachers/<int:tid>/delete', methods=['POST'])
@permission_required('manage_users')
def teacher_delete(tid):
    ok, msg = Teacher.delete(tid)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.teachers_list'))


@schedule_bp.route('/rooms')
@permission_required('manage_users')
def rooms_list():
    rooms = Room.get_all()
    return render_template('schedule/rooms.html', rooms=rooms)


@schedule_bp.route('/rooms/add', methods=['POST'])
@permission_required('manage_users')
def room_add():
    name = request.form.get('name', '').strip()
    building = request.form.get('building', '').strip() or None
    capacity = request.form.get('capacity', type=int) or None
    room_type = request.form.get('room_type', 'classroom')

    if not name:
        flash('Введите название', 'danger')
        return redirect(url_for('schedule.rooms_list'))

    ok, msg, new_id = Room.create(name, building, capacity, room_type)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.rooms_list'))


@schedule_bp.route('/rooms/<int:rid>/edit', methods=['POST'])
@permission_required('manage_users')
def room_edit(rid):
    name = request.form.get('name', '').strip()
    building = request.form.get('building', '').strip() or None
    capacity = request.form.get('capacity', type=int) or None
    room_type = request.form.get('room_type', 'classroom')

    ok, msg = Room.update(rid, name, building, capacity, room_type)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.rooms_list'))


@schedule_bp.route('/rooms/<int:rid>/delete', methods=['POST'])
@permission_required('manage_users')
def room_delete(rid):
    ok, msg = Room.delete(rid)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.rooms_list'))


@schedule_bp.route('/aliases')
@permission_required('manage_users')
def aliases_list():
    aliases = GroupAlias.get_all()
    groups = Group.get_all()
    return render_template('schedule/aliases.html', aliases=aliases, groups=groups)


@schedule_bp.route('/aliases/add', methods=['POST'])
@permission_required('manage_users')
def alias_add():
    group_id = request.form.get('group_id', type=int)
    alias = request.form.get('alias', '').strip()

    if not group_id or not alias:
        flash('Выберите группу и введите алиас', 'danger')
        return redirect(url_for('schedule.aliases_list'))

    ok, msg, new_id = GroupAlias.add(group_id, alias)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.aliases_list'))


@schedule_bp.route('/aliases/<int:alias_id>/delete', methods=['POST'])
@permission_required('manage_users')
def alias_delete(alias_id):
    ok, msg = GroupAlias.delete(alias_id)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.aliases_list'))


# ============================================================
#                 ИМПОРТ PDF
# ============================================================

def _resolve_group_choice(raw_name):
    """
    Определяет, какой group_id соответствует распознанному имени.
    Возвращает (group_id, display_name) или (None, raw_name).
    Логика:
      1. Алиас → group_id
      2. Точное имя (без регистра) → group_id
      3. None
    """
    if not raw_name:
        return None, ''
    gid = GroupAlias.resolve(raw_name)
    if gid:
        return gid, raw_name
    grp = Group.get_by_name(raw_name)
    if grp:
        return grp['id'], raw_name
    return None, raw_name


def _resolve_subject_choice(raw_name):
    """
    Аналогично для предмета.
    """
    if not raw_name:
        return None, ''
    subj = Subject.get_by_name(raw_name)
    if subj:
        return subj['id'], raw_name
    return None, raw_name


@schedule_bp.route('/upload', methods=['GET', 'POST'])
@permission_required('add_journal')
def upload_pdf():
    if request.method == 'GET':
        return render_template(
            'schedule/upload.html',
            step='upload',
            current_year=datetime.now().year,
        )

    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('schedule.upload_pdf'))

    file = request.files['file']
    if not file.filename:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('schedule.upload_pdf'))

    if not file.filename.lower().endswith('.pdf'):
        flash('Поддерживаются только PDF-файлы', 'danger')
        return redirect(url_for('schedule.upload_pdf'))

    teacher_pattern = (request.form.get('teacher_pattern') or r'.+').strip()
    year = request.form.get('year', type=int) or datetime.now().year

    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'schedules')
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    uniq = _uuid.uuid4().hex[:8]
    pdf_path = os.path.join(upload_dir, f"{timestamp}_{uniq}_{safe_name}")
    file.save(pdf_path)

    try:
        from parsers.pdf_schedule import parse_schedule
        lessons = parse_schedule(pdf_path, teacher_pattern)
    except Exception as e:
        flash(f'Ошибка парсинга: {e}', 'danger')
        return redirect(url_for('schedule.upload_pdf'))

    if not lessons:
        flash('Ничего не найдено по заданному шаблону. '
              'Попробуйте изменить regex ФИО (например, ".+" для всех).',
              'warning')
        return redirect(url_for('schedule.upload_pdf'))

    # Задача 2: готовим варианты выбора для каждой строки.
    all_groups = Group.get_all()
    all_subjects = Subject.get_all()

    # Для каждой строки: какой group_id/subject_id выбран по умолчанию.
    # -1 — «Создать новое» (когда не нашли).
    preview_rows = []
    for i, l in enumerate(lessons):
        gid, gname_raw = _resolve_group_choice(l.get('group'))
        sid, sname_raw = _resolve_subject_choice(l.get('subject'))

        preview_rows.append({
            'index': i,
            'raw': l,
            'group_choice': gid if gid else -1,      # -1 = создать новое
            'subject_choice': sid if sid else -1,
            'group_raw': gname_raw,
            'subject_raw': sname_raw,
        })

    preview_id = str(_uuid.uuid4())
    _register_preview(preview_id, {
        'lessons': lessons,
        'filename': safe_name,
        'teacher_pattern': teacher_pattern,
        'year': year,
        'pdf_path': pdf_path,
    })

    groups_recognized = sorted({l['group'] for l in lessons if l.get('group')})
    teachers_recognized = sorted({l['teacher'] for l in lessons if l.get('teacher')})
    subjects_recognized = sorted({l['subject'] for l in lessons if l.get('subject')})

    return render_template(
        'schedule/upload.html',
        step='preview',
        preview_id=preview_id,
        preview_rows=preview_rows,
        all_groups=all_groups,
        all_subjects=all_subjects,
        filename=safe_name,
        teacher_pattern=teacher_pattern,
        year=year,
        groups=groups_recognized,
        teachers=teachers_recognized,
        subjects=subjects_recognized,
    )


@schedule_bp.route('/import/commit', methods=['POST'])
@permission_required('add_journal')
def import_commit():
    preview_id = request.form.get('preview_id')
    if not preview_id or preview_id not in _import_previews:
        flash('Предпросмотр устарел, загрузите PDF заново', 'danger')
        return redirect(url_for('schedule.upload_pdf'))

    preview = _import_previews[preview_id]
    lessons = preview['lessons']
    year = preview['year']

    # Какие строки выбраны (галочка)
    selected_indices = set()
    for key in request.form:
        if key.startswith('lesson_') and key.count('_') == 1:
            try:
                selected_indices.add(int(key.replace('lesson_', '')))
            except ValueError:
                pass

    current_year = AcademicYear.get_current()
    if not current_year:
        flash('Не найден текущий учебный год', 'danger')
        return redirect(url_for('schedule.upload_pdf'))

    academic_year_id = current_year['id']

    stats = {
        'created': 0,
        'skipped': 0,
        'errors': [],
        'new_groups': 0,
        'new_subjects': 0,
        'new_teachers': 0,
        'new_rooms': 0,
    }

    conn = get_db()

    for i, lesson in enumerate(lessons):
        if selected_indices and i not in selected_indices:
            # пользователь снял галочку — пропускаем
            continue

        try:
            # ---- Группа: читаем выбор пользователя ----
            group_choice = request.form.get(f'group_choice_{i}', '').strip()
            if group_choice == '__skip__':
                stats['skipped'] += 1
                continue

            group_name = lesson.get('group')
            if group_choice == '__new__' or not group_choice:
                if not group_name:
                    stats['skipped'] += 1
                    continue
                grp = Group.get_by_name(group_name)
                if not grp:
                    ok, _, new_id = Group.create(group_name)
                    if ok:
                        group_id = new_id
                        stats['new_groups'] += 1
                    else:
                        stats['errors'].append(
                            f"Не удалось создать группу «{group_name}»"
                        )
                        continue
                else:
                    group_id = grp['id']
            else:
                try:
                    group_id = int(group_choice)
                except (ValueError, TypeError):
                    stats['skipped'] += 1
                    continue
                if not Group.get_by_id(group_id):
                    stats['errors'].append(f'Группа #{group_id} не найдена')
                    continue

            # ---- Предмет: читаем выбор ----
            subject_choice = request.form.get(f'subject_choice_{i}', '').strip()
            if subject_choice == '__skip__':
                stats['skipped'] += 1
                continue

            subject_name = lesson.get('subject') or 'Без названия'
            if subject_choice == '__new__' or not subject_choice:
                subj = Subject.get_by_name(subject_name)
                if not subj:
                    ok, _, new_id = Subject.create(subject_name)
                    if ok:
                        subject_id = new_id
                        stats['new_subjects'] += 1
                    else:
                        stats['errors'].append(
                            f"Не удалось создать предмет «{subject_name}»"
                        )
                        continue
                else:
                    subject_id = subj['id']
            else:
                try:
                    subject_id = int(subject_choice)
                except (ValueError, TypeError):
                    stats['skipped'] += 1
                    continue
                if not Subject.get_by_id(subject_id):
                    stats['errors'].append(f'Предмет #{subject_id} не найден')
                    continue

            # ---- Преподаватель ----
            teacher_id, raw_name, was_created, matched = Teacher.find_or_create(
                lesson.get('teacher')
            )
            if was_created:
                stats['new_teachers'] += 1

            # ---- Аудитория ----
            room_id = None
            room_name = lesson.get('room')
            if room_name:
                existing_room = Room.get_by_name(room_name)
                if not existing_room:
                    room_id = Room.find_or_create(room_name)
                    if room_id:
                        stats['new_rooms'] += 1
                else:
                    room_id = existing_room['id']

            # ---- Дата / время ----
            date_str = lesson.get('date')
            if not date_str:
                stats['skipped'] += 1
                continue
            try:
                dd, mm = date_str.split('.')
                date_iso = f"{year}-{mm.zfill(2)}-{dd.zfill(2)}"
                datetime.strptime(date_iso, '%Y-%m-%d')
            except (ValueError, AttributeError):
                stats['errors'].append(f"Некорректная дата «{date_str}»")
                continue

            # Задача 4: в текущем учебном году?
            if not _date_in_current_year(date_iso):
                stats['skipped'] += 1
                continue

            time_str = lesson.get('time')
            if not time_str:
                stats['skipped'] += 1
                continue
            try:
                start, end = time_str.split('-')
                time_start = start.strip()
                time_end = end.strip()
            except ValueError:
                stats['errors'].append(f"Некорректное время «{time_str}»")
                continue

            pair_number = lesson.get('pair') or 1

            lesson_type = 'lecture'
            subj_lower = (subject_name or '').lower()
            if 'с/р' in subj_lower or 'самост' in subj_lower:
                lesson_type = 'independent'
            elif 'экзамен' in subj_lower:
                lesson_type = 'exam'

            exists = conn.execute('''
                SELECT id FROM schedule_lessons
                WHERE date = ? AND pair_number = ? AND group_id = ?
                  AND subject_id = ?
            ''', (date_iso, pair_number, group_id, subject_id)).fetchone()
            if exists:
                stats['skipped'] += 1
                continue

            ok, msg, new_id = ScheduleLesson.create(
                academic_year_id=academic_year_id,
                date=date_iso,
                pair_number=pair_number,
                time_start=time_start,
                time_end=time_end,
                group_id=group_id,
                subject_id=subject_id,
                teacher_id=teacher_id,
                teacher_name_raw=raw_name,
                room_id=room_id,
                room_name_raw=room_name,
                lesson_type=lesson_type,
                original_group_name=group_name,
                source_file=preview['filename'],
            )
            if ok:
                stats['created'] += 1
            else:
                stats['errors'].append(msg)

        except Exception as e:
            stats['errors'].append(f"Ошибка на записи {i}: {e}")

    # Финальный commit — раньше было внутри finally, но теперь
    # соединение живёт до конца запроса, так что коммитим прямо здесь.
    try:
        conn.commit()
    except Exception as e:
        print(f"[import_commit] Ошибка commit: {e}")

    log_activity(
        session['user_id'], 'import_schedule',
        f'Импорт расписания из PDF «{preview["filename"]}»: '
        f'создано {stats["created"]}, пропущено {stats["skipped"]}, '
        f'ошибок {len(stats["errors"])}',
        'schedule_lesson', None,
    )

    _import_previews.pop(preview_id, None)

    parts = [f'Создано: {stats["created"]}']
    if stats['skipped']:
        parts.append(f'пропущено: {stats["skipped"]}')
    if stats['new_groups']:
        parts.append(f'новых групп: {stats["new_groups"]}')
    if stats['new_subjects']:
        parts.append(f'новых предметов: {stats["new_subjects"]}')
    if stats['new_teachers']:
        parts.append(f'новых преподавателей: {stats["new_teachers"]}')
    if stats['new_rooms']:
        parts.append(f'новых аудиторий: {stats["new_rooms"]}')
    if stats['errors']:
        parts.append(f'ошибок: {len(stats["errors"])}')

    flash(' • '.join(parts),
          'success' if stats['created'] > 0 else 'warning')

    if stats['errors']:
        for err in stats['errors'][:5]:
            flash(err, 'warning')

    return redirect(url_for('schedule.index'))


# ============================================================
#                 РАСПИСАНИЕ ГРУППЫ
# ============================================================

def _academic_weeks(academic_year, max_weeks=36):
    if not academic_year:
        return []
    try:
        start = datetime.strptime(academic_year['start_date'], '%Y-%m-%d').date()
        end = datetime.strptime(academic_year['end_date'], '%Y-%m-%d').date()
    except (ValueError, TypeError, KeyError):
        return []

    start = start - timedelta(days=start.weekday())

    weeks = []
    current = start
    number = 1

    while current <= end and number <= max_weeks:
        week_end = current + timedelta(days=6)
        weeks.append({
            'number': number,
            'start': current.isoformat(),
            'end': week_end.isoformat(),
            'label': (
                f"Неделя {number}: "
                f"{current.strftime('%d.%m')} — {week_end.strftime('%d.%m')}"
            ),
        })
        current += timedelta(days=7)
        number += 1

    return weeks


def _current_week_number(academic_year):
    if not academic_year:
        return None
    try:
        start = datetime.strptime(academic_year['start_date'], '%Y-%m-%d').date()
    except (ValueError, TypeError, KeyError):
        return None

    start = start - timedelta(days=start.weekday())
    today = datetime.now().date()
    delta_days = (today - start).days
    if delta_days < 0:
        return 1
    return delta_days // 7 + 1


@schedule_bp.route('/group/<int:group_id>')
@permission_required('view_journals')
def group_schedule(group_id):
    uid = session['user_id']

    group = Group.get_by_id(group_id)
    if not group:
        flash('Группа не найдена', 'danger')
        return redirect(url_for('schedule.index'))

    academic_year = AcademicYear.get_current()
    weeks = _academic_weeks(academic_year, max_weeks=36)

    week_number = request.args.get('week', type=int)
    date_param = request.args.get('date', '').strip()

    if not week_number and date_param:
        try:
            d = datetime.strptime(date_param, '%Y-%m-%d').date()
            for w in weeks:
                ws = datetime.strptime(w['start'], '%Y-%m-%d').date()
                we = datetime.strptime(w['end'], '%Y-%m-%d').date()
                if ws <= d <= we:
                    week_number = w['number']
                    break
        except (ValueError, TypeError):
            pass

    if not week_number:
        week_number = _current_week_number(academic_year) or 1

    week = None
    for w in weeks:
        if w['number'] == week_number:
            week = w
            break

    if not week:
        week = weeks[0] if weeks else {
            'number': 1,
            'start': datetime.now().date().isoformat(),
            'end': (datetime.now().date() + timedelta(days=6)).isoformat(),
            'label': 'Текущая неделя',
        }

    monday = week['start']
    week_data, start, end = ScheduleLesson.get_week(monday)

    group_lessons_by_date = {}
    for d, lessons in week_data.items():
        group_lessons_by_date[d] = [
            l for l in lessons if l['group_id'] == group_id
        ]

    days = []
    day_names = ScheduleLesson.DAY_NAMES_SHORT
    day_names_full = ScheduleLesson.DAY_NAMES_FULL

    current = datetime.strptime(week['start'], '%Y-%m-%d').date()
    for i in range(6):
        d = current + timedelta(days=i)
        ds = d.isoformat()
        lessons = sorted(
            group_lessons_by_date.get(ds, []),
            key=lambda l: (l['pair_number'], l['time_start'])
        )
        days.append({
            'date': ds,
            'date_short': d.strftime('%d.%m'),
            'date_full': d.strftime('%d.%m.%Y'),
            'day_short': day_names[i],
            'day_full': day_names_full[i],
            'is_today': d == datetime.now().date(),
            'lessons': lessons,
        })

    prev_week_number = week_number - 1 if week_number > 1 else None
    next_week_number = week_number + 1 if week_number < len(weeks) else None

    my_teacher_id = User.get_teacher_id(uid)
    can_edit_any = _can_edit_schedule(uid)

    return render_template(
        'schedule/group.html',
        group=group,
        academic_year=academic_year,
        weeks=weeks,
        week=week,
        week_number=week_number,
        days=days,
        prev_week_number=prev_week_number,
        next_week_number=next_week_number,
        can_edit_any=can_edit_any,
        my_teacher_id=my_teacher_id,
    )