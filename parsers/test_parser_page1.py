"""
Тестовый парсер одной страницы PDF расписания.
Показывает, что удаётся извлечь.
НЕ сохраняет в БД — только выводит и сохраняет в TXT.

Запуск:
    python parsers/test_parser_page1.py "путь/к/файлу.pdf"
"""

import sys
import os
import pdfplumber
from datetime import datetime
import re


# Дни недели (в перевёрнутом виде, как извлекается из PDF)
DAYS_REVERSED = {
    'киньледеноП': 'Понедельник',
    'кинротВ': 'Вторник',
    'адерС': 'Среда',
    'гревтеЧ': 'Четверг',
    'ацинтяП': 'Пятница',
    'атоббуС': 'Суббота',
}


def reverse_string(s):
    """Переворачивает строку (для декодирования перевёрнутого текста)"""
    if not s:
        return s
    return s[::-1]


def parse_time_pattern(word):
    """Проверяет, является ли слово временем пары (например, 8:30-9:30)"""
    return bool(re.match(r'^\d{1,2}:\d{2}-\d{1,2}:\d{2}$', word))


def parse_date_reversed(word):
    """
    Парсит перевёрнутую дату.
    '90.12' → '21.09'
    """
    if not word:
        return None

    reversed_word = word[::-1]

    if re.match(r'^\d{2}\.\d{2}$', reversed_word):
        return reversed_word

    return None


def get_year_from_filename(filename):
    """Извлекает год из имени файла"""
    match = re.search(r'(\d{4})', filename)
    if match:
        return int(match.group(1))
    return datetime.now().year


def parse_page(page, year):
    """Парсит одну страницу и возвращает структуру"""

    words = page.extract_words()
    if not words:
        return None

    # ============ ШАГ 1: Найти заголовки групп ============
    # Заголовки групп находятся в top ≈ 20 (шапка страницы)
    # Собираем слова-кандидаты в заголовке

    header_words = [w for w in words if 15 <= w['top'] <= 25]

    # Фильтруем служебные слова
    skip_words = {'Ауд.', 'Часы', 'Занятий', 'Дни', 'Недели', '№'}

    group_header_words = []
    for w in header_words:
        if w['x0'] > 100 and w['text'] not in skip_words:
            group_header_words.append(w)

    # Сортируем по x0
    group_header_words.sort(key=lambda x: x['x0'])

    # Группируем в блоки (если разрыв > 30pt — новая группа)
    group_blocks = []
    current_block = []
    last_x1 = 0

    for w in group_header_words:
        if current_block and (w['x0'] - last_x1) > 30:
            group_blocks.append(current_block)
            current_block = []
        current_block.append(w)
        last_x1 = w['x1']

    if current_block:
        group_blocks.append(current_block)

    # Формируем данные групп
    groups_on_page = []
    for block in group_blocks:
        if not block:
            continue
        name = ' '.join(w['text'] for w in block)
        x_start = block[0]['x0']
        x_end = block[-1]['x1']
        groups_on_page.append({
            'name': name,
            'x_start': x_start,
            'x_end': x_end,
        })

    # ============ ШАГ 2: Определить границы блоков групп ============
    if len(groups_on_page) == 1:
        groups_on_page[0]['x_min'] = 0
        groups_on_page[0]['x_max'] = page.width
    else:
        for i, g in enumerate(groups_on_page):
            if i == 0:
                # Первая: от 0 до середины между ней и следующей
                g['x_min'] = 0
                g['x_max'] = (g['x_start'] + groups_on_page[i+1]['x_start']) / 2
            elif i == len(groups_on_page) - 1:
                # Последняя: от середины до конца
                g['x_min'] = (groups_on_page[i-1]['x_start'] + g['x_start']) / 2
                g['x_max'] = page.width
            else:
                # Средняя
                g['x_min'] = (groups_on_page[i-1]['x_start'] + g['x_start']) / 2
                g['x_max'] = (g['x_start'] + groups_on_page[i+1]['x_start']) / 2

    # ============ ШАГ 3: Парсить каждую группу ============
    result = []

    for group in groups_on_page:
        group_data = {
            'group_name': group['name'],
            'x_range': (group['x_min'], group['x_max']),
            'days': [],
            'lessons': [],
        }

        # Фильтруем слова по x-диапазону
        group_words = [
            w for w in words
            if group['x_min'] <= w['x0'] <= group['x_max']
        ]

        # ============ Ищем дни недели ============
        days_found = {}  # top_key → {day, date, top}

        for w in group_words:
            # Проверяем день недели (в перевёрнутом виде)
            day_name = None
            if w['text'] in DAYS_REVERSED:
                day_name = DAYS_REVERSED[w['text']]
            else:
                reversed_text = reverse_string(w['text'])
                if reversed_text in DAYS_REVERSED.values():
                    day_name = reversed_text

            if day_name:
                top_key = round(w['top'] / 15) * 15
                if top_key not in days_found:
                    days_found[top_key] = {
                        'day': day_name,
                        'date': None,
                        'top': w['top'],
                    }

        # Ищем даты (перевёрнутые, например '90.12' → '21.09')
        for w in group_words:
            date_parsed = parse_date_reversed(w['text'])
            if date_parsed:
                # Ищем ближайший день по top
                best_key = None
                best_diff = 999
                for top_key, day_info in days_found.items():
                    diff = abs(day_info['top'] - w['top'])
                    if diff < best_diff:
                        best_diff = diff
                        best_key = top_key

                if best_key is not None and best_diff < 30:
                    days_found[best_key]['date'] = date_parsed

        sorted_days = sorted(days_found.values(), key=lambda x: x['top'])

        # ============ Находим времена пар ============
        times = []
        for w in group_words:
            if parse_time_pattern(w['text']) and w['x0'] < 100:
                times.append(w)

        # Сортируем времена по top
        times.sort(key=lambda x: x['top'])

        # ============ Для каждой пары извлекаем содержимое ============
        lessons = []

        for time_word in times:
            # Ищем номер пары (справа от времени, x0 ≈ 83)
            pair_num = None
            for w in group_words:
                if (abs(w['x0'] - 83) < 8 and
                    abs(w['top'] - time_word['top']) < 5 and
                    w['text'].isdigit()):
                    pair_num = int(w['text'])
                    break

            # Определяем к какому дню относится пара
            lesson_day = None
            for day in sorted_days:
                if day['top'] <= time_word['top'] + 5:
                    lesson_day = day
                else:
                    break

            if not lesson_day:
                continue

            # Извлекаем содержимое ячейки занятия
            cell_x_min = 100
            cell_x_max = group['x_max'] - 5
            cell_top_min = time_word['top'] - 15
            cell_top_max = time_word['top'] + 12

            cell_words = [
                w for w in group_words
                if (cell_x_min <= w['x0'] <= cell_x_max and
                    cell_top_min <= w['top'] <= cell_top_max)
            ]

            # Сортируем по top, потом по x0
            cell_words.sort(key=lambda x: (round(x['top'] / 3) * 3, x['x0']))

            # Извлекаем текст ячейки
            cell_text_parts = [w['text'] for w in cell_words]
            cell_text = ' '.join(cell_text_parts)

            # Аудитория — справа (x0 > 265)
            room = None
            room_words = [w for w in cell_words if w['x0'] > 265]
            if room_words:
                room = ' '.join([w['text'] for w in room_words])

            lessons.append({
                'day': lesson_day['day'],
                'date': lesson_day['date'],
                'pair_number': pair_num,
                'time': time_word['text'],
                'cell_text': cell_text,
                'room': room,
                'top': time_word['top'],
            })

        group_data['days'] = sorted_days
        group_data['lessons'] = lessons
        result.append(group_data)

    return result


