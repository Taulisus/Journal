"""
Модуль логирования действий пользователей.
"""

import csv
import io
from datetime import datetime, timedelta

from flask import request, has_request_context

from models import get_db


# ============================================================
#                 ЛОГИРОВАНИЕ
# ============================================================

def log_activity(user_id, action, description='', target_type=None, target_id=None):
    try:
        ip = None
        if has_request_context():
            xff = request.headers.get('X-Forwarded-For', '')
            if xff:
                ip = xff.split(',')[0].strip()
            else:
                ip = request.remote_addr

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO activity_log "
                "(user_id, action, description, target_type, target_id, ip, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    action,
                    description or '',
                    target_type,
                    target_id,
                    ip,
                    datetime.now().isoformat(timespec='seconds'),
                )
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[activity] Ошибка логирования: {e}")


# ============================================================
#                 ЧТЕНИЕ ЛОГА
# ============================================================

def get_recent_activity(limit=20, user_id=None):
    conn = get_db()
    try:
        if user_id is not None:
            rows = conn.execute('''
                SELECT al.*, u.username, up.full_name
                FROM activity_log al
                LEFT JOIN users u ON al.user_id = u.id
                LEFT JOIN user_profiles up ON u.id = up.user_id
                WHERE al.user_id = ?
                ORDER BY al.created_at DESC
                LIMIT ?
            ''', (user_id, limit)).fetchall()
        else:
            rows = conn.execute('''
                SELECT al.*, u.username, up.full_name
                FROM activity_log al
                LEFT JOIN users u ON al.user_id = u.id
                LEFT JOIN user_profiles up ON u.id = up.user_id
                ORDER BY al.created_at DESC
                LIMIT ?
            ''', (limit,)).fetchall()
    finally:
        conn.close()

    return [_row_to_dict(r) for r in rows]


def _build_where(filters):
    where = []
    params = []

    if filters.get('user_id'):
        where.append("al.user_id = ?")
        params.append(filters['user_id'])
    if filters.get('action'):
        where.append("al.action = ?")
        params.append(filters['action'])
    if filters.get('target_type'):
        where.append("al.target_type = ?")
        params.append(filters['target_type'])
    if filters.get('date_from'):
        where.append("al.created_at >= ?")
        params.append(filters['date_from'] + 'T00:00:00')
    if filters.get('date_to'):
        where.append("al.created_at <= ?")
        params.append(filters['date_to'] + 'T23:59:59')
    if filters.get('search'):
        where.append("(al.description LIKE ? OR u.username LIKE ? OR up.full_name LIKE ?)")
        s = f"%{filters['search']}%"
        params.extend([s, s, s])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    return where_sql, params


