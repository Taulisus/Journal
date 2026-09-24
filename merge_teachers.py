# merge_teachers.py
# -*- coding: utf-8 -*-
"""
Слияние дублей в teachers.

Запуск:
    python merge_teachers.py           — анализ, показывает группы дублей
    python merge_teachers.py --merge   — то же + подтверждение и слияние
    python merge_teachers.py --merge --yes  — без интерактива (авто)
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


def norm_surname(s):
    """Нормализует фамилию: lower, strip, ё→е."""
    if not s:
        return ''
    return s.strip().lower().replace('ё', 'е')


def is_short_form(fio):
    """
    True, если ФИО короткое:
      - есть точка (инициалы: «Тетенькин Д.А.»)
      - или меньше 3 слов без отчества
    """
    if not fio:
        return False
    fio = fio.strip()
    if '.' in fio:
        return True
    parts = fio.split()
    if len(parts) <= 2:
        return True
    return False


def make_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(BACKUP_DIR, f'journal_{ts}_before_merge_teachers.db')
    shutil.copy2(DB_PATH, dst)
    print(f"[+] Бэкап: {dst}")
    return dst


def find_groups(conn):
    """
    Возвращает: {surname: [ {id, full_name, short_name, is_short}, ... ]}
    Только группы, где больше 1 записи.
    """
    rows = conn.execute(
        "SELECT id, full_name, short_name FROM teachers "
        "ORDER BY full_name"
    ).fetchall()

    groups = {}
    for r in rows:
        fio = (r['full_name'] or '').strip()
        if not fio:
            continue
        parts = fio.split()
        if not parts:
            continue
        surname = norm_surname(parts[0])
        groups.setdefault(surname, []).append({
            'id': r['id'],
            'full_name': fio,
            'short_name': (r['short_name'] or '').strip(),
            'is_short': is_short_form(fio),
        })

    return {s: g for s, g in groups.items() if len(g) > 1}


def print_groups(groups):
    if not groups:
        print("\n[=] Дублей по фамилии не найдено.")
        return
    print(f"\n[!] Найдено групп с одинаковой фамилией: {len(groups)}\n")
    for surname, items in sorted(groups.items()):
        print(f"  Фамилия: {surname!r}  ({len(items)} записей)")
        for it in items:
            tag = 'КОРОТКАЯ' if it['is_short'] else 'ПОЛНАЯ'
            print(f"    [{it['id']:4d}] {tag:9s}  {it['full_name']!r}"
                  f"  (short={it['short_name']!r})")
        print()


def plan_merges(groups):
    """
    Формирует список пар (keep_id, drop_ids).
    keep — самая полная (самая длинная) запись в группе,
    drop — все короткие записи.
    """
    plan = []
    for surname, items in groups.items():
        short = [i for i in items if i['is_short']]
        full = [i for i in items if not i['is_short']]
        if not short:
            continue  # нечего мержить
        if not full:
            # все короткие — оставляем самый короткий, остальные удаляем
            full = [min(short, key=lambda x: len(x['full_name']))]
            short = [s for s in short if s['id'] != full[0]['id']]

        # Если несколько полных — берём самую длинную
        keep = max(full, key=lambda x: len(x['full_name']))
        drop_ids = [s['id'] for s in short if s['id'] != keep['id']]
        if drop_ids:
            plan.append({
                'surname': surname,
                'keep': keep,
                'drop_ids': drop_ids,
            })
    return plan


def merge(conn, plan):
    total = 0
    for p in plan:
        keep_id = p['keep']['id']
        print(f"\n→ Слияние по фамилии {p['surname']!r}:")
        print(f"    Оставляем [{keep_id}] {p['keep']['full_name']!r}")
        for drop_id in p['drop_ids']:
            row = conn.execute(
                "SELECT full_name FROM teachers WHERE id = ?", (drop_id,)
            ).fetchone()
            drop_name = row['full_name'] if row else '???'
            print(f"    Удаляем  [{drop_id}] {drop_name!r}")

            # Обновляем ссылки
            for tbl, col in [
                ('schedule_lessons', 'teacher_id'),
                ('users', 'teacher_id'),
                ('teacher_journals', 'user_id'),
                ('teacher_hours', 'user_id'),
            ]:
                try:
                    conn.execute(
                        f"UPDATE {tbl} SET {col} = ? WHERE {col} = ?",
                        (keep_id, drop_id)
                    )
                except sqlite3.OperationalError:
                    pass

            conn.execute("DELETE FROM teachers WHERE id = ?", (drop_id,))
            total += 1

    conn.commit()
    print(f"\n[+] Удалено/слито: {total} записей")
    return total


def main():
    if not os.path.exists(DB_PATH):
        print(f"[!] БД не найдена: {DB_PATH}")
        sys.exit(1)

    do_merge = '--merge' in sys.argv
    auto_yes = '--yes' in sys.argv

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        groups = find_groups(conn)
        print_groups(groups)

        if not groups:
            return

        if not do_merge:
            print("Запустите с --merge, чтобы выполнить слияние.")
            print("  python merge_teachers.py --merge")
            return

        plan = plan_merges(groups)
        if not plan:
            print("\n[=] Плана для слияния нет (все записи уже уникальны).")
            return

        print(f"\nПлан слияния: {len(plan)} групп")
        if not auto_yes:
            answer = input("Выполнить? (yes/no): ").strip().lower()
            if answer not in ('yes', 'y', 'да'):
                print("Отменено.")
                return

        make_backup()
        merge(conn, plan)

    finally:
        conn.close()


if __name__ == '__main__':
    main()