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


# ============================================================
#                 ПРОВЕРКА ДОСТУПА К ЗАНЯТИЮ
# ============================================================

def _can_edit_schedule(uid):
    """Может ли пользователь редактировать занятия вообще."""
    return (
        Permission.has_permission(uid, 'manage_users')
        or Permission.has_permission(uid, 'edit_schedule')
    )


def _can_edit_lesson(uid, lesson):
    """
    Может ли пользователь редактировать ЭТО занятие.
    Админ — всегда, преподаватель — только своё.
    lesson — sqlite3.Row или dict с полем 'teacher_id'.
    """
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


def _get_filters():
    return {
        'group_id': request.args.get('group_id', type=int),
        'teacher_id': request.args.get('teacher_id', type=int),
        'room_id': request.args.get('room_id', type=int),
    }


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
    filters = _get_filters()

    groups = Group.get_all()
    teachers = Teacher.get_all()
    rooms = Room.get_all()

    uid = session['user_id']
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

        if is_admin:
            teacher_id = request.form.get('teacher_id', type=int) or None
        else:
            teacher_id = my_teacher_id

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

        if is_admin:
            teacher_id = request.form.get('teacher_id', type=int) or None
        else:
            teacher_id = my_teacher_id
            if not teacher_id:
                flash(
                    'Ваш профиль не связан с преподавателем. '
                    'Обратитесь к администратору — без этой связи '
                    'нельзя добавить занятие.',
                    'danger'
                )
                return redirect(url_for('schedule.index'))

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

    return render_template(
        'schedule/edit_lesson.html',
        lesson=None,
        default_date=default_date,
        groups=groups,
        subjects=subjects,
        teachers=teachers,
        rooms=rooms,
        lesson_types=_get_lesson_types(),
        is_admin=is_admin,
        my_teacher_id=my_teacher_id,
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


# ============================================================
#                 ИМПОРТ PDF
# ============================================================

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
    pdf_path = os.path.join(upload_dir, f"{timestamp}_{safe_name}")
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

    preview_id = str(_uuid.uuid4())
    _import_previews[preview_id] = {
        'lessons': lessons,
        'filename': safe_name,
        'teacher_pattern': teacher_pattern,
        'year': year,
        'pdf_path': pdf_path,
    }

    groups = sorted({l['group'] for l in lessons if l.get('group')})
    teachers = sorted({l['teacher'] for l in lessons if l.get('teacher')})
    subjects = sorted({l['subject'] for l in lessons if l.get('subject')})

    return render_template(
        'schedule/upload.html',
        step='preview',
        preview_id=preview_id,
        lessons=lessons,
        filename=safe_name,
        teacher_pattern=teacher_pattern,
        year=year,
        groups=groups,
        teachers=teachers,
        subjects=subjects,
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

    selected_indices = set()
    for key in request.form:
        if key.startswith('lesson_'):
            try:
                selected_indices.add(int(key.replace('lesson_', '')))
            except ValueError:
                pass

    if selected_indices:
        lessons = [l for i, l in enumerate(lessons) if i in selected_indices]

    if not lessons:
        flash('Не выбрано ни одного занятия', 'warning')
        return redirect(url_for('schedule.upload_pdf'))

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
    try:
        for lesson in lessons:
            try:
                group_name = lesson.get('group')
                if not group_name:
                    stats['skipped'] += 1
                    continue

                group_id = GroupAlias.resolve(group_name)
                if not group_id:
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

                subject_name = lesson.get('subject') or 'Без названия'
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

                teacher_id, raw_name, was_created, matched = Teacher.find_or_create(
                    lesson.get('teacher')
                )
                if was_created:
                    stats['new_teachers'] += 1

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
                subj_lower = subject_name.lower()
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
                stats['errors'].append(f"Ошибка на записи: {e}")

        conn.commit()
    finally:
        conn.close()

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