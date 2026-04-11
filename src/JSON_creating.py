import json
import re


def parse_schedule_to_json(markdown_text):
    """
    Парсит расписание из markdown в JSON формат
    Более гибкая версия
    """
    schedule = []
    lines = markdown_text.split('\n')

    # Ищем начало таблицы разными способами
    table_start = -1
    header_found = False

    for i, line in enumerate(lines):
        # Проверяем разные варианты заголовков
        if ('Д/Н' in line or 'День' in line) and ('пара' in line or '№' in line) and (
                'дисциплина' in line or 'предмет' in line):
            table_start = i + 1  # Начинаем со следующей строки
            header_found = True
            print(f"Найден заголовок таблицы в строке {i}")
            break
        # Также ищем строку с разделителем |---|
        if '|' in line and '---' in line and not header_found:
            table_start = i + 1
            print(f"Найден разделитель таблицы в строке {i}")
            break

    if table_start == -1:
        # Если не нашли по стандартным маркерам, ищем любую строку с | и днями недели
        for i, line in enumerate(lines):
            if '|' in line and any(day in line for day in ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']):
                table_start = i
                print(f"Найдена строка с данными в строке {i}")
                break

    if table_start == -1:
        print("❌ Таблица не найдена! Проверьте формат файла.")
        print("Совет: Запустите debug_markdown_file() для анализа")
        return schedule

    print(f"✅ Начало таблицы найдено на строке {table_start}")

    current_day = None

    for i in range(table_start, len(lines)):
        line = lines[i].strip()

        # Пропускаем пустые строки
        if not line:
            continue

        # Останавливаемся на примечаниях или подписях
        if line.startswith('Примечание') or line.startswith('Директор') or line.startswith('---'):
            print(f"Остановка на строке {i}: {line[:30]}")
            break

        # Проверяем, является ли строка частью таблицы
        if '|' not in line:
            continue

        # Разбиваем строку по символу '|'
        parts = [p.strip() for p in line.split('|')]

        # Удаляем пустые части в начале и конце, но сохраняем внутренние пустоты
        while parts and parts[0] == '':
            parts.pop(0)
        while parts and parts[-1] == '':
            parts.pop()

        if len(parts) < 2:
            continue

        # Первая колонка - день недели или номер пары
        first_col = parts[0] if len(parts) > 0 else ''

        # Проверяем, является ли первая колонка днем недели
        if first_col in ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']:
            current_day = first_col
            print(f"Найден день: {current_day} в строке {i}")

            # Получаем данные
            lesson_num = parts[1] if len(parts) > 1 else ''
            subject1 = parts[2] if len(parts) > 2 else ''
            subject2 = parts[3] if len(parts) > 3 else ''

            # Добавляем запись
            add_schedule_entry(schedule, current_day, lesson_num, subject1, subject2)

        # Если первая колонка - это номер пары (цифра)
        elif current_day and (first_col.isdigit() or (first_col and '-' in first_col)):
            lesson_num = first_col
            subject1 = parts[1] if len(parts) > 1 else ''
            subject2 = parts[2] if len(parts) > 2 else ''

            add_schedule_entry(schedule, current_day, lesson_num, subject1, subject2)

        # Если первая колонка пустая, значит это продолжение предыдущего дня
        elif current_day and (first_col == '' or first_col == '—' or first_col == '-'):
            lesson_num = parts[1] if len(parts) > 1 else ''
            subject1 = parts[2] if len(parts) > 2 else ''
            subject2 = parts[3] if len(parts) > 3 else ''

            if lesson_num and lesson_num != '' and not lesson_num[0].isdigit():
                # Если lesson_num не цифра, то это может быть предмет
                subject1 = lesson_num
                lesson_num = ''

            if lesson_num and (lesson_num.isdigit() or '-' in lesson_num):
                add_schedule_entry(schedule, current_day, lesson_num, subject1, subject2)

    print(f"✅ Всего найдено записей: {len(schedule)}")
    return schedule


def add_schedule_entry(schedule, day, lesson_num, subject1, subject2):
    """Добавляет запись в расписание, обрабатывая диапазоны пар"""
    if not lesson_num:
        return

    if '-' in lesson_num:
        # Разбиваем на отдельные пары
        try:
            clean_num = lesson_num.replace('.', '').replace(' ', '')
            start, end = clean_num.split('-')
            for num in range(int(start), int(end) + 1):
                schedule.append({
                    'day': day,
                    'lesson': str(num),
                    'subject1': subject1,
                    'subject2': subject2
                })
        except:
            # Если не удалось разобрать диапазон, добавляем как есть
            schedule.append({
                'day': day,
                'lesson': lesson_num,
                'subject1': subject1,
                'subject2': subject2
            })
    elif lesson_num and lesson_num != '':
        schedule.append({
            'day': day,
            'lesson': lesson_num.replace('.', ''),
            'subject1': subject1,
            'subject2': subject2
        })


def clean_and_analyze_subject(subject):
    """Анализирует предмет, сохраняя информацию о чередовании"""
    if not subject:
        return '', False, None, None

    original = subject
    has_alternation = '//' in original

    if not has_alternation:
        cleaned = ' '.join(original.split())
        return cleaned, False, None, None

    numerator = None
    denominator = None

    if original.startswith('//'):
        denominator = original[2:].strip()
    elif original.endswith('//'):
        numerator = original[:-2].strip()
    else:
        parts = original.split('//')
        if len(parts) >= 2:
            numerator = parts[0].strip()
            denominator = parts[1].strip()

    if numerator:
        numerator = ' '.join(numerator.split())
    if denominator:
        denominator = ' '.join(denominator.split())

    if numerator and denominator:
        cleaned = f"{numerator} // {denominator}"
    elif numerator:
        cleaned = numerator
    elif denominator:
        cleaned = denominator
    else:
        cleaned = original.replace('//', '').strip()
        cleaned = ' '.join(cleaned.split())

    return cleaned, True, numerator, denominator


def process_schedule_with_alternation(schedule):
    """Обрабатывает чередование предметов"""
    processed_schedule = []

    for item in schedule:
        subject1_clean, sub1_alt, sub1_num, sub1_den = clean_and_analyze_subject(item['subject1'])
        subject2_clean, sub2_alt, sub2_num, sub2_den = clean_and_analyze_subject(item['subject2'])

        has_alternation = sub1_alt or sub2_alt
        alternation_info = None

        if has_alternation:
            alternation_info = {
                'type': 'alternating',
                'description': 'Предметы чередуются по числителю/знаменателю (по неделям)',
                'numerator': sub1_num or sub2_num,
                'denominator': sub1_den or sub2_den,
                'note': 'В числителе - первая неделя, в знаменателе - вторая неделя'
            }

        processed_schedule.append({
            'day': item['day'],
            'lesson': item['lesson'],
            'subject1': subject1_clean,
            'subject2': subject2_clean,
            'alternating': has_alternation,
            'alternation_details': alternation_info
        })

    return processed_schedule


# Основная часть
print("🚀 Начинаем парсинг расписания...")
print("=" * 50)

# Читаем файл
try:
    with open('PI.md', 'r', encoding='utf-8') as f:
        text = f.read()
    print(f"✅ Файл прочитан, размер: {len(text)} символов")
except FileNotFoundError:
    print("❌ Файл PI.md не найден!")
    exit(1)

# Парсим расписание
schedule_data = parse_schedule_to_json(text)

if not schedule_data:
    print("\n⚠️ ВНИМАНИЕ: Расписание не найдено!")
    print("Запустите функцию debug_markdown_file('PI.md') для диагностики")
else:
    print(f"\n📊 Найдено записей до обработки: {len(schedule_data)}")

    # Обрабатываем чередование
    final_schedule = process_schedule_with_alternation(schedule_data)

    # Создаем итоговую структуру JSON
    result = {
        "metadata": {
            "group": "09.03.04 Программная инженерия",
            "profile": "Программное обеспечение компьютерных систем",
            "academic_year": "2025-2026",
            "semester": "Весенний",
            "period": "02.02.2026-06.06.2026",
            "note": "// - означает чередование по числителю/знаменателю (по неделям)"
        },
        "schedule": final_schedule
    }

    # Сохраняем в JSON файл
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ Расписание сохранено в schedule.json")
    print(f"📊 Всего записей: {len(final_schedule)}")

    # Показываем первые 5 записей
    if final_schedule:
        print("\n📋 Первые 5 записей:")
        for item in final_schedule[:5]:
            print(json.dumps(item, ensure_ascii=False, indent=2))