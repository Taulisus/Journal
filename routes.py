from datetime import datetime
import os
import re

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    jsonify, session, Response, send_file,
)

from decorators import login_required, permission_required
from models import (
    Group, Subject, Student, GroupSubject, get_db, UserProfile, Permission, Position,
    TeacherJournal, Curator, TeacherHours, User, SemesterGrade, PositionPermission,
)
from journal_manager import JournalManager
from utils import (
    generate_report_chart,
    create_backup,
)
from config import Config
from stats import (
    get_user_weekly_avg,
    refresh_user_weekly_avg,
    get_teacher_stats,
    get_schedule_avg_per_week,
)
from activity import (
    log_activity,
    get_recent_activity,
    get_activity_filtered,
    get_activity_for_export,
    get_unique_actions,
    get_unique_users,
    get_unique_target_types,
    activity_to_csv,
    get_old_activity_stats,
    clear_old_activity,
)
from models_schedule import (
    ScheduleLesson, Teacher, Room, AcademicYear, GroupAlias,
)
from blueprints._helpers import has_emoji


main_bp = Blueprint('main', __name__)


# ============================================================
#                 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _make_db_backup(prefix='mass_transfer'):
    """Обёртка над utils.create_backup. Возвращает путь или None."""
    ok, path_or_err, _ = create_backup(
        db_path=Config.DATABASE,
        backup_dir=os.path.join(os.path.dirname(Config.DATABASE), 'backups'),
        prefix=prefix,
        max_backups=30,
    )
    return path_or_err if ok else None


def _user_owns_journal(uid, gsid):
    """True, если у пользователя есть manage_users ИЛИ журнал ему назначен."""
    if Permission.has_permission(uid, 'manage_users'):
        return True
    return any(j['id'] == gsid for j in TeacherJournal.get_user_journals(uid))


def _require_journal_access(uid, gsid):
    """Для HTML-роутов. Возвращает None или Response."""
    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Журнал не найден', 'danger')
        return redirect(url_for('journals.index'))
    if not _user_owns_journal(uid, gsid):
        flash('Журнал вам не назначен', 'danger')
        return redirect(url_for('journals.index'))
    return None


def _require_journal_access_json(uid, gsid):
    """Для JSON-эндпоинтов. Возвращает None или (jsonify, status_code)."""
    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        return jsonify({'success': False, 'message': 'Журнал не найден'}), 404
    if not _user_owns_journal(uid, gsid):
        return jsonify({'success': False, 'message': 'Журнал вам не назначен'}), 403
    return None


