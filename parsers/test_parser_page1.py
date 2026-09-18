"""
Тестовый парсер одной страницы PDF расписания.
Показывает, что удаётся извлечь.
НЕ сохраняет в БД — только выводит и сохраняет в TXT.

Запуск:
    python parsers/test_parser_page1.py "путь/к/файлу.pdf"
"""

import sys
import os
import re
import pdfplumber
from datetime import datetime


# Дни недели (в перевёрнутом виде, как извлекается из PDF)
DAYS_REVERSED = {
    'киньледеноП': ('Понедельник', 1),
    'кинротВ':     ('Вторник',     2),
    'адерС':       ('Среда',       3),
    'гревтеЧ':     ('Четверг',     4),
    'ацинтяП':     ('Пятница',     5),
    'атоббуС':     ('Суббота',     6),
}

DAY_ORDER = {
    'Понедельник': 1, 'Вторник': 2, 'Среда': 3,
    'Четверг': 4, 'Пятница': 5, 'Суббота': 6,
}


def reverse_string(s):
    return s[::-1] if s else s


def parse_time_pattern(word):
    """Проверяет, является ли слово временем пары (например, 8:30-9:30)"""
    return bool(re.match(r'^\d{1,2}:\d{2}-\d{1,2}:\d{2}$', word))


def parse_date_reversed(word):
    """'90.12' → '21.09'"""
    if not word:
        return None
    reversed_word = word[::-1]
    if re.match(r'^\d{2}\.\d{2}$', reversed_word):
        return reversed_word
    return None


def get_year_from_filename(filename):
    match = re.search(r'(\d{4})', filename)
    return int(match.group(1)) if match else datetime.now().year


def split_content(content):
    """
    Разбирает содержимое ячейки занятия на:
    - subject (предмет)
    - teacher (ФИО преподавателя, 'Фамилия И.О.')
    - lesson_type ('lecture' / 'practice' / 'independent' / 'exam')
    """
    if not content:
        return None, None, 'lecture'

    content = content.strip()

    # Тип занятия
    lesson_type = 'lecture'
    low = content.lower()
    if 'с/р' in low.replace(' ', ''):
        lesson_type = 'independent'
    elif 'экзамен' in low:
        lesson_type = 'exam'
    elif 'зачёт' in low or 'зачет' in low:
        lesson_type = 'diff_credit'

    # ФИО: "Фамилия И.О." / "Фамилия И.О," / "Фамилия И.О"
    fio_pattern = (
        r'([А-ЯЁ][а-яё\-]+'
        r'(?:\s+[А-ЯЁ][а-яё\-]+)?'
        r'\s+[А-ЯЁ]\.\s*[А-ЯЁ][.,]?)'
    )
    m = re.search(fio_pattern, content)
    teacher = m.group(1).strip() if m else None
    if teacher and teacher.endswith(','):
        teacher = teacher[:-1] + '.'

    # Предмет = content без ФИО и без типа
    subject = content
    if teacher:
        subject = subject.replace(teacher.rstrip('.'), '').replace(teacher, '')
    subject = re.sub(r'\bс\s*/\s*р\b', '', subject, flags=re.I)
    subject = re.sub(r'\bэкзамен\b', '', subject, flags=re.I)
    subject = re.sub(r'\bзач[её]т\b', '', subject, flags=re.I)
    subject = ' '.join(subject.split()).strip(' ,;.')
    subject = subject or None

    return subject, teacher, lesson_type


