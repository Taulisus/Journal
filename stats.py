"""
Статистика для главной страницы.

Функции:
  - get_user_weekly_avg(user_id, weeks=4, force=False)   — среднее число пар в неделю
  - refresh_user_weekly_avg(user_id, weeks=4)             — принудительный пересчёт
  - get_teacher_stats(user_id)                            — план/факт/осталось по журналам
  - is_cache_stale(user_id, stat_key, max_age_minutes=60) — устарел ли кэш
"""

import json
from datetime import datetime, timedelta

from models import get_db, TeacherJournal, GroupSubject
from journal_manager import JournalManager


# ============================================================
#                 ВНУТРЕННИЕ УТИЛИТЫ
# ============================================================

def _cache_get(user_id, stat_key):
    """
    Возвращает (value, updated_at) или (None, None), если нет.
    value — распарсенный JSON.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT stat_value, updated_at FROM stats_cache "
            "WHERE user_id = ? AND stat_key = ?",
            (user_id, stat_key)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None, None

    try:
        value = json.loads(row['stat_value']) if row['stat_value'] else None
    except (ValueError, TypeError):
        value = None

    return value, row['updated_at']


def _cache_set(user_id, stat_key, value):
    """
    Записывает value (любой JSON-сериализуемый) в кэш.
    """
    conn = get_db()
    try:
        now = datetime.now().isoformat(timespec='seconds')
        payload = json.dumps(value, ensure_ascii=False)

        existing = conn.execute(
            "SELECT id FROM stats_cache WHERE user_id = ? AND stat_key = ?",
            (user_id, stat_key)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE stats_cache SET stat_value = ?, updated_at = ? WHERE id = ?",
                (payload, now, existing['id'])
            )
        else:
            conn.execute(
                "INSERT INTO stats_cache (user_id, stat_key, stat_value, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, stat_key, payload, now)
            )
        conn.commit()
    finally:
        conn.close()


def is_cache_stale(user_id, stat_key, max_age_minutes=60):
    """
    Возвращает True, если кэша нет или он старше max_age_minutes.
    """
    _, updated_at = _cache_get(user_id, stat_key)
    if not updated_at:
        return True

    try:
        dt = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        return True

    return datetime.now() - dt > timedelta(minutes=max_age_minutes)


# ============================================================
#                 СРЕДНЕЕ ЧИСЛО ПАР В НЕДЕЛЮ
# ============================================================

def _collect_user_lessons(user_id, weeks=4):
    """
    Возвращает список (date, time_interval) — все уникальные занятия
    из всех журналов пользователя за последние `weeks` недель.

    Считает по журналам, где пользователь — преподаватель
    (teacher_journals).
    """
    journals = TeacherJournal.get_user_journals(user_id)
    if not journals:
        return []

    # Границы диапазона: последние N недель (включая текущую)
    today = datetime.now().date()
    start_date = today - timedelta(weeks=weeks)
    start_str = start_date.isoformat()

    conn = get_db()
    try:
        all_lessons = set()

        for j in journals:
            gs_id = j['id']
            table = JournalManager.get_table_name(gs_id)

            # Проверяем, существует ли таблица
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            ).fetchone()
            if not exists:
                continue

            # Уникальные пары (date, time_interval) за период
            rows = conn.execute(
                f"SELECT DISTINCT date, time_interval FROM {table} "
                f"WHERE date >= ? ORDER BY date",
                (start_str,)
            ).fetchall()

            for r in rows:
                date = r['date']
                ti = r['time_interval'] or ''
                key = (gs_id, date, ti)
                all_lessons.add(key)

        return sorted(all_lessons)
    finally:
        conn.close()


def refresh_user_weekly_avg(user_id, weeks=4):
    """
    Пересчитывает среднее число пар в неделю для пользователя
    и записывает в кэш. Возвращает:
      {
        'avg': float,               # среднее число пар в неделю
        'total_lessons': int,       # всего пар за период
        'weeks': int,               # число недель
        'period_start': str,        # YYYY-MM-DD
        'period_end': str,          # YYYY-MM-DD
        'updated_at': str,          # ISO timestamp
        'has_data': bool,           # есть ли хоть одна пара
      }
    """
    lessons = _collect_user_lessons(user_id, weeks=weeks)

    today = datetime.now().date()
    start_date = today - timedelta(weeks=weeks)

    total = len(lessons)
    avg = round(total / weeks, 2) if weeks > 0 else 0.0

    data = {
        'avg': avg,
        'total_lessons': total,
        'weeks': weeks,
        'period_start': start_date.isoformat(),
        'period_end': today.isoformat(),
        'updated_at': datetime.now().isoformat(timespec='seconds'),
        'has_data': total > 0,
    }

    _cache_set(user_id, 'weekly_avg', data)
    return data


def get_user_weekly_avg(user_id, weeks=4, force=False):
    """
    Возвращает кэшированное среднее число пар в неделю.
    Если кэша нет или он старше 60 минут (или force=True) — пересчитывает.
    """
    if force or is_cache_stale(user_id, 'weekly_avg', max_age_minutes=60):
        return refresh_user_weekly_avg(user_id, weeks=weeks)

    value, _ = _cache_get(user_id, 'weekly_avg')
    if value is None:
        # кэш был пустой/битый — пересчитываем
        return refresh_user_weekly_avg(user_id, weeks=weeks)

    return value


# ============================================================
#                 СТАТИСТИКА ПРЕПОДАВАТЕЛЯ
# ============================================================

def get_teacher_stats(user_id):
    """
    Для каждого журнала пользователя и каждого семестра считает:
      - план (из teacher_hours, fallback — group_subject_hours),
      - факт (JournalManager.get_conducted_hours),
      - осталось (план - факт).

    Возвращает:
      {
        'items': [ {...}, ... ],
        'total_planned': int,
        'total_actual': int,
        'total_remaining': int,
        'has_data': bool,
      }
    """
    journals = TeacherJournal.get_user_journals(user_id)
    items = []

    total_planned = 0
    total_actual = 0

    for j in journals:
        gs_id = j['id']
        semesters = GroupSubject.get_semesters(gs_id)

        for sem in semesters:
            # План: сначала teacher_hours, если нет — group_subject_hours
            planned_row = _get_planned_hours(user_id, gs_id, sem)
            plan_total = (
                planned_row.get('lecture_hours', 0)
                + planned_row.get('practice_hours', 0)
                + planned_row.get('independent_hours', 0)
                + planned_row.get('exam_hours', 0)
            )

            # Факт
            actual = JournalManager.get_conducted_hours(gs_id, sem)
            actual_total = actual.get('total', 0)

            remaining = max(plan_total - actual_total, 0)
            percent = round((actual_total / plan_total * 100), 1) if plan_total > 0 else 0

            items.append({
                'gs_id': gs_id,
                'group_name': j['group_name'],
                'subject_name': j['subject_name'],
                'semester': sem,
                'planned_total': plan_total,
                'actual_total': actual_total,
                'remaining': remaining,
                'percent': percent,
                'planned': {
                    'lecture': planned_row.get('lecture_hours', 0),
                    'practice': planned_row.get('practice_hours', 0),
                    'independent': planned_row.get('independent_hours', 0),
                    'exam': planned_row.get('exam_hours', 0),
                },
                'actual': {
                    'lecture': actual.get('lecture', 0),
                    'practice': actual.get('practice', 0),
                    'independent': actual.get('independent', 0),
                    'exam': actual.get('exam', 0),
                },
            })

            total_planned += plan_total
            total_actual += actual_total

    return {
        'items': items,
        'total_planned': total_planned,
        'total_actual': total_actual,
        'total_remaining': max(total_planned - total_actual, 0),
        'has_data': len(items) > 0,
    }


def _get_planned_hours(user_id, gs_id, semester):
    """
    Возвращает план часов для преподавателя:
      - если есть запись в teacher_hours — берём её,
      - иначе fallback на group_subject_hours.
    Возвращает dict с ключами lecture_hours / practice_hours /
    independent_hours / exam_hours.
    """
    from models import TeacherHours

    th = TeacherHours.get(user_id, gs_id, semester)
    if th:
        d = dict(th)
        return {
            'lecture_hours': d.get('lecture_hours', 0),
            'practice_hours': d.get('practice_hours', 0),
            'independent_hours': d.get('independent_hours', 0),
            'exam_hours': d.get('exam_hours', 0),
        }

    # Fallback: общий план пары (group_subject_hours)
    gh = GroupSubject.get_hours(gs_id, semester)
    if isinstance(gh, dict):
        return {
            'lecture_hours': gh.get('lecture_hours', 0),
            'practice_hours': gh.get('practice_hours', 0),
            'independent_hours': gh.get('independent_hours', 0),
            'exam_hours': gh.get('exam_hours', 0),
        }

    return {
        'lecture_hours': 0,
        'practice_hours': 0,
        'independent_hours': 0,
        'exam_hours': 0,
    }