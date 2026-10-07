# merge_groups.py
# -*- coding: utf-8 -*-
"""
Поиск и слияние похожих групп в таблице groups.

Проблема: после импорта расписания из PDF группы могут попадать в БД
в разных форматах:
    «ИСП 43-9» / «ИСП43-9» / «ИСП  43-9» / «ИСП 43 9»
    «ИСП 45-11» / «ИСП 45/11» / «ИСП 45.11»
Все три — одна группа.

Скрипт ищет похожие по нормализованному названию (убирает пробелы,
дефисы, точки, слэши; приводит к lower; ё→е) и предлагает слить.

Использование:
    python merge_groups.py            # показать группы (без изменений)
    python merge_groups.py --merge    # показать + слить
    python merge_groups.py --merge --yes  # авто
"""

import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'journal.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


# ============================================================
#                 НОРМАЛИЗАЦИЯ
# ============================================================

def normalize_group(name):
    """
    Приводит название группы к «канонической» форме для сравнения:
      - нижний регистр
      - ё → е
      - убирает пробелы, точки, дефисы, слэши, запятые
      - оставляет только буквы и цифры

    Пример:
      'ИСП 43-9'  → 'исп439'
      'ИСП43-9'   → 'исп439'
      'ИСП 45/11' → 'исп4511'
      'ИСП 45.11' → 'исп4511'
    """
    if not name:
        return ''
    s = name.strip().lower().replace('ё', 'е')
    s = re.sub(r'[^\w]', '', s, flags=re.UNICODE)
    return s


def extract_prefix_number(name):
    """
    Извлекает «префикс+номер» из названия группы.
    Работает для форматов:
      'ИСП 43-9'   → ('ИСП', '43-9')
      'РУПО 11'    → ('РУПО', '11')
      'ЮР 12А'     → ('ЮР', '12А')
      'ИС 32-9'    → ('ИС', '32-9')

    Возвращает (prefix, number) или (None, None).
    """
    if not name:
        return None, None
    s = name.strip()

    # Префикс — буквы в начале (рус или лат), до 6 символов
    m = re.match(r'^([А-Яа-яЁёA-Za-z]{2,6})\s*[-\s]?\s*(.+)$', s)
    if not m:
        return None, None

    prefix = m.group(1).strip().lower().replace('ё', 'е')
    number = m.group(2).strip()

    # Убираем всё, кроме букв, цифр и дефисов/точек/слэшей → нормализуем дефис
    number = re.sub(r'[\s.,/\\]+', '-', number)
    number = re.sub(r'-+', '-', number).strip('-')

    return prefix, number


# ============================================================
#                 ПОИСК ДУБЛЕЙ
# ============================================================

def find_groups(conn):
    """
    Возвращает список групп похожих групп.
    Каждая группа = [ {id, name}, ... ], минимум 2 элемента.

    Логика:
      1. Нормализуем название и группируем по совпадению.
      2. Дополнительно — по (prefix, number) с fuzzy.
    """
    rows = conn.execute("SELECT id, name FROM groups ORDER BY name").fetchall()
    groups_list = [{'id': r['id'], 'name': r['name']} for r in rows]

    if len(groups_list) < 2:
        return []

    # Шаг 1: группировка по нормализованному названию
    by_norm = {}
    for g in groups_list:
        key = normalize_group(g['name'])
        if not key:
            continue
        by_norm.setdefault(key, []).append(g)

    result = [items for items in by_norm.values() if len(items) > 1]

    # Шаг 2: fuzzy для оставшихся
    used_ids = set()
    for g in result:
        for x in g:
            used_ids.add(x['id'])

    remaining = [g for g in groups_list if g['id'] not in used_ids]

    try:
        from rapidfuzz import fuzz

        # Сравниваем пары по (prefix, number), нормализованный
        for i in range(len(remaining)):
            for j in range(i + 1, len(remaining)):
                a = normalize_group(remaining[i]['name'])
                b = normalize_group(remaining[j]['name'])

                if not a or not b:
                    continue

                ratio = fuzz.ratio(a, b)
                if ratio >= 90:  # группы короткие, поэтому порог высокий
                    found = None
                    for g in result:
                        if any(x['id'] == remaining[i]['id'] for x in g):
                            found = g
                            break
                    if found is None:
                        result.append([remaining[i], remaining[j]])
                    else:
                        if not any(x['id'] == remaining[j]['id'] for x in found):
                            found.append(remaining[j])
    except ImportError:
        pass  # без rapidfuzz — только точные совпадения

    return result


