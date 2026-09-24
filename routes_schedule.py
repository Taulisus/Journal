"""
Blueprint для расписания.
Префикс: /schedule
"""

from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session,
)

from decorators import login_required, permission_required
from models import Group, Subject, get_db, Permission
from models_schedule import (
    ScheduleLesson, Teacher, Room, AcademicYear, GroupAlias,
)


schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')


# ============================================================
#                 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _parse_date(value, default=None):
    """Парсит YYYY-MM-DD, возвращает строку или default."""
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
    """Возвращает понедельник недели, в которую входит date_str."""
    if not date_str:
        date_str = _today_str()
    dt = datetime.strptime(date_str, '%Y-%m-%d').date()
    monday = dt - timedelta(days=dt.weekday())
    return monday.isoformat()


def _get_filters():
    """Общие фильтры из query-параметров."""
    return {
        'group_id': request.args.get('group_id', type=int),
        'teacher_id': request.args.get('teacher_id', type=int),
        'room_id': request.args.get('room_id', type=int),
    }


def _week_days(monday_str):
    """
    Возвращает список из 7 дат (строк) начиная с понедельника.
    """
    monday = datetime.strptime(monday_str, '%Y-%m-%d').date()
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


def _day_label(date_str):
    """'2026-09-21' -> ('21.09.2026', 'Пн', 'Понедельник')"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    short = ScheduleLesson.DAY_NAMES_SHORT[dt.weekday()]
    full = ScheduleLesson.DAY_NAMES_FULL[dt.weekday()]
    return dt.strftime('%d.%m.%Y'), short, full


# ============================================================
#                 ГЛАВНАЯ СТРАНИЦА РАСПИСАНИЯ
# ============================================================

@schedule_bp.route('/')
@permission_required('view_journals')
def index():
    """
    Просмотр расписания на день или неделю.
    Query: ?view=day|week&date=YYYY-MM-DD&group_id=N&teacher_id=N&room_id=N
    """
    view = request.args.get('view', 'day')
    if view not in ('day', 'week'):
        view = 'day'

    date_str = _parse_date(request.args.get('date'), _today_str())
    filters = _get_filters()

    groups = Group.get_all()
    teachers = Teacher.get_all()
    rooms = Room.get_all()

    context = {
        'view': view,
        'date': date_str,
        'filters': filters,
        'groups': groups,
        'teachers': teachers,
        'rooms': rooms,
    }

    if view == 'week':
        monday = _week_start(date_str)
        week, start, end = ScheduleLesson.get_week(monday)

        # Строим удобную структуру: {date_str: {'label': ..., 'lessons': [...]}}
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

        label, short, full = _day_label(date_str)
        context.update({
            'lessons': lessons,
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


# ============================================================
#                 СЕГОДНЯ
# ============================================================

@schedule_bp.route('/today')
@permission_required('view_journals')
def today():
    """Редирект на текущую дату в режиме дня."""
    return redirect(url_for(
        'schedule.index',
        view='day',
        date=_today_str(),
        **{k: v for k, v in _get_filters().items() if v},
    ))


# ============================================================
#                 РЕДАКТИРОВАНИЕ
# ============================================================

@schedule_bp.route('/lesson/<int:lesson_id>/edit', methods=['GET', 'POST'])
@permission_required('add_journal')
def edit_lesson(lesson_id):
    lesson = ScheduleLesson.get_by_id(lesson_id)
    if not lesson:
        flash('Занятие не найдено', 'danger')
        return redirect(url_for('schedule.index'))

    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        pair_number = request.form.get('pair_number', type=int)
        time_start = request.form.get('time_start', '').strip()
        time_end = request.form.get('time_end', '').strip()
        group_id = request.form.get('group_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        teacher_id = request.form.get('teacher_id', type=int) or None
        room_id = request.form.get('room_id', type=int) or None
        lesson_type = request.form.get('lesson_type', 'lecture')

        if not date or not _parse_date(date):
            flash('Некорректная дата', 'danger')
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
            from activity import log_activity
            log_activity(
                session['user_id'], 'edit_schedule_lesson',
                f'Изменено занятие расписания #{lesson_id} ({date}, пара {pair_number})',
                'schedule_lesson', lesson_id,
            )
            flash(msg, 'success')
            return redirect(url_for('schedule.index', view='day', date=date))

        flash(msg, 'danger')
        return redirect(url_for('schedule.edit_lesson', lesson_id=lesson_id))

    # GET: показываем форму
    groups = Group.get_all()
    subjects = Subject.get_all()
    teachers = Teacher.get_all()
    rooms = Room.get_all()

    return render_template(
        'schedule/edit_lesson.html',
        lesson=lesson,
        groups=groups,
        subjects=subjects,
        teachers=teachers,
        rooms=rooms,
        lesson_types=[
            ('lecture', 'Лекция'),
            ('practice', 'Практическая'),
            ('independent', 'С/Р'),
            ('dictation', 'Под запись'),
            ('exam', 'Экзамен'),
            ('diff_credit', 'Дифф. зачёт'),
        ],
    )


@schedule_bp.route('/lesson/<int:lesson_id>/delete', methods=['POST'])
@permission_required('add_journal')
def delete_lesson(lesson_id):
    lesson = ScheduleLesson.get_by_id(lesson_id)
    if not lesson:
        flash('Занятие не найдено', 'danger')
        return redirect(url_for('schedule.index'))

    date = lesson['date']
    ok, msg = ScheduleLesson.delete(lesson_id)

    if ok:
        from activity import log_activity
        log_activity(
            session['user_id'], 'delete_schedule_lesson',
            f'Удалено занятие расписания #{lesson_id} ({date})',
            'schedule_lesson', lesson_id,
        )

    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('schedule.index', view='day', date=date))


# ============================================================
#                 СОЗДАНИЕ ВРУЧНУЮ
# ============================================================

@schedule_bp.route('/lesson/new', methods=['GET', 'POST'])
@permission_required('add_journal')
def new_lesson():
    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        pair_number = request.form.get('pair_number', type=int)
        time_start = request.form.get('time_start', '').strip()
        time_end = request.form.get('time_end', '').strip()
        group_id = request.form.get('group_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        teacher_id = request.form.get('teacher_id', type=int) or None
        room_id = request.form.get('room_id', type=int) or None
        lesson_type = request.form.get('lesson_type', 'lecture')

        if not date or not _parse_date(date):
            flash('Некорректная дата', 'danger')
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
            from activity import log_activity
            log_activity(
                session['user_id'], 'add_schedule_lesson',
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

    return render_template(
        'schedule/edit_lesson.html',
        lesson=None,
        default_date=default_date,
        groups=groups,
        subjects=subjects,
        teachers=teachers,
        rooms=rooms,
        lesson_types=[
            ('lecture', 'Лекция'),
            ('practice', 'Практическая'),
            ('independent', 'С/Р'),
            ('dictation', 'Под запись'),
            ('exam', 'Экзамен'),
            ('diff_credit', 'Дифф. зачёт'),
        ],
    )


# ============================================================
#                 СВОБОДНЫЕ АУДИТОРИИ
# ============================================================

@schedule_bp.route('/free-rooms')
@permission_required('view_journals')
def free_rooms():
    """Свободные аудитории на выбранное время."""
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
    """JSON-расписание на день."""
    date_str = _parse_date(request.args.get('date'), _today_str())
    filters = _get_filters()

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
    """JSON-расписание на неделю."""
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
    """Автокомплит по преподавателям."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'success': True, 'items': []})

    rows = Teacher.search(q, limit=20)
    return jsonify({
        'success': True,
        'items': [
            {
                'id': r['id'],
                'full_name': r['full_name'],
                'short_name': r['short_name'],
            }
            for r in rows
        ],
    })


@schedule_bp.route('/api/rooms/search')
@permission_required('view_journals')
def api_rooms_search():
    """Автокомплит по аудиториям."""
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
    """JSON-список свободных аудиторий на указанное время."""
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
    return render_template(
        'schedule/aliases.html',
        aliases=aliases,
        groups=groups,
    )


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