def _get_week_schedule(uid, monday_str=None):
    """
    Расписание недели для дашборда.
    Если у пользователя есть teacher_id — только его занятия.
    Иначе — все занятия недели.

    Для каждого дня собирает:
      - 'lessons'          — плоский список (для AJAX и на будущее),
      - 'lessons_by_pair'  — dict {pair_number: lesson}, чтобы шаблон
                             мог напрямую доставать пару по номеру 1..7.
    """
    from datetime import datetime, timedelta

    if monday_str:
        try:
            monday = datetime.strptime(monday_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            monday = datetime.now().date()
    else:
        monday = datetime.now().date()

    monday = monday - timedelta(days=monday.weekday())

    teacher_id = None
    try:
        teacher_id = User.get_teacher_id(uid)
    except Exception:
        teacher_id = None

    week, start, end = ScheduleLesson.get_week(monday)

    if teacher_id:
        filtered = {}
        for d, lessons in week.items():
            filtered[d] = [l for l in lessons if l['teacher_id'] == teacher_id]
        week = filtered

    days = []
    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']
    for i in range(6):
        d = monday + timedelta(days=i)
        ds = d.isoformat()
        lessons = week.get(ds, [])
        lessons = sorted(lessons, key=lambda l: (l['pair_number'], l['time_start']))

        # Раскладываем занятия по номеру пары (1..7).
        # Это позволяет шаблону просто итерироваться по range(1, 8)
        # без вложенных {% for %} — у Jinja2 есть проблема со scoping,
        # из-за которой {% set %} внутри вложенного цикла не «протекает»
        # во внешний scope.
        lessons_by_pair = {}
        for l in lessons:
            try:
                pair_num = int(l['pair_number'])
            except (TypeError, ValueError, KeyError):
                continue
            # На одну пару должно быть одно занятие; если вдруг несколько —
            # берём первое (обычно так и есть).
            lessons_by_pair.setdefault(pair_num, l)

        days.append({
            'date': ds,
            'date_label': f"{d.day:02d}.{d.month:02d}",
            'day_short': day_names[i],
            'day_full': ScheduleLesson.DAY_NAMES_FULL[i],
            'is_today': d == datetime.now().date(),
            'lessons': lessons,
            'lessons_by_pair': lessons_by_pair,
        })

    return {
        'days': days,
        'week_start': monday.isoformat(),
        'prev_week': (monday - timedelta(days=7)).isoformat(),
        'next_week': (monday + timedelta(days=7)).isoformat(),
        'has_any': any(d['lessons'] for d in days),
    }


def _find_next_lesson(teacher_id):
    """
    Находит ближайшую пару преподавателя (сегодня, начиная с текущего времени).
    Если сегодня больше нет — ищет в следующие 7 дней.
    Возвращает dict или None.

    Дополнительно ищет journal_gsid — id журнала (group_subjects.id),
    соответствующего этой паре (по group_id + subject_id), чтобы можно
    было открыть журнал прямо из виджета.
    """
    from datetime import datetime, timedelta, time as _time

    now = datetime.now()
    today = now.date()
    now_hhmm = now.strftime('%H:%M')

    for offset in range(0, 8):
        d = today + timedelta(days=offset)
        date_str = d.isoformat()

        lessons = ScheduleLesson.get_for_date(date_str, teacher_id=teacher_id)
        if not lessons:
            continue

        def _key(l):
            t = (l['time_start'] or '00:00')[:5]
            return (l['pair_number'] or 0, t)

        lessons = sorted(lessons, key=_key)

        for l in lessons:
            ts = (l['time_start'] or '')[:5]
            te = (l['time_end'] or '')[:5]
            if not ts:
                continue

            if offset == 0:
                if te and te < now_hhmm:
                    continue
                is_now = bool(te) and ts <= now_hhmm <= te
                try:
                    h, m = ts.split(':')
                    start_dt = datetime.combine(today, _time(int(h), int(m)))
                    minutes_until = int((start_dt - now).total_seconds() // 60)
                except (ValueError, TypeError):
                    minutes_until = None

                return {
                    'date': date_str,
                    'time_start': ts,
                    'time_end': te,
                    'pair_number': l['pair_number'],
                    'group_id': l['group_id'],
                    'group_name': l['group_name'],
                    'subject_id': l['subject_id'],
                    'subject_name': l['subject_name'],
                    'room_name': l['room_resolved_name'],
                    'journal_gsid': _find_journal_gsid(l['group_id'], l['subject_id']),
                    'is_today': True,
                    'is_now': is_now,
                    'minutes_until': minutes_until,
                }
            else:
                return {
                    'date': date_str,
                    'time_start': ts,
                    'time_end': te,
                    'pair_number': l['pair_number'],
                    'group_id': l['group_id'],
                    'group_name': l['group_name'],
                    'subject_id': l['subject_id'],
                    'subject_name': l['subject_name'],
                    'room_name': l['room_resolved_name'],
                    'journal_gsid': _find_journal_gsid(l['group_id'], l['subject_id']),
                    'is_today': False,
                    'is_now': False,
                    'minutes_until': None,
                }

    return None


def _find_journal_gsid(group_id, subject_id):
    """
    Находит id журнала (group_subjects.id) для пары (группа, предмет).
    Возвращает id или None.
    """
    if not group_id or not subject_id:
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM group_subjects "
            "WHERE group_id = ? AND subject_id = ? LIMIT 1",
            (group_id, subject_id),
        ).fetchone()
        return row['id'] if row else None
    except Exception:
        return None

def _pick_greeting_name(full_name, username):
    """
    Из ФИО достаём только имя.
    """
    if full_name:
        parts = full_name.split()
        if len(parts) >= 3:
            return parts[1]
        if len(parts) == 2:
            second = parts[1]
            second_low = second.lower()
            if second_low.endswith(('ович', 'евич', 'ич', 'овна', 'евна', 'ична')):
                return parts[0]
            return second
        return parts[0]
    return username or 'пользователь'


# ============================================================
#                 ГЛАВНАЯ
# ============================================================

@main_bp.route('/')
@login_required
def dashboard():
    uid = session['user_id']
    is_admin = Permission.has_permission(uid, 'manage_users')

    current_semester = Config.get_current_semester()
    teacher_id = User.get_teacher_id(uid)

    # --- Приветствие ---
    profile = User.get_profile(uid)
    full_name = (profile.get('full_name') or '').strip() if profile else ''
    username = (profile.get('username') or '') if profile else ''
    greeting_name = _pick_greeting_name(full_name, username)

    now = datetime.now()
    hour = now.hour
    if 5 <= hour < 12:
        greeting_prefix = 'Доброе утро'
    elif 12 <= hour < 18:
        greeting_prefix = 'Добрый день'
    elif 18 <= hour < 23:
        greeting_prefix = 'Добрый вечер'
    else:
        greeting_prefix = 'Доброй ночи'

    _months = [
        'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    ]
    _wdays = ['понедельник', 'вторник', 'среда', 'четверг',
              'пятница', 'суббота', 'воскресенье']
    today_str = f"{_wdays[now.weekday()]}, {now.day} {_months[now.month - 1]} {now.year}"

    # --- Плитки ---
    tiles = []

    if is_admin:
        tiles.append({
            'key': 'groups', 'title': 'Группы',
            'value': len(Group.get_all()),
            'icon': 'bi-people-fill', 'color': 'primary',
            'url': url_for('groups.index'),
        })
        tiles.append({
            'key': 'subjects', 'title': 'Предметы',
            'value': len(Subject.get_all()),
            'icon': 'bi-book-fill', 'color': 'success',
            'url': url_for('subjects.index'),
        })
        tiles.append({
            'key': 'students', 'title': 'Студенты',
            'value': len(Student.get_all()),
            'icon': 'bi-person-lines-fill', 'color': 'info',
            'url': url_for('students.index'),
        })
        tiles.append({
            'key': 'journals', 'title': 'Журналы',
            'value': len(GroupSubject.get_all()),
            'icon': 'bi-journal-text', 'color': 'warning',
            'url': url_for('journals.index'),
        })

        schedule_stat = get_schedule_avg_per_week(teacher_id=teacher_id, weeks=4)
        tiles.append({
            'key': 'schedule', 'title': 'Расписание',
            'value': schedule_stat['avg'], 'suffix': '/нед',
            'icon': 'bi-calendar-week', 'color': 'purple',
            'url': url_for('schedule.index'),
        })

        tiles.append({
            'key': 'teachers', 'title': 'Преподаватели',
            'value': len(Teacher.get_all(active_only=True)),
            'icon': 'bi-person-badge', 'color': 'teal',
            'url': url_for('schedule.teachers_list'),
        })
        tiles.append({
            'key': 'rooms', 'title': 'Аудитории',
            'value': len(Room.get_all()),
            'icon': 'bi-door-open', 'color': 'pink',
            'url': url_for('schedule.rooms_list'),
        })
        tiles.append({
            'key': 'users', 'title': 'Пользователи',
            'value': len(User.get_all()),
            'icon': 'bi-shield-lock', 'color': 'orange',
            'url': url_for('users.index'),
        })
    else:
        my_journals = TeacherJournal.get_user_journals(uid)
        tiles.append({
            'key': 'my_journals', 'title': 'Мои журналы',
            'value': len(my_journals),
            'icon': 'bi-journal-bookmark-fill', 'color': 'primary',
            'url': url_for('journals.index'),
        })

        my_hours = get_teacher_stats(uid, semester=current_semester)
        if my_hours['has_data'] and my_hours['total_planned'] > 0:
            hours_value = f"{my_hours['total_actual']} / {my_hours['total_planned']}"
        else:
            hours_value = '—'
        tiles.append({
            'key': 'my_hours', 'title': 'Мои часы',
            'value': hours_value, 'suffix': 'ч',
            'icon': 'bi-clock-history', 'color': 'success',
            'url': url_for('main.teacher_hours_stats'),
        })

        schedule_stat = get_schedule_avg_per_week(teacher_id=teacher_id, weeks=4)
        tiles.append({
            'key': 'schedule', 'title': 'Расписание',
            'value': schedule_stat['avg'], 'suffix': '/нед',
            'icon': 'bi-calendar-week', 'color': 'info',
            'url': url_for('schedule.index'),
        })

    # --- Расписание недели ---
    week_param = request.args.get('week')
    schedule_week = None
    try:
        schedule_week = _get_week_schedule(uid, week_param)
    except Exception as e:
        print(f"[dashboard] Не удалось получить расписание: {e}")

    # --- Ближайшая пара ---
    next_lesson = None
    if teacher_id:
        try:
            next_lesson = _find_next_lesson(teacher_id)
        except Exception as e:
            print(f"[dashboard] next_lesson: {e}")

    # --- Мои часы ---
    teacher_stats = None
    if is_admin:
        if teacher_id:
            teacher_stats = get_teacher_stats(uid, semester=current_semester)
    else:
        teacher_stats = get_teacher_stats(uid, semester=current_semester)

    if teacher_stats and not teacher_stats['has_data']:
        teacher_stats = None

    # --- Данные для круговой диаграммы: разбивка проведённых часов по журналам ---
    # Цвет сектора = цвет прогресс-бара в «Моих часах» (по проценту выполнения)
    chart_data = []
    if teacher_stats and teacher_stats.get('has_data'):
        for item in teacher_stats['items']:
            actual = item['actual_total']
            if actual <= 0:
                continue

            pct = item['percent']
            if pct >= 100:
                color = '#10b981'   # success — зелёный
            elif pct >= 50:
                color = '#4f46e5'   # primary — индиго
            elif pct >= 25:
                color = '#f59e0b'   # warning — жёлтый
            else:
                color = '#ef4444'   # danger — красный

            chart_data.append({
                'label': f"{item['group_name']} · {item['subject_name']}",
                'value': actual,
                'color': color,
                'planned': item['planned_total'],
                'percent': pct,
            })

        # Добавляем серый сектор «Осталось»
        if teacher_stats['total_remaining'] > 0:
            chart_data.append({
                'label': 'Осталось',
                'value': teacher_stats['total_remaining'],
                'color': '#cbd5e1',
                'planned': 0,
                'percent': 0,
            })

    # --- Последние действия ---
    activity = None
    if is_admin:
        activity = get_recent_activity(limit=10)

    # --- Мини-график посещаемости (админ) ---
    attendance_stats = None
    if is_admin:
        try:
            from stats import get_overall_attendance_stats
            attendance_stats = get_overall_attendance_stats(weeks=8)
        except Exception as e:
            print(f"[dashboard] attendance_stats: {e}")

    return render_template(
        'dashboard.html',
        tiles=tiles,
        is_admin=is_admin,
        schedule_week=schedule_week,
        teacher_stats=teacher_stats,
        chart_data=chart_data,
        activity=activity,
        attendance_stats=attendance_stats,
        next_lesson=next_lesson,
        current_semester=current_semester,
        current_user_teacher_id=teacher_id,
        greeting_prefix=greeting_prefix,
        greeting_name=greeting_name,
        today_str=today_str,
    )

@main_bp.route('/dashboard/week')
@login_required
def dashboard_week():
    """
    JSON для AJAX-перелистывания недель на дашборде.
    Возвращает ту же структуру, что и schedule_week в dashboard().
    """
    uid = session['user_id']
    monday_str = (request.args.get('week') or '').strip() or None

    try:
        data = _get_week_schedule(uid, monday_str)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

    days = []
    for d in data['days']:
        days.append({
            'date': d['date'],
            'date_label': d['date_label'],
            'day_short': d['day_short'],
            'day_full': d['day_full'],
            'is_today': d['is_today'],
            'lessons': [
                {
                    'id': l['id'],
                    'pair_number': l['pair_number'],
                    'time_start': l['time_start'],
                    'time_end': l['time_end'],
                    'group_id': l['group_id'],
                    'group_name': l['group_name'],
                    'subject_name': l['subject_name'],
                    'room_resolved_name': l['room_resolved_name'],
                    'teacher_short_name': l['teacher_short_name'],
                }
                for l in d['lessons']
            ],
        })

    return jsonify({
        'success': True,
        'week_start': data['week_start'],
        'prev_week': data['prev_week'],
        'next_week': data['next_week'],
        'has_any': data['has_any'],
        'days': days,
    })


@main_bp.route('/dashboard/refresh-stats', methods=['POST'])
@login_required
def refresh_stats():
    uid = session['user_id']
    data = refresh_user_weekly_avg(uid, weeks=4)
    return jsonify({'success': True, 'data': data})


# ============================================================
#                 ЛОГ ДЕЙСТВИЙ
# ============================================================

ACTION_LABELS = {
    'login': 'Вход в систему',
    'logout': 'Выход из системы',
    'add_group': 'Создание группы',
    'edit_group': 'Редактирование группы',
    'delete_group': 'Удаление группы',
    'add_subject': 'Создание предмета',
    'edit_subject': 'Редактирование предмета',
    'delete_subject': 'Удаление предмета',
    'add_student': 'Добавление студента',
    'edit_student': 'Редактирование студента',
    'delete_student': 'Удаление студента',
    'import_students': 'Импорт студентов',
    'mass_transfer': 'Массовый перевод студентов',
    'add_journal': 'Создание журнала',
    'delete_journal': 'Удаление журнала',
    'edit_hours': 'Изменение часов',
    'add_lesson': 'Добавление занятия',
    'delete_lesson': 'Удаление занятия',
    'edit_lesson_type': 'Изменение типа занятия',
    'edit_lesson_time': 'Изменение времени занятия',
    'edit_entry': 'Изменение записи',
    'set_semester_grade': 'Оценка за семестр',
    'add_user': 'Создание пользователя',
    'edit_user': 'Редактирование пользователя',
    'delete_user': 'Удаление пользователя',
    'assign_journals': 'Назначение журналов',
    'profile_edit': 'Обновление профиля',
    'password_change': 'Смена пароля',
    'activity_export': 'Экспорт лога',
    'activity_cleanup': 'Очистка лога',
    'edit_role': 'Изменение прав роли',
    'add_schedule_lesson': 'Добавление занятия в расписание',
    'edit_schedule_lesson': 'Изменение занятия в расписании',
    'delete_schedule_lesson': 'Удаление занятия из расписания',
    'import_schedule': 'Импорт расписания из PDF',
    'export_journal': 'Экспорт журнала в Excel',
    'create_backup': 'Создание бэкапа БД',
}

TARGET_TYPE_LABELS = {
    'user': 'Пользователь',
    'group': 'Группа',
    'subject': 'Предмет',
    'student': 'Студент',
    'journal': 'Журнал',
    'lesson': 'Занятие',
    'position': 'Роль',
    'schedule_lesson': 'Занятие расписания',
}


def _parse_activity_filters():
    return {
        'user_id': request.args.get('user_id', type=int),
        'action': (request.args.get('action') or '').strip() or None,
        'target_type': (request.args.get('target_type') or '').strip() or None,
        'date_from': (request.args.get('date_from') or '').strip() or None,
        'date_to': (request.args.get('date_to') or '').strip() or None,
        'search': (request.args.get('search') or '').strip() or None,
    }


@main_bp.route('/activity')
@login_required
def activity_log_page():
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    filters = _parse_activity_filters()

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    if per_page not in (20, 50, 100, 200):
        per_page = 50

    data = get_activity_filtered(filters, page=page, per_page=per_page)

    all_users = get_unique_users()
    all_actions = get_unique_actions()
    all_target_types = get_unique_target_types()

    cleanup_stats = get_old_activity_stats(days=90)

    return render_template(
        'activity.html',
        data=data,
        filters=filters,
        all_users=all_users,
        all_actions=all_actions,
        all_target_types=all_target_types,
        action_labels=ACTION_LABELS,
        target_type_labels=TARGET_TYPE_LABELS,
        cleanup_stats=cleanup_stats,
        per_page=per_page,
    )


@main_bp.route('/activity/export.csv')
@login_required
def activity_export_csv():
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    filters = _parse_activity_filters()
    items = get_activity_for_export(filters, limit=10000)

    csv_content = activity_to_csv(items)
    csv_bytes = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')

    filename = f'activity_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    log_activity(uid, 'activity_export',
                 f'Экспорт лога в CSV ({len(items)} записей)',
                 'user', uid)

    return Response(
        csv_bytes,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        }
    )


