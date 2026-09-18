"""
Отладочный скрипт: показывает все слова на первой странице PDF с координатами.
Результат сохраняется в parsers/output/debug_page1.txt

Запуск:
    python parsers/debug_page1.py "путь/к/файлу.pdf"
"""

import sys
import os
import pdfplumber


def main():
    if len(sys.argv) < 2:
        pdf_path = "1-4_kursy_s_21_09-26_09_2026.pdf"
    else:
        pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        print(f"ОШИБКА: Файл не найден: {pdf_path}")
        print()
        print("Укажите полный путь к PDF:")
        print(f'  python parsers/debug_page1.py "C:\\path\\to\\file.pdf"')
        return

    # Создаём папку для вывода
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'debug_page1.txt')

    with open(output_file, 'w', encoding='utf-8') as out:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            words = page.extract_words()

            # Сортируем по top (округлённому), потом по x0
            words.sort(key=lambda w: (round(w['top'] / 3) * 3, w['x0']))

            out.write(f"Файл: {pdf_path}\n")
            out.write(f"Всего слов: {len(words)}\n")
            out.write(f"Размер страницы: {page.width:.1f} x {page.height:.1f}\n")
            out.write("\n")
            out.write(f"{'x0':>7} {'x1':>7} {'top':>7} {'bot':>7} | text\n")
            out.write("-" * 80 + "\n")

            for w in words:
                out.write(f"{w['x0']:>7.1f} {w['x1']:>7.1f} {w['top']:>7.1f} {w['bottom']:>7.1f} | {w['text']}\n")

    print(f"Сохранено: {output_file}")
    print(f"Размер файла: {os.path.getsize(output_file) / 1024:.1f} КБ")
    print()
    print("Отправьте этот файл в чат.")


if __name__ == '__main__':
    main()