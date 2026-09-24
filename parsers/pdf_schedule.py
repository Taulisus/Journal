# parsers/pdf_schedule.py
# -*- coding: utf-8 -*-
"""
Парсер PDF-расписания. Извлечён из schedule_app.py, без UI.

Зависимость: pymupdf (fitz).

Основная функция:
    parse_schedule(pdf_path, teacher_pattern='.+') -> list[dict]

Возвращает список занятий:
    {
        'page':  int,
        'group': str | None,
        'day':   str | None,
        'date':  str | None,   # 'DD.MM'
        'pair':  int | None,
        'time':  str | None,   # 'HH:MM-HH:MM'
        'subject': str | None,
        'teacher': str,
        'room':  str | None,
    }

Отладка (ручной запуск):
    python -m parsers.pdf_schedule <pdf> [page_num]
    python -m parsers.pdf_schedule <pdf> --summary [teacher_pattern]
"""

import os
import re
import sys

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError as e:
        raise ImportError(
            "Не удалось импортировать PyMuPDF. Установите его командой:\n"
            "    python -m pip install pymupdf==1.24.14\n"
            f"Подробности: {e}"
        )


# ============================================================
#                 КОНСТАНТЫ
# ============================================================

DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
DAY_INDEX = {d: i for i, d in enumerate(DAYS)}

TIME_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})")
DATE_RE = re.compile(r"^\d{2}\.\d{2}$")
PAIR_RE = re.compile(r"^[1-7]$")
ROOM_RE = re.compile(
    r"^\d{1,3}[а-яА-Я]?$|^с/?р$|^Спорт\s*зал$|^Спортзал$|^Библ$|^акт\s*зал$|^актзал$|^Спорт$"
)

# Инициалы: «М.А.», «М. А.», «МА» (редко)
INITIALS_RE = re.compile(r"^[А-ЯЁ]\.?\s?[А-ЯЁ]\.?$")

STOP_HEADER = {
    "Дни", "Недели", "Часы", "Час", "Часъ", "Занятий",
    "Ауд.", "Ауд", "Ауд,", "Aуд.", "Aуд", "Ауд:",
}

_HEADER_BLACKLIST = {
    'дни', 'недели', 'часы', 'час', 'часъ', 'занятий', 'занятия', 'занятие',
    'ауд', 'ауд.', 'ауд,', 'ауд:', 'ayd', 'ayd.', 'ayd,',
    'предмет', 'преподаватель', 'группа', 'пара', 'время', 'день', 'дата',
}

# Слова, которые часто встречаются вторым словом в названии предмета.
# Если встречаем «Х Y», где Y из этого списка — это название предмета,
# а не «Фамилия Имя».
_SUBJECT_TAIL_WORDS = {
    'язык', 'родины', 'безопасности', 'литература', 'математика',
    'физика', 'информатика', 'история', 'культура', 'география',
    'биология', 'химия', 'обществознание', 'физическая', 'русский',
    'иностранный', 'английский', 'немецкий', 'обж', 'мхк', 'астрономия',
    'экономика', 'право', 'педагогика', 'психология', 'технология',
    'черчение', 'музыка', 'изо', 'физкультура',
}

_GP = (r"(?:Р\s*У\s*П\s*О|И\s*С\s*П?|Ю\s*Р|П\s*Д|Д\s*С|Т\s*Г|Т\s*Д|П\s*К\s*Д|Ф\s*С)")
GROUP_RE = re.compile(
    _GP + r"\s*-?\s*\d{1,2}(?:\s*[-/.]\s*\d{1,2})?(?:\s*[А-Я])?"
    r"(?:\s*[,;]\s*" + _GP + r"\s*-?\s*\d{1,2}(?:\s*[-/.]\s*\d{1,2})?(?:\s*[А-Я])?)*"
)
PREFIXES = ["РУПО", "ИСП", "ЮР", "ПД", "ДС", "ТГ", "ТД", "ПКД", "ФС", "ИС"]


def _normalize_prefixes(s):
    for p in PREFIXES:
        s = re.sub(r"\s*".join(re.escape(c) for c in p), p, s)
    return s


# ============================================================
#                 ФИЛЬТРЫ
# ============================================================