@main_bp.route('/activity/cleanup', methods=['POST'])
@login_required
def activity_cleanup():
    uid = session['user_id']
    if not Permission.has_permission(uid, 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.dashboard'))

    days = request.form.get('days', 90, type=int)
    if days not in (30, 60, 90, 180, 365):
        days = 90

    deleted, error = clear_old_activity(days=days)

    if error:
        flash(f'Ошибка очистки: {error}', 'danger')
    elif deleted == 0:
        flash(f'Нет записей старше {days} дней — нечего удалять', 'info')
    else:
        log_activity(uid, 'activity_cleanup',
                     f'Очищено {deleted} записей старше {days} дней',
                     'user', uid)
        flash(f'Удалено {deleted} записей старше {days} дней', 'success')

    return redirect(url_for('main.activity_log_page'))


@main_bp.route('/admin/backup', methods=['POST'])
@permission_required('manage_users')
def manual_backup():
    uid = session['user_id']

    ok, path_or_err, size_kb = create_backup(prefix='manual')

    if ok:
        log_activity(uid, 'create_backup',
                     f'Создан бэкап БД ({size_kb:.1f} КБ)',
                     'user', uid)
        flash(f'Бэкап создан: {os.path.basename(path_or_err)} ({size_kb:.1f} КБ)', 'success')
    else:
        flash(f'Ошибка: {path_or_err}', 'danger')

    return redirect(url_for('main.activity_log_page'))


# ============================================================
#                 ПРОФИЛЬ
# ============================================================

@main_bp.route('/profile')
@login_required
def profile():
    uid = session['user_id']
    return _render_profile(uid, is_self=True)


@main_bp.route('/profile/<int:uid>')
@login_required
def profile_view(uid):
    current_uid = session['user_id']
    if not Permission.has_permission(current_uid, 'manage_users'):
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('main.profile'))

    if uid == current_uid:
        return redirect(url_for('main.profile'))

    target = User.get_by_id(uid)
    if not target:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('main.users'))

    return _render_profile(uid, is_self=False)