def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print('  python parsers/test_parser_page1.py "путь/к/файлу.pdf"')
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        print(f"❌ Файл не найден: {pdf_path}")
        sys.exit(1)

    year = get_year_from_filename(os.path.basename(pdf_path))

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(output_dir, f'parse_{base_name}_{timestamp}.txt')

    with open(output_file, 'w', encoding='utf-8') as out:
        def log(msg=''):
            print(msg)
            out.write(msg + '\n')

        log("=" * 70)
        log(f"ТЕСТОВЫЙ ПАРСИНГ PDF")
        log(f"Файл: {pdf_path}")
        log(f"Год: {year}")
        log(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log("=" * 70)
        log()

        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]

            log(f"📄 Анализ СТРАНИЦЫ 1 из {len(pdf.pages)}")
            log()

            result = parse_page(page, year)

            if not result:
                log("❌ Не удалось распарсить страницу")
                return

            log(f"🎯 Найдено групп на странице: {len(result)}")
            log()

            for group in result:
                log("=" * 70)
                log(f"ГРУППА: {group['group_name']}")
                log(f"X-диапазон: {group['x_range'][0]:.1f} — {group['x_range'][1]:.1f}")
                log("=" * 70)
                log()

                log(f"📅 Дней недели: {len(group['days'])}")
                for day in group['days']:
                    log(f"   • {day['day']:<15} {day['date'] or '?':<10} (top={day['top']:.1f})")
                log()

                log(f"📚 Всего пар: {len(group['lessons'])}")
                log()

                # Группируем по дням
                days_dict = {}
                for lesson in group['lessons']:
                    day = lesson['day']
                    if day not in days_dict:
                        days_dict[day] = []
                    days_dict[day].append(lesson)

                for day_name in ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']:
                    if day_name not in days_dict:
                        continue

                    day_lessons = sorted(days_dict[day_name], key=lambda x: x['pair_number'] or 0)
                    day_date = next((d['date'] for d in group['days'] if d['day'] == day_name), None)

                    log(f"--- {day_name} ({day_date or '?'}) ---")

                    for lesson in day_lessons:
                        pair_num = lesson['pair_number'] or '?'
                        time = lesson['time']
                        cell = lesson['cell_text']
                        room = lesson['room'] or '—'

                        log(f"  Пара {pair_num} ({time}):")
                        log(f"    Ячейка: {cell}")
                        log(f"    Аудитория: {room}")
                        log()

                    log()

                log()

        log()
        log("=" * 70)
        log(f"✅ ГОТОВО!")
        log(f"📁 Файл сохранён: {output_file}")
        log("=" * 70)

    print()
    print(f"📁 Файл: {output_file}")
    print("Отправьте его для анализа.")


if __name__ == '__main__':
    main()