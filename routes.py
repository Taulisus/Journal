from datetime import datetime
import os
import re
import shutil

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    jsonify, session, Response, send_file,
)
from werkzeug.security import generate_password_hash

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
from stats import get_user_weekly_avg, refresh_user_weekly_avg, get_teacher_stats
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


main_bp = Blueprint('main', __name__)


# ============================================================
#                 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def has_emoji(text):
    if not text:
        return False
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u27BF\U0001F900-\U0001F9FF]+",
        flags=re.UNICODE)
    return bool(emoji_pattern.search(text))


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

        days.append({
            'date': ds,
            'date_label': f"{d.day:02d}.{d.month:02d}",
            'day_short': day_names[i],
            'day_full': ScheduleLesson.DAY_NAMES_FULL[i],
            'is_today': d == datetime.now().date(),
            'lessons': lessons,
        })

    return {
        'days': days,
        'week_start': monday.isoformat(),
        'prev_week': (monday - timedelta(days=7)).isoformat(),
        'next_week': (monday + timedelta(days=7)).isoformat(),
        'has_any': any(d['lessons'] for d in days),
    }


# ============================================================
#                 ГЛАВНАЯ
# ============================================================

@main_bp.route('/')
@login_required
def dashboard():
    uid = session['user_id']

    groups_count = len(Group.get_all())
    subjects_count = len(Subject.get_all())
    students_count = len(Student.get_all())
    pairs_count = len(GroupSubject.get_all())

    weekly_avg = get_user_weekly_avg(uid, weeks=4)

    activity = None
    if Permission.has_permission(uid, 'manage_users'):
        activity = get_recent_activity(limit=20)

    teacher_stats = None
    has_journals = len(TeacherJournal.get_user_journals(uid)) > 0
    if has_journals:
        teacher_stats = get_teacher_stats(uid)

    week_param = request.args.get('week')
    schedule_week = None
    try:
        schedule_week = _get_week_schedule(uid, week_param)
    except Exception as e:
        print(f"[dashboard] Не удалось получить расписание: {e}")

    current_user_teacher_id = None
    try:
        current_user_teacher_id = User.get_teacher_id(uid)
    except Exception:
        pass

    return render_template(
        'dashboard.html',
        groups_count=groups_count,
        subjects_count=subjects_count,
        students_count=students_count,
        pairs_count=pairs_count,
        weekly_avg=weekly_avg,
        activity=activity,
        teacher_stats=teacher_stats,
        schedule_week=schedule_week,
        current_user_teacher_id=current_user_teacher_id,
    )


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