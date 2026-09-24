# blueprints/_helpers.py
# -*- coding: utf-8 -*-
"""
Общие хелперы для всех Blueprints.
"""

import os
import re
import shutil
from datetime import datetime

from flask import session, redirect, url_for, flash, jsonify

from config import Config
from models import Permission, TeacherJournal, GroupSubject


# ============================================================
#                 ЭМОДЗИ
# ============================================================

def has_emoji(text):
    """True, если в тексте есть эмодзи."""
    if not text:
        return False
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\u2600-\u27BF\U0001F900-\U0001F9FF]+",
        flags=re.UNICODE,
    )
    return bool(emoji_pattern.search(text))


# ============================================================
#                 БЭКАП БД
# ============================================================

def _make_db_backup(prefix='manual'):
    """
    Делает копию journal.db в backups/ с указанным префиксом.
    Возвращает путь или None.
    """
    try:
        db_path = Config.DATABASE
        if not os.path.exists(db_path):
            return None

        backup_dir = os.path.join(
            os.path.dirname(os.path.abspath(db_path)), 'backups'
        )
        os.makedirs(backup_dir, exist_ok=True)

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        dst = os.path.join(backup_dir, f'journal_{ts}_before_{prefix}.db')
        shutil.copy2(db_path, dst)
        return dst
    except Exception as e:
        print(f"[backup] Ошибка: {e}")
        return None


# ============================================================
#                 ДОСТУП К ЖУРНАЛУ
# ============================================================

def _user_owns_journal(uid, gsid):
    """True, если у пользователя есть manage_users ИЛИ журнал ему назначен."""
    if Permission.has_permission(uid, 'manage_users'):
        return True
    return any(
        j['id'] == gsid for j in TeacherJournal.get_user_journals(uid)
    )


def _require_journal_access(uid, gsid):
    """
    Возвращает None, если доступ есть, иначе Response (redirect + flash).
    Для HTML-роутов.
    """
    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        flash('Журнал не найден', 'danger')
        return redirect(url_for('journals.index'))
    if not _user_owns_journal(uid, gsid):
        flash('Журнал вам не назначен', 'danger')
        return redirect(url_for('journals.index'))
    return None


def _require_journal_access_json(uid, gsid):
    """
    Для JSON-эндпоинтов. Возвращает None или (jsonify, status_code).
    """
    pair = GroupSubject.get_by_id(gsid)
    if not pair:
        return jsonify({'success': False, 'message': 'Журнал не найден'}), 404
    if not _user_owns_journal(uid, gsid):
        return jsonify({
            'success': False,
            'message': 'Журнал вам не назначен'
        }), 403
    return None