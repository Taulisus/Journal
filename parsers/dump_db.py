"""
Дамп содержимого БД для анализа.
Сохраняет всё в parsers/output/db_dump.txt

Запуск:
    python parsers/dump_db.py
"""

import sqlite3
import os
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'journal.db')


def dump_db():
    output_dir = os.path.join(BASE_DIR, 'parsers', 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'db_dump.txt')

    if not os.path.exists(DB_PATH):
        print(f"❌ БД не найдена: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    with open(output_file, 'w', encoding='utf-8') as out:
        def log(msg=''):
            print(msg)
            out.write(msg + '\n')

        log("=" * 80)
        log("ДАМП БАЗЫ ДАННЫХ")
        log(f"БД: {DB_PATH}")
        log(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log("=" * 80)

        # ============ Список всех таблиц ============
        log()
        log("=" * 80)
        log("СПИСОК ТАБЛИЦ")
        log("=" * 80)
        tables = [
            row['name'] for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'journal_%' "
                "ORDER BY name"
            )
        ]
        for t in tables:
            log(f"  • {t}")

        # Динамические таблицы journal_*
        journal_tables = [
            row['name'] for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'journal_%' ORDER BY name"
            )
        ]
        log(f"\n  Динамических журналов (journal_*): {len(journal_tables)}")

        # ============ Academic years ============
        log()
        log("=" * 80)
        log("УЧЕБНЫЕ ГОДЫ (academic_years)")
        log("=" * 80)
        for row in cur.execute("SELECT * FROM academic_years ORDER BY id"):
            log(f"  id={row['id']:<3} | {row['name']:<12} | "
                f"{row['start_date']} — {row['end_date']} | "
                f"is_current={row['is_current']}")

        # ============ Groups ============
        log()
        log("=" * 80)
        log("ГРУППЫ (groups)")
        log("=" * 80)
        groups = cur.execute("SELECT * FROM groups ORDER BY name").fetchall()
        log(f"Всего групп: {len(groups)}\n")
        for row in groups:
            code = row['code'] if 'code' in row.keys() else ''
            year = row['academic_year_id'] if 'academic_year_id' in row.keys() else ''
            log(f"  id={row['id']:<4} | {row['name']:<40} | "
                f"code={code} | year={year}")

        # ============ Group aliases ============
        log()
        log("=" * 80)
        log("АЛИАСЫ ГРУПП (group_aliases)")
        log("=" * 80)
        aliases = cur.execute(
            "SELECT ga.*, g.name AS group_name FROM group_aliases ga "
            "LEFT JOIN groups g ON ga.group_id = g.id ORDER BY ga.alias"
        ).fetchall()
        log(f"Всего алиасов: {len(aliases)}\n")
        for row in aliases:
            log(f"  id={row['id']:<4} | alias='{row['alias']}' → "
                f"group_id={row['group_id']} ({row['group_name']})")

        # ============ Teachers ============
        log()
        log("=" * 80)
        log("ПРЕПОДАВАТЕЛИ (teachers)")
        log("=" * 80)
        teachers = cur.execute("SELECT * FROM teachers ORDER BY short_name").fetchall()
        log(f"Всего преподавателей: {len(teachers)}\n")
        for row in teachers:
            log(f"  id={row['id']:<4} | short='{row['short_name']}' | "
                f"full='{row['full_name']}' | active={row['is_active']}")

        # ============ Rooms ============
        log()
        log("=" * 80)
        log("АУДИТОРИИ (rooms)")
        log("=" * 80)
        rooms = cur.execute("SELECT * FROM rooms ORDER BY name").fetchall()
        log(f"Всего аудиторий: {len(rooms)}\n")
        for row in rooms:
            log(f"  id={row['id']:<4} | '{row['name']}' | "
                f"building='{row['building']}' | type={row['room_type']}")

        # ============ Subjects ============
        log()
        log("=" * 80)
        log("ПРЕДМЕТЫ (subjects) — первые 50")
        log("=" * 80)
        subjects = cur.execute("SELECT * FROM subjects ORDER BY name").fetchall()
        log(f"Всего предметов: {len(subjects)}\n")
        for row in subjects[:50]:
            log(f"  id={row['id']:<4} | {row['name']}")
        if len(subjects) > 50:
            log(f"  ... и ещё {len(subjects) - 50}")

        # ============ schedule_lessons ============
        log()
        log("=" * 80)
        log("РАСПИСАНИЕ (schedule_lessons)")
        log("=" * 80)
        try:
            cnt = cur.execute("SELECT COUNT(*) FROM schedule_lessons").fetchone()[0]
            log(f"Всего записей: {cnt}\n")

            rows = cur.execute('''
                SELECT sl.*, g.name AS group_name, s.name AS subject_name,
                       t.short_name AS teacher_short, r.name AS room_name
                FROM schedule_lessons sl
                LEFT JOIN groups g ON sl.group_id = g.id
                LEFT JOIN subjects s ON sl.subject_id = s.id
                LEFT JOIN teachers t ON sl.teacher_id = t.id
                LEFT JOIN rooms r ON sl.room_id = r.id
                ORDER BY sl.date, sl.pair_number
                LIMIT 30
            ''').fetchall()
            if rows:
                log("Первые 30 записей:\n")
                for row in rows:
                    log(f"  {row['date']} пара {row['pair_number']} | "
                        f"{row['group_name']} | {row['subject_name']} | "
                        f"{row['teacher_short'] or row['teacher_name_raw']} | "
                        f"ауд.{row['room_name'] or row['room_name_raw']} | "
                        f"type={row['lesson_type']}")
        except Exception as e:
            log(f"  ⚠️ Ошибка: {e}")

        # ============ Структура schedule_lessons ============
        log()
        log("=" * 80)
        log("СТРУКТУРА schedule_lessons")
        log("=" * 80)
        for row in cur.execute("PRAGMA table_info(schedule_lessons)"):
            log(f"  {row['name']:<25} {row['type']:<12} "
                f"notnull={row['notnull']} default={row['dflt_value']}")

        # ============ Источники расписания ============
        log()
        log("=" * 80)
        log("ИСТОЧНИКИ РАСПИСАНИЯ (source_file) — уникальные")
        log("=" * 80)
        try:
            sources = cur.execute(
                "SELECT source_file, COUNT(*) as cnt FROM schedule_lessons "
                "GROUP BY source_file"
            ).fetchall()
            for row in sources:
                log(f"  '{row['source_file']}' — {row['cnt']} записей")
        except Exception as e:
            log(f"  ⚠️ Ошибка: {e}")

        log()
        log("=" * 80)
        log(f"✅ ГОТОВО! Файл: {output_file}")
        log("=" * 80)

    conn.close()
    print(f"\n📁 Файл: {output_file}")
    print("Отправь его в чат.")


if __name__ == '__main__':
    dump_db()