def _is_likely_teacher(text):
    """
    Похоже ли на ФИО преподавателя.
    Отбрасывает заголовки, числа, время, группы, длинные названия предметов.
    """
    if not text:
        return False

    t = text.strip()

    if len(t) < 4 or len(t) > 60:
        return False

    if re.match(r'^[\d\s\.\-:,]+$', t):
        return False

    if TIME_RE.search(t):
        return False

    if PAIR_RE.match(t):
        return False

    if DATE_RE.match(t):
        return False

    tl = t.lower().rstrip('.,;:')
    if tl in _HEADER_BLACKLIST:
        return False

    first_word = tl.split()[0] if tl.split() else ''
    if first_word.rstrip('.,;:') in _HEADER_BLACKLIST:
        return False

    if GROUP_RE.search(t):
        return False

    if not re.search(r'[А-Яа-яЁё]', t):
        return False

    words = t.split()
    if len(words) < 2:
        return False

    capitalized = sum(1 for w in words if w and w[0].isupper())
    if capitalized < 2:
        return False

    if len(words) > 4:
        return False

    has_initials = any(INITIALS_RE.match(w.rstrip('.,')) for w in words[1:])
    has_patronymic = any(
        w.lower().endswith(('вич', 'вна', 'чна', 'ична'))
        for w in words
    )

    if has_initials or has_patronymic:
        return True

    if len(words) == 2 and capitalized == 2:
        second = words[1].lower().rstrip('.,;:')
        if second in _SUBJECT_TAIL_WORDS:
            return False
        return True

    return False


def _is_likely_subject(text):
    """
    Похоже ли на название предмета.
    Не пропускает числа, время, группы.
    """
    if not text:
        return False

    t = text.strip()

    if len(t) < 3 or len(t) > 120:
        return False

    if re.match(r'^[\d\s\.\-:,]+$', t):
        return False

    if TIME_RE.search(t):
        return False

    if PAIR_RE.match(t):
        return False

    if DATE_RE.match(t):
        return False

    if GROUP_RE.search(t):
        return False

    if not re.search(r'[А-Яа-яЁё]', t):
        return False

    return True


# ============================================================
#                 ЯДРО ПАРСИНГА
# ============================================================

