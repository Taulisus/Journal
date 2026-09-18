"""
Тестовый скрипт: извлекает структуру PDF и сохраняет в TXT-файл.
НЕ сохраняет ничего в БД, только выводит структуру.

Запуск:
    python parsers/inspect_pdf.py "путь/к/файлу.pdf"

Результат сохраняется в:
    parsers/output/inspect_<имя_файла>.txt
"""

import sys
import os
import pdfplumber
from datetime import datetime


def inspect_pdf(pdf_path, output_path):
    """Показывает структуру PDF и сохраняет в файл"""

    with open(output_path, 'w', encoding='utf-8') as out:
        def log(msg=''):
            """Вывод и в консоль, и в файл"""
            print(msg)
            out.write(msg + '\n')

        if not os.path.exists(pdf_path):
            log(f"❌ Файл не найден: {pdf_path}")
            return False

        log("=" * 70)
        log(f"ИНСПЕКЦИЯ PDF: {os.path.basename(pdf_path)}")
        log(f"Дата анализа: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log("=" * 70)
        log()

        with pdfplumber.open(pdf_path) as pdf:
            log(f"📄 Всего страниц: {len(pdf.pages)}")
            log()

            # Анализируем все страницы
            for page_num in range(len(pdf.pages)):
                page = pdf.pages[page_num]

                log("=" * 70)
                log(f"СТРАНИЦА {page_num + 1}")
                log("=" * 70)
                log(f"Размер: {page.width:.1f} x {page.height:.1f}")
                log()

                # 1. Пробуем извлечь таблицы
                log("📊 ПОПЫТКА ИЗВЛЕЧЬ ТАБЛИЦЫ:")
                log("-" * 70)

                try:
                    tables = page.extract_tables()
                except Exception as e:
                    log(f"❌ Ошибка extract_tables(): {e}")
                    tables = None

                if tables:
                    log(f"Найдено таблиц: {len(tables)}")
                    log()

                    for t_idx, table in enumerate(tables):
                        log(f"--- Таблица {t_idx + 1} ---")
                        log(f"Строк: {len(table)}")
                        if table and table[0]:
                            log(f"Колонок: {len(table[0])}")
                        log()

                        # Показываем все строки таблицы
                        for r_idx, row in enumerate(table):
                            log(f"Строка {r_idx}:")
                            for c_idx, cell in enumerate(row):
                                if cell:
                                    cell_str = str(cell).replace('\n', ' \\n ')[:200]
                                    log(f"  [{c_idx}] {cell_str}")
                                else:
                                    log(f"  [{c_idx}] (пусто)")
                            log()

                        log()
                else:
                    log("❌ Таблицы не найдены через extract_tables()")
                    log()

                    # Пробуем extract_text
                    log("📝 ПОПЫТКА ЧЕРЕЗ extract_text():")
                    log("-" * 70)
                    try:
                        text = page.extract_text()
                        if text:
                            log(text[:5000])
                        else:
                            log("❌ Текст тоже не извлекается")
                    except Exception as e:
                        log(f"❌ Ошибка extract_text(): {e}")

                log()

                # 2. Информация о словах
                try:
                    words = page.extract_words()
                    log(f"📝 Слов на странице: {len(words)}")

                    if words:
                        log()
                        log("Первые 30 слов (с координатами):")
                        log("-" * 70)
                        for w in words[:30]:
                            log(f"  x0={w['x0']:.1f}, top={w['top']:.1f}, text='{w['text']}'")
                except Exception as e:
                    log(f"❌ Ошибка extract_words(): {e}")

                log()
                log()

            # Итоговая статистика
            log("=" * 70)
            log("ОБЩАЯ СТАТИСТИКА")
            log("=" * 70)

            total_tables = 0
            total_words = 0
            pages_with_tables = 0

            for page in pdf.pages:
                try:
                    tables = page.extract_tables()
                    if tables:
                        total_tables += len(tables)
                        pages_with_tables += 1
                except:
                    pass

                try:
                    total_words += len(page.extract_words())
                except:
                    pass

            log(f"Всего страниц:            {len(pdf.pages)}")
            log(f"Страниц с таблицами:      {pages_with_tables}")
            log(f"Всего таблиц:             {total_tables}")
            log(f"Всего слов:               {total_words}")
            log()

            # Размер PDF
            log(f"Размер PDF:               {os.path.getsize(pdf_path) / 1024:.1f} КБ")
            log()

    return True


def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print('  python parsers/inspect_pdf.py "путь/к/файлу.pdf"')
        print()
        print("Пример:")
        print('  python parsers/inspect_pdf.py "1-4_kursy_s_21_09-26_09_2026.pdf"')
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        print(f"❌ Файл не найден: {pdf_path}")
        sys.exit(1)

    # Создаём папку для вывода
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)

    # Имя выходного файла
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(output_dir, f'inspect_{base_name}_{timestamp}.txt')

    print(f"📄 Анализ PDF: {pdf_path}")
    print(f"📝 Результат: {output_file}")
    print()

    success = inspect_pdf(pdf_path, output_file)

    if success:
        print()
        print("=" * 70)
        print(f"✅ ГОТОВО!")
        print(f"📁 Файл сохранён: {output_file}")
        print(f"📊 Размер файла: {os.path.getsize(output_file) / 1024:.1f} КБ")
        print("=" * 70)
        print()
        print("Отправьте этот файл для анализа.")


if __name__ == '__main__':
    main()