def print_groups(groups):
    if not groups:
        print("\n[=] Похожих групп не найдено.")
        return
    print(f"\n[!] Найдено групп с похожими названиями: {len(groups)}\n")
    for idx, items in enumerate(groups, start=1):
        print(f"  Группа #{idx}  ({len(items)} записей):")
        for g in items:
            prefix, number = extract_prefix_number(g['name'])
            print(f"    [{g['id']:4d}]  {g['name']!r}  (prefix: {prefix}, номер: {number})")
        print()


# ============================================================
#                 ВЫБОР ГЛАВНОЙ
# ============================================================

def choose_keep(items):
    """
    Выбирает «главную» запись:
      - с более длинным названием (полное — лучше сокращения),
      - при равенстве — с меньшим id.
    """
    return max(items, key=lambda s: (len(s['name'] or ''), -s['id']))


# ============================================================
#                 СЛИЯНИЕ
# ============================================================

def make_backup():
    if not os.path.exists(DB_PATH):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(BACKUP_DIR, f'journal_{ts}_before_merge_groups.db')
    shutil.copy2(DB_PATH, dst)
    print(f"[+] Бэкап: {dst}")
    return dst


def merge(conn, groups):
    """
    Слияние групп: оставляем главную, у остальных:
      - students: переносим студентов в главную группу
        (если у студента ФИО уже есть в главной — пропускаем / удаляем дубль)
      - group_subjects: если у главной группы уже есть журнал по тому же
        предмету — переносим данные из журнала-дубля в главный журнал
        и удаляем дубль. Если нет — обновляем group_id.
      - schedule_lessons: обновляем group_id.
      - curators: переносим кураторство (при UNIQUE(user_id, group_id)
        дубли пропускаем).
      - student_group_history: обновляем group_id (уникальных ограничений нет).
      - group_aliases: обновляем group_id (если алиас не конфликтует).
      - Удаляем дубль.

    Возвращает (merged, stats_dict, errors).
    """
    stats = {
        'students_moved': 0,
        'students_skipped_dup': 0,
        'journals_moved': 0,
        'journals_transferred': 0,
        'lessons_updated': 0,
        'curators_moved': 0,
        'history_updated': 0,
        'aliases_moved': 0,
    }
    merged = 0
    errors = []

    for items in groups:
        keep = choose_keep(items)
        drop = [g for g in items if g['id'] != keep['id']]

        print(f"\n→ Группа:")
        print(f"    Оставляем [{keep['id']}] {keep['name']!r}")
        for d in drop:
            print(f"    Удаляем  [{d['id']}] {d['name']!r}")

        for d in drop:
            drop_id = d['id']
            keep_id = keep['id']

            # --- 1. Студенты ---
            drop_students = conn.execute(
                "SELECT id, full_name FROM students WHERE group_id = ?",
                (drop_id,)
            ).fetchall()

            keep_students_names = {
                (r['full_name'] or '').strip().lower()
                for r in conn.execute(
                    "SELECT full_name FROM students WHERE group_id = ?",
                    (keep_id,)
                ).fetchall()
            }

            for st in drop_students:
                sname = (st['full_name'] or '').strip().lower()
                if sname in keep_students_names:
                    # Дубль по ФИО — удаляем студента
                    try:
                        conn.execute("DELETE FROM students WHERE id = ?", (st['id'],))
                        stats['students_skipped_dup'] += 1
                    except Exception as e:
                        errors.append(f"students delete #{st['id']}: {e}")
                else:
                    conn.execute(
                        "UPDATE students SET group_id = ? WHERE id = ?",
                        (keep_id, st['id'])
                    )
                    keep_students_names.add(sname)
                    stats['students_moved'] += 1

            # --- 2. group_subjects ---
            drop_pairs = conn.execute(
                "SELECT id, subject_id FROM group_subjects WHERE group_id = ?",
                (drop_id,)
            ).fetchall()

            for p in drop_pairs:
                pair_drop_id = p['id']
                subject_id = p['subject_id']

                pair_keep = conn.execute(
                    "SELECT id FROM group_subjects WHERE group_id = ? AND subject_id = ?",
                    (keep_id, subject_id)
                ).fetchone()

                if pair_keep:
                    # Переносим данные из журнала-дубля в главный
                    try:
                        _transfer_journal_data(
                            conn, pair_drop_id, pair_keep['id']
                        )
                        conn.execute(f"DROP TABLE IF EXISTS journal_{pair_drop_id}")
                        conn.execute(
                            "DELETE FROM group_subject_hours WHERE group_subject_id = ?",
                            (pair_drop_id,)
                        )
                        conn.execute(
                            "DELETE FROM student_semester_grades WHERE group_subject_id = ?",
                            (pair_drop_id,)
                        )
                        conn.execute(
                            "DELETE FROM group_subjects WHERE id = ?",
                            (pair_drop_id,)
                        )
                        stats['journals_transferred'] += 1
                    except Exception as e:
                        errors.append(f"journal_{pair_drop_id}: {e}")
                else:
                    try:
                        conn.execute(
                            "UPDATE group_subjects SET group_id = ? WHERE id = ?",
                            (keep_id, pair_drop_id)
                        )
                        stats['journals_moved'] += 1
                    except Exception as e:
                        errors.append(f"group_subjects #{pair_drop_id}: {e}")

            # --- 3. Расписание ---
            try:
                cur = conn.execute(
                    "UPDATE schedule_lessons SET group_id = ? WHERE group_id = ?",
                    (keep_id, drop_id)
                )
                stats['lessons_updated'] += cur.rowcount
            except Exception as e:
                errors.append(f"schedule_lessons: {e}")

            # --- 4. Кураторы ---
            drop_curators = conn.execute(
                "SELECT id, user_id FROM curators WHERE group_id = ?",
                (drop_id,)
            ).fetchall()
            for c in drop_curators:
                existing = conn.execute(
                    "SELECT id FROM curators WHERE user_id = ? AND group_id = ?",
                    (c['user_id'], keep_id)
                ).fetchone()
                if existing:
                    # Уже есть — удаляем дубль
                    conn.execute("DELETE FROM curators WHERE id = ?", (c['id'],))
                else:
                    conn.execute(
                        "UPDATE curators SET group_id = ? WHERE id = ?",
                        (keep_id, c['id'])
                    )
                    stats['curators_moved'] += 1

            # --- 5. История переводов ---
            try:
                cur = conn.execute(
                    "UPDATE student_group_history SET group_id = ? WHERE group_id = ?",
                    (keep_id, drop_id)
                )
                stats['history_updated'] += cur.rowcount
            except Exception as e:
                errors.append(f"student_group_history: {e}")

            # --- 6. Алиасы групп ---
            drop_aliases = conn.execute(
                "SELECT id, alias FROM group_aliases WHERE group_id = ?",
                (drop_id,)
            ).fetchall()
            for a in drop_aliases:
                # Проверим, нет ли такого же алиаса у главной
                existing = conn.execute(
                    "SELECT id FROM group_aliases WHERE LOWER(alias) = LOWER(?) AND group_id = ?",
                    (a['alias'], keep_id)
                ).fetchone()
                if existing:
                    conn.execute("DELETE FROM group_aliases WHERE id = ?", (a['id'],))
                else:
                    try:
                        conn.execute(
                            "UPDATE group_aliases SET group_id = ? WHERE id = ?",
                            (keep_id, a['id'])
                        )
                        stats['aliases_moved'] += 1
                    except sqlite3.IntegrityError:
                        # Алиас уникален и уже занят кем-то ещё — пропускаем
                        conn.execute("DELETE FROM group_aliases WHERE id = ?", (a['id'],))

            # --- 7. Удаляем дубль группы ---
            try:
                conn.execute("DELETE FROM groups WHERE id = ?", (drop_id,))
                merged += 1
            except Exception as e:
                errors.append(f"groups #{drop_id}: {e}")

    conn.commit()
    return merged, stats, errors