def get_words(page):
    return [
        {"x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3], "text": w[4]}
        for w in page.get_text("words")
    ]


def merge(cell, x_gap=2.5):
    """Склеивает слова с пробелами там, где между ними был зазор > x_gap."""
    if not cell:
        return ""
    parts = [cell[0]["text"]]
    px = cell[0]["x1"]
    for w in cell[1:]:
        if w["x0"] - px > x_gap:
            parts.append(" ")
        parts.append(w["text"])
        px = w["x1"]
    return "".join(parts)


def merge_no_spaces(cell):
    """Склеивает все слова в строку без пробелов (для времени)."""
    return "".join(w["text"] for w in cell)


def split_cells(words_sorted, x_gap=5.0):
    cells, cur, prev = [], [], None
    for w in words_sorted:
        if prev is not None and w["x0"] - prev > x_gap:
            cells.append(cur)
            cur = []
        cur.append(w)
        prev = w["x1"]
    if cur:
        cells.append(cur)
    return cells


def group_lines(words, y_tol=2.5):
    lines = []
    for w in sorted(words, key=lambda w: (w["y0"], w["x0"])):
        for ln in lines:
            if abs(ln["y0"] - w["y0"]) <= y_tol:
                ln["words"].append(w)
                break
        else:
            lines.append({"y0": w["y0"], "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        ys = [(w["y0"] + w["y1"]) / 2 for w in ln["words"]]
        ln["y_center"] = sum(ys) / len(ys)
    lines.sort(key=lambda l: l["y0"])
    return lines


def find_groups_on_page(page, words):
    top = [w for w in words if w["y0"] < 60]
    if not top:
        return []
    top.sort(key=lambda w: w["x0"])
    cells = split_cells(top, x_gap=15)

    groups = []
    for cell in cells:
        text = merge(cell, x_gap=3)
        text = re.sub(r"\s+", " ", text).strip()
        clean = text
        for s in STOP_HEADER:
            clean = re.sub(
                r"(?<![А-Яа-я])" + re.escape(s) + r"(?![А-Яа-я])", " ", clean
            )
        clean = re.sub(r"\s+", " ", clean).strip()
        if not clean:
            continue
        m = GROUP_RE.search(clean)
        if not m:
            continue
        g = _normalize_prefixes(m.group(0)).strip(" ,;.")
        groups.append({
            "group": g,
            "x0": cell[0]["x0"],
            "x1": cell[-1]["x1"],
            "x_center": (cell[0]["x0"] + cell[-1]["x1"]) / 2,
            "y_header": cell[0]["y0"],
        })
    return groups


def group_for_lesson(lesson_x, groups):
    if not groups:
        return None
    return min(groups, key=lambda g: abs(g["x_center"] - lesson_x))["group"]


def find_day_date(lines, lesson_x, lesson_y):
    day_candidates = []
    for ln in lines:
        for w in ln["words"]:
            if w["text"] not in DAYS:
                continue
            dx = lesson_x - w["x0"]
            if dx <= -20 or dx > 260:
                continue
            in_span = w["y0"] - 8 <= lesson_y <= w["y1"] + 8
            wy = (w["y0"] + w["y1"]) / 2
            day_candidates.append({
                "day": w["text"],
                "y0": w["y0"], "y1": w["y1"], "wy": wy,
                "in_span": in_span,
                "span_size": w["y1"] - w["y0"],
                "dy": abs(wy - lesson_y),
            })
    if not day_candidates:
        return None, None

    in_span = [c for c in day_candidates if c["in_span"]]
    if in_span:
        in_span.sort(key=lambda c: c["span_size"])
        best = in_span[0]
    else:
        day_candidates.sort(key=lambda c: c["dy"])
        best = day_candidates[0]

    date_candidates = []
    for ln in lines:
        for w in ln["words"]:
            if not DATE_RE.match(w["text"]):
                continue
            dx = lesson_x - w["x0"]
            if dx <= -20 or dx > 260:
                continue
            wy = (w["y0"] + w["y1"]) / 2
            if best["y0"] - 40 <= wy <= best["y1"] + 5:
                date_candidates.append({
                    "date": w["text"],
                    "dist": abs(wy - best["y0"]),
                })
    date = None
    if date_candidates:
        date_candidates.sort(key=lambda c: c["dist"])
        date = date_candidates[0]["date"]
    return best["day"], date


def find_pair_nearest(lines, y, lesson_x, max_dy=130):
    """
    Ищет номер пары.
    Логика: на строке со временем, в узкой полосе X (78..120).
    """
    best = None
    for ln in lines:
        dy = abs(ln["y_center"] - y)
        if dy > max_dy:
            continue

        joined = merge_no_spaces(ln["words"])
        if not TIME_RE.search(joined):
            continue

        for w in ln["words"]:
            if not PAIR_RE.match(w["text"]):
                continue
            if not (78 <= w["x0"] <= 120):
                continue
            if best is None or dy < best[0]:
                best = (dy, int(w["text"]))

    return best[1] if best else None


def find_time_nearest(lines, y, lesson_x, max_dy=130):
    """
    Ищет время пары. Время в PDF разбито на куски,
    поэтому склеиваем строку БЕЗ пробелов.
    """
    best = None
    for ln in lines:
        joined = merge_no_spaces(ln["words"])

        m = TIME_RE.search(joined)
        if not m:
            continue

        dy = abs(ln["y_center"] - y)
        if dy > max_dy:
            continue

        ln_x = ln["words"][0]["x0"]
        dx = lesson_x - ln_x
        if dx <= 10 or dx > 300:
            continue

        if best is None or dy < best[0]:
            best = (dy, f"{m.group(1)}:{m.group(2)}-{m.group(3)}:{m.group(4)}")

    return best[1] if best else None


def find_subject_above(lines, teacher_cell, max_dy=25):
    """
    Ищет название предмета выше ячейки с ФИО.
    max_dy увеличен до 25 — из-за того, что в некоторых записях
    предмет стоит на 20–25 px выше ФИО.
    """
    cx0, cx1 = teacher_cell[0]["x0"], teacher_cell[-1]["x1"]
    cy = sum((w["y0"] + w["y1"]) / 2 for w in teacher_cell) / len(teacher_cell)

    best = None
    for ln in lines:
        dy = cy - ln["y_center"]
        if not (2 < dy < max_dy):
            continue

        overlap = [w for w in ln["words"]
                   if not (w["x1"] < cx0 - 5 or w["x0"] > cx1 + 5)]
        if not overlap:
            continue

        s = merge(overlap)
        if not s:
            continue

        if not _is_likely_subject(s):
            continue

        if _is_likely_teacher(s):
            continue

        if best is None or dy < best[0]:
            best = (dy, s)

    return best[1] if best else None


def find_room_near(lines, teacher_cell, max_dy=10):
    """
    Ищет аудиторию правее ФИО на той же строке.

    Сначала — обычное одиночное слово по ROOM_RE.
    Если не находится, пробуем склеить соседние слова в строке
    (для случаев, когда «Спорт зал» разбит на отдельные буквы).
    """
    tx1 = teacher_cell[-1]["x1"]
    ty = sum((w["y0"] + w["y1"]) / 2 for w in teacher_cell) / len(teacher_cell)

    for ln in lines:
        if abs(ln["y_center"] - ty) > max_dy:
            continue

        # Слова правее ФИО в этой строке
        right = [w for w in ln["words"] if w["x0"] > tx1 + 2]
        if not right:
            continue

        # 1. Одиночное слово по ROOM_RE
        for w in right:
            t = w["text"].strip()
            if t and ROOM_RE.match(t):
                return t

        # 2. Склеенное (без пробелов) — для «Спорт зал» и подобных
        glued = "".join(w["text"] for w in right)
        glued = glued.strip()
        if glued and ROOM_RE.match(glued):
            return glued

        # 3. Склеенное (с пробелами) — для «акт зал», «с/р»
        spaced = merge(right, x_gap=3).strip()
        if spaced and ROOM_RE.match(spaced):
            return spaced

    return None

    # Склеиваем по X — в одну или несколько ячеек
    right_words.sort(key=lambda w: (w["y0"], w["x0"]))
    cells = split_cells(right_words, x_gap=8)

    # Ищем первую ячейку, подходящую под ROOM_RE
    for cell in cells:
        glued = "".join(w["text"] for w in cell)
        spaced = merge(cell, x_gap=3)
        for cand in (glued, spaced):
            cand_clean = cand.strip()
            if not cand_clean:
                continue
            if ROOM_RE.match(cand_clean):
                return cand_clean

    return None


def extract(pdf_path, pattern):
    pat = re.compile(pattern, re.IGNORECASE)
    doc = fitz.open(pdf_path)
    lessons = []
    for pno in range(len(doc)):
        page = doc[pno]
        words = get_words(page)
        if not words:
            continue

        groups = find_groups_on_page(page, words)
        if not groups:
            continue

        lines = group_lines(words)
        for ln in lines:
            cells = split_cells(ln["words"], x_gap=5)
            for cell in cells:
                ctext = merge(cell)
                if not pat.search(ctext):
                    continue

                if not _is_likely_teacher(ctext):
                    continue

                cx = (cell[0]["x0"] + cell[-1]["x1"]) / 2
                cy = sum((w["y0"] + w["y1"]) / 2 for w in cell) / len(cell)
                group = group_for_lesson(cx, groups)
                day, date = find_day_date(lines, cx, cy)
                lessons.append({
                    "page": pno + 1,
                    "group": group,
                    "day": day,
                    "date": date,
                    "pair": find_pair_nearest(lines, cy, cx),
                    "time": find_time_nearest(lines, cy, cx),
                    "subject": find_subject_above(lines, cell),
                    "teacher": ctext,
                    "room": find_room_near(lines, cell),
                })
    return lessons


def dedup(lessons):
    seen, out = set(), []
    for l in lessons:
        k = (l["page"], l["group"], l["day"], l["pair"],
             l["time"], l["room"], l["teacher"])
        if k in seen:
            continue
        seen.add(k)
        out.append(l)
    return out


# ============================================================
#                 ДОПОЛНЕНИЕ ВРЕМЕНИ ИЗ КОНФИГА
# ============================================================

def _fill_time_from_config(lessons):
    """
    Для занятий, у которых время не найдено в PDF,
    подставляет его из Config.TIME_INTERVALS_BY_DAY
    по номеру пары и дню недели.

    Также переводит формат '0830-0930' → '08:30-09:30'.
    """
    try:
        from config import Config
    except ImportError:
        return lessons

    # {weekday: {pair_number: 'HH:MM-HH:MM'}}
    pair_time_map = {}
    for weekday, intervals in Config.TIME_INTERVALS_BY_DAY.items():
        pair_time_map[weekday] = {}
        for idx, (value, _label) in enumerate(intervals, start=1):
            pair_time_map[weekday][idx] = _norm_interval(value)

    day_to_weekday = {
        'Понедельник': 0, 'Вторник': 1, 'Среда': 2,
        'Четверг': 3, 'Пятница': 4, 'Суббота': 5,
    }

    filled = 0
    for l in lessons:
        if l.get('time'):
            continue
        wd = day_to_weekday.get(l.get('day'))
        pair = l.get('pair')
        if wd is None or not pair:
            continue
        t = pair_time_map.get(wd, {}).get(pair)
        if not t:
            continue
        l['time'] = t
        filled += 1

    if filled:
        print(f"[pdf_schedule] Подставлено время из Config для {filled} занятий")

    return lessons


def _norm_interval(value):
    """'0830-0930' → '08:30-09:30'. Если уже с двоеточиями — оставляет как есть."""
    if not value:
        return value
    if ':' in value:
        return value
    m = re.match(r'^(\d{2})(\d{2})-(\d{2})(\d{2})$', value)
    if not m:
        return value
    return f"{m.group(1)}:{m.group(2)}-{m.group(3)}:{m.group(4)}"


def parse_schedule(pdf_path, teacher_pattern=r".+"):
    """
    Основная точка входа.

    pdf_path         — путь к PDF
    teacher_pattern  — regex по ФИО преподавателя (без учёта регистра)

    Возвращает список dict-ов (см. docstring модуля).
    """
    lessons = dedup(extract(pdf_path, teacher_pattern))
    lessons = _fill_time_from_config(lessons)
    return lessons


# ============================================================
#                 ОТЛАДКА
# ============================================================

def debug_dump_page(pdf_path, page_num=1,
                    output_path='parsers/output/debug_page.txt'):
    """Выгружает все слова страницы с координатами в текстовый файл."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = fitz.open(pdf_path)
    if page_num < 1 or page_num > len(doc):
        print(f"Страницы {page_num} нет. Всего страниц: {len(doc)}")
        return

    page = doc[page_num - 1]
    words = page.get_text("words")

    try:
        pw = page.rect.width
        ph = page.rect.height
    except AttributeError:
        rect = page.mediabox
        pw = rect.width
        ph = rect.height

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# Файл: {pdf_path}\n")
        f.write(f"# Страница: {page_num} из {len(doc)}\n")
        f.write(f"# Размер страницы: {pw:.1f} x {ph:.1f}\n")
        f.write(f"# Слов: {len(words)}\n")
        f.write("#\n")
        f.write("# x0      y0      x1      y1      text\n")
        f.write("# " + "-" * 70 + "\n")
        for w in words:
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
            f.write(f"{x0:7.1f} {y0:7.1f} {x1:7.1f} {y1:7.1f}  {text!r}\n")

    print(f"Дамп сохранён в {output_path}")
    print(f"Строк: {len(words)}")


def debug_parse_summary(pdf_path, teacher_pattern=r".+"):
    """Быстрый анализ: сколько занятий и у скольких есть каждое поле."""
    lessons = parse_schedule(pdf_path, teacher_pattern)

    total = len(lessons)
    with_time = sum(1 for l in lessons if l.get('time'))
    with_pair = sum(1 for l in lessons if l.get('pair'))
    with_subject = sum(1 for l in lessons if l.get('subject'))
    with_room = sum(1 for l in lessons if l.get('room'))
    with_group = sum(1 for l in lessons if l.get('group'))
    with_day = sum(1 for l in lessons if l.get('day'))

    print(f"Всего занятий:           {total}")
    print(f"  с группой:             {with_group}")
    print(f"  с днём:                {with_day}")
    print(f"  с парой:               {with_pair}")
    print(f"  со временем:           {with_time}")
    print(f"  с предметом:           {with_subject}")
    print(f"  с аудиторией:          {with_room}")

    return lessons


# ============================================================
#                 CLI
# ============================================================

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python -m parsers.pdf_schedule <pdf> [page_num]")
        print("  python -m parsers.pdf_schedule <pdf> --summary [teacher_pattern]")
        print()
        print("Примеры:")
        print("  python -m parsers.pdf_schedule schedule.pdf 1")
        print('  python -m parsers.pdf_schedule schedule.pdf --summary')
        print('  python -m parsers.pdf_schedule schedule.pdf --summary "Ваганов"')
        sys.exit(1)

    pdf = sys.argv[1]

    if not os.path.isfile(pdf):
        print(f"Файл не найден: {pdf}")
        sys.exit(1)

    if len(sys.argv) >= 3 and sys.argv[2] == '--summary':
        pattern = sys.argv[3] if len(sys.argv) > 3 else r".+"
        debug_parse_summary(pdf, pattern)
    else:
        pg = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        debug_dump_page(
            pdf,
            page_num=pg,
            output_path=f'parsers/output/debug_page{pg}.txt',
        )