def _render_profile(uid, is_self):
    profile_data = User.get_profile(uid)
    if not profile_data:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('main.dashboard'))

    positions = Position.get_user_positions(uid)
    journals = TeacherJournal.get_user_journals(uid)
    weekly_avg = get_user_weekly_avg(uid, weeks=4)
    recent_activity = get_recent_activity(limit=10, user_id=uid)

    perms_personal = Permission.get_personal_permissions(uid)
    perms_from_roles = PositionPermission.get_permissions_for_user_via_positions(uid)
    perms_all = Permission.get_user_permissions(uid)

    perms_dict = {}
    for p in Permission.get_all():
        perms_dict[p['code']] = p['name']

    positions_with_perms = []
    for pos in positions:
        pos_perms_ids = PositionPermission.get_for_position(pos['id'])
        pos_perms_codes = []
        for p in Permission.get_all():
            if p['id'] in pos_perms_ids:
                pos_perms_codes.append(p['code'])
        positions_with_perms.append({
            'position': dict(pos),
            'permission_codes': pos_perms_codes,
        })

    return render_template(
        'profile.html',
        profile_user=profile_data,
        positions=positions,
        positions_with_perms=positions_with_perms,
        perms=perms_all,
        perms_personal=perms_personal,
        perms_from_roles=perms_from_roles,
        perms_dict=perms_dict,
        journals=journals,
        weekly_avg=weekly_avg,
        recent_activity=recent_activity,
        is_self=is_self,
    )