def get_activity_filtered(filters=None, page=1, per_page=50):
    filters = filters or {}
    where_sql, params = _build_where(filters)

    conn = get_db()
    try:
        total = conn.execute(f'''
            SELECT COUNT(*) as c
            FROM activity_log al
            LEFT JOIN users u ON al.user_id = u.id
            LEFT JOIN user_profiles up ON u.id = up.user_id
            {where_sql}
        ''', params).fetchone()['c']

        offset = max(0, (page - 1) * per_page)

        rows = conn.execute(f'''
            SELECT al.*, u.username, up.full_name
            FROM activity_log al
            LEFT JOIN users u ON al.user_id = u.id
            LEFT JOIN user_profiles up ON u.id = up.user_id
            {where_sql}
            ORDER BY al.created_at DESC
            LIMIT ? OFFSET ?
        ''', params + [per_page, offset]).fetchall()
    finally:
        conn.close()

    total_pages = max(1, (total + per_page - 1) // per_page)

    return {
        'items': [_row_to_dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    }


def get_activity_for_export(filters=None, limit=10000):
    filters = filters or {}
    where_sql, params = _build_where(filters)

    conn = get_db()
    try:
        rows = conn.execute(f'''
            SELECT al.*, u.username, up.full_name
            FROM activity_log al
            LEFT JOIN users u ON al.user_id = u.id
            LEFT JOIN user_profiles up ON u.id = up.user_id
            {where_sql}
            ORDER BY al.created_at DESC
            LIMIT ?
        ''', params + [limit]).fetchall()
    finally:
        conn.close()

    return [_row_to_dict(r) for r in rows]


def get_unique_actions():
    conn = get_db()
    try:
        rows = conn.execute("SELECT DISTINCT action FROM activity_log ORDER BY action").fetchall()
    finally:
        conn.close()
    return [r['action'] for r in rows]


def get_unique_users():
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT DISTINCT al.user_id, u.username, up.full_name
            FROM activity_log al
            LEFT JOIN users u ON al.user_id = u.id
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE al.user_id IS NOT NULL
            ORDER BY up.full_name, u.username
        ''').fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_unique_target_types():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT target_type FROM activity_log "
            "WHERE target_type IS NOT NULL ORDER BY target_type"
        ).fetchall()
    finally:
        conn.close()
    return [r['target_type'] for r in rows]


# ============================================================
#                 CSV-ЭКСПОРТ
# ============================================================

def activity_to_csv(items):
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    writer.writerow([
        'ID', 'Дата и время', 'Пользователь', 'Логин',
        'Действие', 'Описание', 'Тип объекта', 'ID объекта', 'IP',
    ])

    for a in items:
        writer.writerow([
            a.get('id', ''),
            a.get('created_at', ''),
            a.get('display_name', ''),
            a.get('username', ''),
            a.get('action', ''),
            a.get('description', ''),
            a.get('target_type', '') or '',
            a.get('target_id', '') or '',
            a.get('ip', '') or '',
        ])

    return output.getvalue()


# ============================================================
#                 ССЫЛКИ НА ОБЪЕКТЫ
# ============================================================

def get_target_url(target_type, target_id):
    if not target_type or not target_id:
        return None
    try:
        tid = int(target_id)
    except (ValueError, TypeError):
        return None

    try:
        from flask import url_for

        if target_type == 'user':
            return url_for('main.profile_view', uid=tid)
        if target_type == 'group':
            return url_for('main.groups')
        if target_type == 'subject':
            return url_for('main.subjects')
        if target_type == 'student':
            return url_for('main.student_card', sid=tid)
        if target_type == 'journal':
            return url_for('main.journal', gsid=tid)
    except Exception:
        return None

    return None


# ============================================================
#                 ВНУТРЕННИЕ УТИЛИТЫ
# ============================================================

def _row_to_dict(r):
    d = dict(r)
    d['created_at_human'] = _humanize_time(d.get('created_at'))
    d['display_name'] = d.get('full_name') or d.get('username') or 'Аноним'
    d['target_url'] = get_target_url(d.get('target_type'), d.get('target_id'))
    return d


def _humanize_time(iso_str):
    if not iso_str:
        return ''
    try:
        dt = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return iso_str

    today = datetime.now().date()
    if dt.date() == today:
        return f"сегодня {dt.strftime('%H:%M')}"
    if dt.date() == today - timedelta(days=1):
        return f"вчера {dt.strftime('%H:%M')}"

    return dt.strftime('%d.%m.%Y %H:%M')


# ============================================================
#                 ОЧИСТКА СТАРОГО ЛОГА
# ============================================================

def get_old_activity_stats(days=90):
    """
    Возвращает статистику по старым записям:
      {
        'total': int,           # всего записей в логе
        'old_count': int,       # старше N дней
        'cutoff_date': str,     # граница (YYYY-MM-DD)
        'oldest_date': str,     # самая старая запись (YYYY-MM-DD или None)
      }
    """
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec='seconds')

    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
        old_count = conn.execute(
            "SELECT COUNT(*) FROM activity_log WHERE created_at < ?", (cutoff,)
        ).fetchone()[0]
        oldest = conn.execute(
            "SELECT MIN(created_at) FROM activity_log"
        ).fetchone()[0]
    finally:
        conn.close()

    oldest_date = None
    if oldest:
        try:
            oldest_date = datetime.fromisoformat(oldest).strftime('%d.%m.%Y')
        except (ValueError, TypeError):
            oldest_date = oldest

    cutoff_human = (datetime.now() - timedelta(days=days)).strftime('%d.%m.%Y')

    return {
        'total': total,
        'old_count': old_count,
        'cutoff_date': cutoff_human,
        'oldest_date': oldest_date,
    }


def clear_old_activity(days=90):
    """
    Удаляет записи activity_log старше N дней.
    Возвращает (deleted_count, error_message).
    """
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec='seconds')

    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM activity_log WHERE created_at < ?", (cutoff,))
        deleted = cur.rowcount
        conn.commit()
        return deleted, None
    except Exception as e:
        conn.rollback()
        return 0, str(e)
    finally:
        conn.close()