"""
Импорт преподавателей из Excel файла в таблицу teachers.
Читает 'Преподаватели.xlsx' из корня проекта.
"""

import sqlite3
import os
import re
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'journal.db')
EXCEL_FILE = os.path.join(BASE_DIR, 'Преподаватели.xlsx')


def make_short_name(full_name):
    """
    Преобразует 'Ватолина Ольга Альбертовна' → 'Ватолина О.А.'
    """
    if not full_name:
        return ''

    parts = full_name.strip().split()

    if len(parts) < 2:
        return full_name

    # Фамилия + инициалы
    surname = parts[0]
    initials = '.'.join([p[0].upper() for p in parts[1:] if p]) + '.'

    return f"{surname} {initials}"


def import_teachers():
    """Импорт преподавателей из Excel"""
    print("=" * 70)
    print("ИМПОРТ ПРЕПОДАВАТЕЛЕЙ")
    print("=" * 70)
    print()

    # Проверяем наличие файлов
    if not os.path.exists(EXCEL_FILE):
        print(f"❌ Файл не найден: {EXCEL_FILE}")
        print(f"   Поместите файл 'Преподаватели.xlsx' в корень проекта.")
        return False

    if not os.path.exists(DB_PATH):
        print(f"❌ БД не найдена: {DB_PATH}")
        print(f"   Сначала запустите миграцию: python migrations/migration_v3.py")
        return False

    # Читаем Excel
    print(f"📖 Чтение файла: {EXCEL_FILE}")
    try:
        df = pd.read_excel(EXCEL_FILE, header=None)
    except Exception as e:
        print(f"❌ Ошибка чтения Excel: {e}")
        return False

    # Первая строка — заголовок (№, ФИО)
    # Данные со второй строки
    # Колонка B (индекс 1) содержит ФИО

    print(f"   Строк в файле: {len(df)}")
    print()

    # Подключение к БД
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    added = 0
    skipped = 0
    errors = 0

    print("📥 Импорт преподавателей...")

    for idx, row in df.iterrows():
        # Пропускаем заголовок
        if idx == 0:
            continue

        # ФИО во второй колонке (индекс 1)
        try:
            full_name = row.iloc[1]
        except:
            continue

        if pd.isna(full_name):
            continue

        full_name = str(full_name).strip()

        # Пропускаем пустые
        if not full_name or len(full_name) < 5:
            continue

        # Проверяем, что это похоже на ФИО (2-3 слова, кириллица)
        words = full_name.split()
        if len(words) < 2 or len(words) > 4:
            print(f"   ⚠️  Пропущено (не похоже на ФИО): '{full_name}'")
            errors += 1
            continue

        # Формируем короткое имя
        short_name = make_short_name(full_name)

        # Проверяем, есть ли уже такой преподаватель
        existing = cursor.execute(
            "SELECT id FROM teachers WHERE full_name = ?",
            (full_name,)
        ).fetchone()

        if existing:
            skipped += 1
            continue

        # Добавляем
        try:
            cursor.execute('''
                INSERT INTO teachers (full_name, short_name, is_active)
                VALUES (?, ?, 1)
            ''', (full_name, short_name))
            added += 1
            print(f"   ✅ {full_name} ({short_name})")
        except Exception as e:
            print(f"   ❌ Ошибка добавления '{full_name}': {e}")
            errors += 1

    conn.commit()
    conn.close()

    print()
    print("=" * 70)
    print("✅ ИМПОРТ ЗАВЕРШЁН")
    print("=" * 70)
    print()
    print(f"📊 Статистика:")
    print(f"   Добавлено:  {added}")
    print(f"   Пропущено:  {skipped} (уже в базе)")
    print(f"   Ошибок:     {errors}")
    print()

    # Показать итоговый список
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    total = cursor.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
    conn.close()

    print(f"📋 Всего преподавателей в БД: {total}")
    print()

    return True


if __name__ == '__main__':
    success = import_teachers()
    exit(0 if success else 1)