@main_bp.route('/profile/edit', methods=['POST'])
@login_required
def profile_edit():
    uid = session['user_id']

    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()

    if has_emoji(username) or has_emoji(full_name):
        flash('Эмодзи запрещены', 'danger')
        return redirect(url_for('main.profile'))

    phone = re.sub(r'[^\d]', '', phone)[:11] if phone else ''

    s, m = User.update_profile(uid, username, full_name, phone)

    if s:
        session['username'] = username
        log_activity(uid, 'profile_edit',
                     f'Обновлён профиль (логин: {username})',
                     'user', uid)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.profile'))


@main_bp.route('/profile/change-password', methods=['POST'])
@login_required
def profile_change_password():
    uid = session['user_id']

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    new_password2 = request.form.get('new_password2', '')

    s, m = User.change_password(uid, current_password, new_password, new_password2)

    if s:
        log_activity(uid, 'password_change',
                     'Пароль изменён',
                     'user', uid)

    flash(m, 'success' if s else 'danger')
    return redirect(url_for('main.profile'))


# ============================================================
#                 ОТЧЕТЫ
# ============================================================

@main_bp.route('/reports')
@permission_required('create_report')
def reports():
    uid = session['user_id']
    if Permission.has_permission(uid, 'manage_users'):
        pairs = GroupSubject.get_all()
    else:
        pairs = TeacherJournal.get_user_journals(uid)
    return render_template('reports.html', pairs=pairs)