def parse_page(page, year, source_file=''):
    """Парсит одну страницу и возвращает структуру"""

    words = page.extract_words()
    if not words:
        return None

    # ============ ШАГ 1: маркеры столбцов из шапки ============
    # В шапке (top <= 22) ищем служебные слова-маркеры столбцов:
    #   'Дни'   — столбец дней недели
    #   'Часы'  — столбец времени
    #   'Ауд.'  — столбец аудитории
    # Это даёт точные x-координаты столбцов каждой группы.

    header = [w for w in words if 15 <= w['top'] <= 22]
    header.sort(key=lambda x: x['x0'])

    hour_markers = [w for w in header if w['text'] == 'Часы']
    room_markers = [w for w in header if w['text'] == 'Ауд.']

    if not hour_markers:
        return None

    # ============ ШАГ 2: группы и их столбцы ============
    groups_on_page = []
    for i, hour in enumerate(hour_markers):
        # Правая граница поиска — x следующего "Часы" (или бесконечность)
        next_hour_x = hour_markers[i+1]['x0'] if i+1 < len(hour_markers) else 1e9

        # Столбец аудитории — первый "Ауд." после "Часы" и до следующей "Часы"
        group_room = None
        for rm in room_markers:
            if hour['x0'] < rm['x0'] < next_hour_x:
                group_room = rm
                break

        # Заголовок группы — слова между "Часы" и следующим "Часы",
        # исключая служебные ("Недели", "Занятий", "Ауд.", "Дни", "Часы", "№")
        skip = {'Дни', 'Часы', 'Недели', 'Занятий', 'Ауд.', '№'}
        name_words = [
            w for w in header
            if hour['x0'] <= w['x0'] < next_hour_x
            and w['text'] not in skip
        ]
        name_words.sort(key=lambda x: x['x0'])
        name = ' '.join(w['text'] for w in name_words).strip()

        groups_on_page.append({
            'name': name or f'Группа {i+1}',
            'time_x_min': hour['x0'],
            'room_x_min': group_room['x0'] if group_room else None,
        })

    if not groups_on_page:
        return None

    # ============ ШАГ 3: границы блоков групп ============
    # Граница между группами = середина между правым краем столбца
    # аудитории предыдущей группы и левым краем столбца времени следующей.
    for i, g in enumerate(groups_on_page):
        if i == 0:
            g['x_min'] = 0
        else:
            prev = groups_on_page[i-1]
            prev_room_x1 = (prev['room_x_min'] + 20) if prev['room_x_min'] else prev['time_x_min'] + 250
            g['x_min'] = (prev_room_x1 + g['time_x_min']) / 2

        if i == len(groups_on_page) - 1:
            g['x_max'] = page.width
        else:
            nxt = groups_on_page[i+1]
            this_room_x1 = (g['room_x_min'] + 20) if g['room_x_min'] else g['time_x_min'] + 250
            g['x_max'] = (this_room_x1 + nxt['time_x_min']) / 2

    # ============ ШАГ 4: парсинг каждой группы ============
    result = []

    for group in groups_on_page:
        group_words = [
            w for w in words
            if group['x_min'] <= w['x0'] <= group['x_max']
        ]

        # --- Дни и даты ---
        days_found = {}
        for w in group_words:
            if w['text'] in DAYS_REVERSED:
                day_name, day_num = DAYS_REVERSED[w['text']]
                key = round(w['top'] / 15) * 15
                if key not in days_found:
                    days_found[key] = {
                        'day': day_name,
                        'day_num': day_num,
                        'date': None,
                        'top': w['top'],
                    }

        sorted_days = sorted(days_found.values(), key=lambda x: x['top'])

        # Привязка даты к диапазону [day.top - 40, next_day.top)
        for w in group_words:
            d = parse_date_reversed(w['text'])
            if not d:
                continue
            for i, day in enumerate(sorted_days):
                next_top = sorted_days[i+1]['top'] if i+1 < len(sorted_days) else 1e9
                if day['top'] - 40 <= w['top'] < next_top:
                    if day['date'] is None:
                        day['date'] = d
                    break

        # --- Времена пар: только в столбце времени группы ---
        time_x_min = group['time_x_min']
        times = [
            w for w in group_words
            if parse_time_pattern(w['text'])
            and abs(w['x0'] - time_x_min) < 25
        ]
        times.sort(key=lambda x: x['top'])

        # --- Границы столбца занятия и аудитории ---
        # Столбец занятия: от (time_x_min + 40) до room_x_min - 5
        x_cell_min = time_x_min + 40
        room_x_min = group['room_x_min'] if group['room_x_min'] else group['x_max'] - 60
        x_room_min = room_x_min - 5

        # Заголовки группы в шапке (top <= 22) — игнорируем
        # Также заголовок-подзаголовок под шапкой (top < 60) — если он не пересекается
        # с реальными парами. Определим первый день — всё, что ВЫШЕ первого дня
        # минус 30 pt, считаем заголовком и не пускаем в пары.
        # ВАЖНО: в этом PDF день недели может стоять НИЖЕ первой пары (см. debug:
        # "киньледеноП" на top=96.5, а первая пара Пн на top=39.8).
        # Поэтому используем min(top) всех времён как опорную точку.
        first_pair_top = times[0]['top'] if times else 0
        header_cutoff = first_pair_top - 5  # всё выше этого — заголовок

        # --- Извлекаем пары ---
        lessons = []
        for idx, time_word in enumerate(times):
            # Номер пары: цифра справа от времени (x ≈ time_x_min + 40)
            pair_num = None
            for w in group_words:
                if (abs(w['x0'] - (time_x_min + 40)) < 12
                        and abs(w['top'] - time_word['top']) < 5
                        and w['text'].isdigit()):
                    pair_num = int(w['text'])
                    break

            # Перерывы (без номера) — пропускаем
            if pair_num is None:
                continue

            # Границы ячейки: [середина_предыдущего, next.top - 3]
            if idx == 0:
                cell_top_min = time_word['top'] - 5
            else:
                prev_top = times[idx-1]['top']
                cell_top_min = (prev_top + time_word['top']) / 2

            if idx + 1 < len(times):
                cell_top_max = times[idx + 1]['top'] - 3
            else:
                cell_top_max = time_word['top'] + 12

            # День пары: ближайший предшествующий день
            # Учитываем, что день может быть НИЖЕ первой пары (top дня > top пары).
            # Логика: если день выше пары — это нормально (день = "шапка" дня).
            # Если день НИЖЕ пары — значит, это метка начала следующего дня,
            # и текущая пара относится к предыдущему дню.
            lesson_day = None
            for day in sorted_days:
                # Если день выше пары или немного ниже (в пределах 60 pt) — относим
                if day['top'] <= time_word['top'] + 60:
                    lesson_day = day
                else:
                    break
            if not lesson_day:
                lesson_day = sorted_days[0] if sorted_days else None
            if not lesson_day:
                continue

            # Слова ячейки
            cell_words = [
                w for w in group_words
                if x_cell_min <= w['x0'] <= group['x_max'] - 5
                and cell_top_min <= w['top'] <= cell_top_max
                and w['top'] >= header_cutoff
            ]
            cell_words.sort(key=lambda x: (round(x['top'] / 3) * 3, x['x0']))

            # Аудитория — только из правого столбца
            room_words = [w for w in cell_words if w['x0'] >= x_room_min]
            room = ' '.join(w['text'] for w in room_words).strip() if room_words else None

            # Содержимое занятия — левее аудитории
            content_words = [w for w in cell_words if w['x0'] < x_room_min]
            content = ' '.join(w['text'] for w in content_words).strip() if content_words else None

            # Разбор content
            subject, teacher, lesson_type = split_content(content)

            # Парсим время начала и конца
            time_parts = time_word['text'].split('-')
            time_start = time_parts[0] if len(time_parts) == 2 else time_word['text']
            time_end = time_parts[1] if len(time_parts) == 2 else ''

            lessons.append({
                'day': lesson_day['day'],
                'day_num': lesson_day['day_num'],
                'date': lesson_day['date'],
                'pair_number': pair_num,
                'time': time_word['text'],
                'time_start': time_start,
                'time_end': time_end,
                'content': content,
                'subject': subject,
                'teacher': teacher,
                'lesson_type': lesson_type,
                'room': room,
                'top': time_word['top'],
            })

        result.append({
            'group_name': group['name'],
            'x_range': (group['x_min'], group['x_max']),
            'days': sorted_days,
            'lessons': lessons,
        })

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
    source_file = os.path.basename(pdf_path)

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

            result = parse_page(page, year, source_file)
            if not result:
                log("❌ Не удалось распарсить страницу")
                return

            log(f"🎯 Найдено групп на странице: {len(result)}")
            log()

            total_lessons = 0
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
                total_lessons += len(group['lessons'])
                log()

                # Группируем по дням
                days_dict = {}
                for lesson in group['lessons']:
                    days_dict.setdefault(lesson['day'], []).append(lesson)

                for day_name in ['Понедельник', 'Вторник', 'Среда',
                                 'Четверг', 'Пятница', 'Суббота']:
                    if day_name not in days_dict:
                        continue

                    day_lessons = sorted(
                        days_dict[day_name],
                        key=lambda x: x['pair_number'] or 0
                    )
                    day_date = next(
                        (d['date'] for d in group['days'] if d['day'] == day_name),
                        None
                    )

                    log(f"--- {day_name} ({day_date or '?'}) ---")

                    for lesson in day_lessons:
                        log(f"  Пара {lesson['pair_number']} "
                            f"({lesson['time_start']}-{lesson['time_end']}):")
                        log(f"    Предмет:   {lesson['subject'] or '—'}")
                        log(f"    Препод:    {lesson['teacher'] or '—'}")
                        log(f"    Тип:       {lesson['lesson_type']}")
                        log(f"    Аудитория: {lesson['room'] or '—'}")
                        log(f"    Сырой текст: {lesson['content']!r}")
                        log()

                    log()

                log()

            log("=" * 70)
            log(f"ИТОГО пар на странице: {total_lessons}")
            log("=" * 70)
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