def _transfer_journal_data(conn, from_gsid, to_gsid):
    """
    Переносит записи из journal_<from_gsid> в journal_<to_gsid>.
    Если в главном журнале уже есть запись по (student_id, date, time_interval) —
    пропускаем (главная приоритетна).
    """
    for t in (f'journal_{from_gsid}', f'journal_{to_gsid}'):
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (t,)
        ).fetchone()
        if not exists:
            return

    rows = conn.execute(f'''
        SELECT student_id, date, time_interval, semester, topic, type,
               attendance, grade, comment
        FROM journal_{from_gsid}
    ''').fetchall()

    for r in rows:
        exists = conn.execute(f'''
            SELECT id FROM journal_{to_gsid}
            WHERE student_id = ? AND date = ? AND time_interval = ?
            LIMIT 1
        ''', (r['student_id'], r['date'], r['time_interval'])).fetchone()

        if exists:
            continue

        conn.execute(f'''
            INSERT INTO journal_{to_gsid}
            (student_id, date, time_interval, semester, topic, type, attendance, grade, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            r['student_id'], r['date'], r['time_interval'],
            r['semester'], r['topic'], r['type'],
            r['attendance'], r['grade'], r['comment']
        ))


# ============================================================
#                 MAIN
# ============================================================

def main():
    if not os.path.exists(DB_PATH):
        print(f"[!] БД не найдена: {DB_PATH}")
        sys.exit(1)

    do_merge = '--merge' in sys.argv
    auto_yes = '--yes' in sys.argv

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        groups = find_groups(conn)
        print_groups(groups)

        if not groups:
            return

        if not do_merge:
            print("Запустите с --merge, чтобы выполнить слияние:")
            print("    python merge_groups.py --merge")
            return

        print(f"\nПлан слияния: {len(groups)} групп")
        if not auto_yes:
            answer = input("Выполнить? (yes/no): ").strip().lower()
            if answer not in ('yes', 'y', 'да', 'д'):
                print("Отменено.")
                return

        make_backup()
        merged, stats, errors = merge(conn, groups)

        print(f"\n[+] Слито групп: {merged}")
        print(f"    Студентов перенесено:       {stats['students_moved']}")
        print(f"    Студентов-дублей удалено:   {stats['students_skipped_dup']}")
        print(f"    Журналов перенесено:        {stats['journals_moved']}")
        print(f"    Журналов объединено:        {stats['journals_transferred']}")
        print(f"    Занятий в расписании:       {stats['lessons_updated']}")
        print(f"    Кураторств перенесено:      {stats['curators_moved']}")
        print(f"    Записей истории обновлено:  {stats['history_updated']}")
        print(f"    Алиасов перенесено:         {stats['aliases_moved']}")

        if errors:
            print(f"\n[!] Ошибки ({len(errors)}):")
            for e in errors[:20]:
                print(f"    - {e}")

    finally:
        conn.close()


if __name__ == '__main__':
    main()