# merge_subjects.py
# -*- coding: utf-8 -*-
"""
Поиск и слияние похожих предметов в таблице subjects.

Проблема: после импорта расписания из PDF предметы с кодом МДК могут
попадать в БД в разных форматах:
    «МДК 06.04 Интеллектуальные системы и технологии»
    «06.04 Интел системы»
    «06.04 Интеллектуальные системы»
Все три — один предмет.

Скрипт ищет похожие по нормализованному названию (без МДК/пунктуации,
lower, ё→е) и предлагает слить.

Использование:
    python merge_subjects.py            # показать группы (без изменений)
    python merge_subjects.py --merge    # показать + слить
    python merge_subjects.py --merge --yes  # авто
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

def normalize_subject(name):
    """
    Приводит название предмета к «канонической» форме для сравнения:
      - нижний регистр
      - ё → е
      - убирает префикс «МДК»
      - убирает точки, запятые, дефисы
      - сжимает пробелы
    """
    if not name:
        return ''
    s = name.strip().lower().replace('ё', 'е')

    # Убираем «мдк» в начале
    s = re.sub(r'^\s*мдк\s*', '', s)

    # Убираем всё, кроме букв, цифр и пробелов
    s = re.sub(r'[^\w\s]', ' ', s, flags=re.UNICODE)

    # Сжимаем пробелы
    s = re.sub(r'\s+', ' ', s).strip()

    return s


def extract_code(name):
    """
    Извлекает код МДК вида '06.04' из названия, если он есть.
    Возвращает строку или None.
    """
    if not name:
        return None
    # Ищем XX.XX или XX.XX.XX
    m = re.search(r'\b(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\b', name)
    return m.group(1) if m else None


def short_key(name):
    """
    Короткий ключ для группировки: код МДК + первые значимые слова.
    Используется, когда fuzzy не сработал.
    """
    s = normalize_subject(name)
    words = s.split()
    # Первые 3 слова после кода
    return ' '.join(words[:3])


# ============================================================
#                 ПОИСК ДУБЛЕЙ
# ============================================================

def find_groups(conn):
    """
    Возвращает список групп похожих предметов.
    Каждая группа = [ {id, name}, ... ], минимум 2 элемента.

    Логика:
      1. Сначала группируем по коду МДК (06.04).
         Если у нескольких предметов один и тот же код — они в одной группе.
      2. Внутри группы — fuzzy-сравнение нормализованных названий.
      3. Если rapidfuzz недоступен — по первым 2 словам.
    """
    rows = conn.execute("SELECT id, name FROM subjects ORDER BY name").fetchall()
    subjects = [{'id': r['id'], 'name': r['name']} for r in rows]

    if len(subjects) < 2:
        return []

    # Шаг 1: группировка по коду МДК
    by_code = {}
    for s in subjects:
        code = extract_code(s['name'])
        if code:
            by_code.setdefault(code, []).append(s)

    groups = []
    for code, items in by_code.items():
        if len(items) > 1:
            groups.append(items)

    # Шаг 2: fuzzy для оставшихся (без кода или из разных групп)
    # Соберём «уже в группах», чтобы не дублировать
    used_ids = set()
    for g in groups:
        for s in g:
            used_ids.add(s['id'])

    remaining = [s for s in subjects if s['id'] not in used_ids]

    # Fuzzy по нормализованным названиям
    try:
        from rapidfuzz import fuzz

        # Сравниваем каждую пару
        for i in range(len(remaining)):
            for j in range(i + 1, len(remaining)):
                a = normalize_subject(remaining[i]['name'])
                b = normalize_subject(remaining[j]['name'])

                if not a or not b:
                    continue

                ratio = fuzz.token_sort_ratio(a, b)
                # Порог чувствительности: 85 — довольно строго
                if ratio >= 85:
                    # Ищем, есть ли уже группа с одним из них
                    found = None
                    for g in groups:
                        if any(s['id'] == remaining[i]['id'] for s in g):
                            found = g
                            break
                    if found is None:
                        groups.append([remaining[i], remaining[j]])
                    else:
                        if not any(s['id'] == remaining[j]['id'] for s in found):
                            found.append(remaining[j])
    except ImportError:
        # Fallback: по первым 2 словам
        by_key = {}
        for s in remaining:
            k = ' '.join(normalize_subject(s['name']).split()[:2])
            if k:
                by_key.setdefault(k, []).append(s)
        for k, items in by_key.items():
            if len(items) > 1:
                groups.append(items)

    return groups


def print_groups(groups):
    if not groups:
        print("\n[=] Похожих предметов не найдено.")
        return
    print(f"\n[!] Найдено групп похожих предметов: {len(groups)}\n")
    for idx, items in enumerate(groups, start=1):
        print(f"  Группа #{idx}  ({len(items)} записей):")
        for s in items:
            code = extract_code(s['name'])
            print(f"    [{s['id']:4d}]  {s['name']!r}  (код: {code})")
        print()


# ============================================================
#                 СЛИЯНИЕ
# ============================================================

def choose_keep(items):
    """
    Выбирает «главную» запись:
      - С более длинным названием (полное — лучше сокращения).
      - При равенстве — с меньшим id.
    """
    def score(s):
        # Длиннее + есть «МДК» в названии + есть слова «Интеллект»
        n = s['name'] or ''
        return (
            len(n),
            'мдк' in n.lower(),
            'интеллект' in n.lower(),
        )
    return max(items, key=score)


def make_backup():
    if not os.path.exists(DB_PATH):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(BACKUP_DIR, f'journal_{ts}_before_merge_subjects.db')
    shutil.copy2(DB_PATH, dst)
    print(f"[+] Бэкап: {dst}")
    return dst


def merge(conn, groups):
    """
    Слияние: оставляем главный предмет, у остальных:
      - В group_subjects:
          * если у группы уже есть журнал по главному предмету — переносим данные
            из журнала дубля в главный и удаляем дубль.
          * если нет — обновляем subject_id.
      - В schedule_lessons: просто обновляем subject_id.
      - Удаляем дубли.
    Возвращает (merged_count, deleted_journals, errors).
    """
    merged = 0
    deleted_journals = 0
    errors = []

    for items in groups:
        keep = choose_keep(items)
        drop = [s for s in items if s['id'] != keep['id']]

        print(f"\n→ Группа предметов:")
        print(f"    Оставляем [{keep['id']}] {keep['name']!r}")
        for d in drop:
            print(f"    Удаляем  [{d['id']}] {d['name']!r}")

        for d in drop:
            drop_id = d['id']
            keep_id = keep['id']

            # 1. Расписание
            try:
                conn.execute(
                    "UPDATE schedule_lessons SET subject_id = ? WHERE subject_id = ?",
                    (keep_id, drop_id)
                )
            except Exception as e:
                errors.append(f"schedule_lessons: {e}")

            # 2. group_subjects — там UNIQUE(group_id, subject_id)
            pairs_drop = conn.execute(
                "SELECT id, group_id FROM group_subjects WHERE subject_id = ?",
                (drop_id,)
            ).fetchall()

            for pair_drop in pairs_drop:
                pair_drop_id = pair_drop['id']
                group_id = pair_drop['group_id']

                # Уже есть журнал по главному предмету в этой группе?
                pair_keep = conn.execute(
                    "SELECT id FROM group_subjects WHERE group_id = ? AND subject_id = ?",
                    (group_id, keep_id)
                ).fetchone()

                if pair_keep:
                    # Переносим данные из journal_<pair_drop_id> в journal_<pair_keep_id>
                    try:
                        _transfer_journal_data(
                            conn, pair_drop_id, pair_keep['id']
                        )
                        # Удаляем таблицу дубля
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
                        deleted_journals += 1
                    except Exception as e:
                        errors.append(f"Не удалось перенести journal_{pair_drop_id}: {e}")
                else:
                    # Просто перепривязываем
                    try:
                        conn.execute(
                            "UPDATE group_subjects SET subject_id = ? WHERE id = ?",
                            (keep_id, pair_drop_id)
                        )
                    except Exception as e:
                        errors.append(f"group_subjects: {e}")

            # 3. Удаляем сам дубль
            try:
                conn.execute("DELETE FROM subjects WHERE id = ?", (drop_id,))
                merged += 1
            except Exception as e:
                errors.append(f"subjects: {e}")

    conn.commit()
    return merged, deleted_journals, errors


def _transfer_journal_data(conn, from_gsid, to_gsid):
    """
    Переносит записи из journal_<from_gsid> в journal_<to_gsid>.
    Если в главном журнале уже есть запись по (student_id, date, time_interval) —
    пропускаем (главная запись приоритетна).
    """
    # Проверка, что таблицы существуют
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

    # Включаем внешние ключи + WAL — как в models.py
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        groups = find_groups(conn)
        print_groups(groups)

        if not groups:
            return

        if not do_merge:
            print("Запустите с --merge, чтобы выполнить слияние:")
            print("    python merge_subjects.py --merge")
            return

        print(f"\nПлан слияния: {len(groups)} групп")
        if not auto_yes:
            answer = input("Выполнить? (yes/no): ").strip().lower()
            if answer not in ('yes', 'y', 'да', 'д'):
                print("Отменено.")
                return

        make_backup()
        merged, deleted_j, errors = merge(conn, groups)

        print(f"\n[+] Слито предметов: {merged}")
        if deleted_j:
            print(f"[+] Удалено дублирующих журналов: {deleted_j}")
        if errors:
            print(f"\n[!] Ошибки ({len(errors)}):")
            for e in errors[:20]:
                print(f"    - {e}")

    finally:
        conn.close()


if __name__ == '__main__':
    main()