@main_bp.route('/reports/<int:gsid>')
@permission_required('create_report')
def view_report(gsid):
    uid = session['user_id']

    resp = _require_journal_access(uid, gsid)
    if resp:
        return resp

    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Пара не найдена', 'danger')
        return redirect(url_for('main.reports'))

    semester = request.args.get('semester', None, type=int)
    stats = JournalManager.get_statistics(gsid, semester)
    students = Student.get_by_group(pair['group_id'])

    student_stats = {}
    for s in stats['students']:
        st = Student.get_by_id(s['student_id'])
        if st:
            total_considered = (s['absences'] or 0) + (s['attendances'] or 0)

            student_stats[s['student_id']] = {
                'name': st['full_name'],
                'absences': s['absences'],
                'attendances': s['attendances'],
                'total': total_considered,
                'avg_grade': round(s['avg_grade'] or 0, 2),
                'absence_percent': round(
                    ((s['absences'] or 0) / total_considered * 100) if total_considered > 0 else 0,
                    1
                )
            }

    cf = f'report_{gsid}.png'
    cp = os.path.join(Config.STATIC_FOLDER, 'charts', cf)
    os.makedirs(os.path.dirname(cp), exist_ok=True)

    names = [s['full_name'] for s in students]
    absences = [student_stats.get(s['id'], {}).get('absences', 0) for s in students]
    avg_grades = [student_stats.get(s['id'], {}).get('avg_grade', 0) for s in students]

    try:
        generate_report_chart(names, absences, avg_grades, cp)
        chart_filename = f'charts/{cf}'
    except Exception as e:
        print(f"[report] Ошибка генерации графика: {e}")
        chart_filename = None

    return render_template('report_detail.html', pair=pair, stats=stats,
                           student_stats=student_stats, chart_filename=chart_filename)


# ============================================================
#                 СТАТИСТИКА ЧАСОВ ПРЕПОДАВАТЕЛЯ
# ============================================================

@main_bp.route('/teacher/hours-stats')
@login_required
def teacher_hours_stats():
    uid = session['user_id']
    journals = TeacherJournal.get_user_journals(uid)

    stats = []
    total_planned = {'lecture': 0, 'practice': 0, 'independent': 0, 'exam': 0, 'total': 0}
    total_actual = {'lecture': 0, 'practice': 0, 'independent': 0, 'exam': 0, 'total': 0}

    for j in journals:
        semesters = GroupSubject.get_semesters(j['id'])
        for sem in semesters:
            planned_row = TeacherHours.get(uid, j['id'], sem)
            if planned_row:
                planned = dict(planned_row)
            else:
                planned = {'lecture_hours': 0, 'practice_hours': 0, 'independent_hours': 0, 'exam_hours': 0}

            actual = JournalManager.get_conducted_hours(j['id'], sem)

            pt = (planned.get('lecture_hours', 0) + planned.get('practice_hours', 0) +
                  planned.get('independent_hours', 0) + planned.get('exam_hours', 0))

            stats.append({
                'group_name': j['group_name'],
                'subject_name': j['subject_name'],
                'gs_id': j['id'],
                'semester': sem,
                'planned': {
                    'lecture': planned.get('lecture_hours', 0),
                    'practice': planned.get('practice_hours', 0),
                    'independent': planned.get('independent_hours', 0),
                    'exam': planned.get('exam_hours', 0),
                    'total': pt
                },
                'actual': {
                    'lecture': actual.get('lecture', 0),
                    'practice': actual.get('practice', 0),
                    'independent': actual.get('independent', 0),
                    'exam': actual.get('exam', 0),
                    'total': actual.get('total', 0)
                }
            })

            total_planned['lecture'] += planned.get('lecture_hours', 0)
            total_planned['practice'] += planned.get('practice_hours', 0)
            total_planned['independent'] += planned.get('independent_hours', 0)
            total_planned['exam'] += planned.get('exam_hours', 0)
            total_planned['total'] += pt

            total_actual['lecture'] += actual.get('lecture', 0)
            total_actual['practice'] += actual.get('practice', 0)
            total_actual['independent'] += actual.get('independent', 0)
            total_actual['exam'] += actual.get('exam', 0)
            total_actual['total'] += actual.get('total', 0)

    return render_template('teacher_hours.html', stats=stats,
                           total_planned=total_planned, total_actual=total_actual)