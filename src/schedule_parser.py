import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json
from datetime import datetime, timedelta


def create_calendar(file_name: str, file_path: str):
    print("\n" + "=" * 70)
    print("🚀 Начинаем парсинг расписания...")
    print("=" * 70)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        print(f"✅ Файл прочитан, размер: {len(text)} символов")
    except FileNotFoundError:
        print(f"❌ Файл {file_name}.md не найден!")
        return

    # Извлекаем metadata
    metadata = extract_metadata_from_md(text)
    print(f"\n📋 Извлеченные метаданные:")
    for key, value in metadata.items():
        if value:
            print(f"  {key}: {value}")

    # Парсим расписание
    schedule_data = parse_schedule_to_json(text)

    if not schedule_data:
        print("\n⚠️ ВНИМАНИЕ: Расписание не найдено!")
        return

    print(f"\n📊 Найдено записей: {len(schedule_data)}")

    # Обрабатываем чередование
    final_schedule = process_schedule_with_alternation(schedule_data)

    # Сохраняем основной JSON
    result = {
        "metadata": metadata,
        "schedule": final_schedule
    }

    with open(f'{file_name}_schedule.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ Расписание сохранено в {file_name}_schedule.json")

    # Создаем JSON для календаря
    calendar_json = create_calendar_json(final_schedule, metadata)

    # Сохраняем календарь JSON
    with open(f'{file_name}_calendar.json', 'w', encoding='utf-8') as f:
        json.dump(calendar_json, f, ensure_ascii=False, indent=2)

    print(f"✅ Календарь сохранен в {file_name}_calendar.json")
    print(f"📅 Создано событий: {calendar_json['calendar']['total_events']}")

    # Сохраняем ICS файл
    save_as_ics(calendar_json, file_name)


def extract_metadata_from_md(markdown_text: str) -> Dict[str, str]:
    """ Извлекает metadata из markdown файла """
    metadata = {
        "group": "",
        "profile": "",
        "academic_year": "",
        "semester": "",
        "period": "",
        "start_date": "",
        "end_date": "",
        "note": "// - означает чередование по числителю/знаменателю (по неделям)"
    }

    lines = markdown_text.split('\n')

    # Паттерны для поиска
    patterns = {
        "group": r"Направление[:\s]*([0-9]{2}\.[0-9]{2}\.[0-9]{2}\s+[А-Яа-я\s]+)",
        "profile": r"Профиль[:\s]*([А-Яа-я\s\d\(\)]+)",
        "academic_year": r"Учебный год[:\s]*([0-9]{4}-[0-9]{4})",
        "period": r"ТО[:\s]*\(?([0-9]{2}\.[0-9]{2}\.[0-9]{4}-[0-9]{2}\.[0-9]{2}\.[0-9]{4})",
        "semester": r"(Осенний|Весенний|зимний|летний)\s*семестр"
    }

    for line in lines:
        if "Направление" in line and not metadata["group"]:
            match = re.search(patterns["group"], line)
            if match:
                metadata["group"] = match.group(1).strip()

        if "Профиль" in line and not metadata["profile"]:
            match = re.search(patterns["profile"], line)
            if match:
                metadata["profile"] = match.group(1).strip()

        if "Учебный год" in line and not metadata["academic_year"]:
            match = re.search(patterns["academic_year"], line)
            if match:
                metadata["academic_year"] = match.group(1).strip()

        if "ТО:" in line and not metadata["period"]:
            match = re.search(patterns["period"], line)
            if match:
                metadata["period"] = match.group(1).strip()
                if '-' in metadata["period"]:
                    dates = metadata["period"].split('-')
                    metadata["start_date"] = dates[0].strip()
                    metadata["end_date"] = dates[1].strip()

        if not metadata["semester"]:
            match = re.search(patterns["semester"], line, re.IGNORECASE)
            if match:
                metadata["semester"] = match.group(1).capitalize()

    if not metadata["semester"] and metadata["start_date"]:
        month = int(metadata["start_date"].split('.')[1])
        if month >= 9 or month <= 1:
            metadata["semester"] = "Осенний"
        else:
            metadata["semester"] = "Весенний"

    return metadata


def parse_schedule_to_json(markdown_text: str) -> List[Dict]:
    """
    Парсит расписание из markdown в JSON формат
    Возвращает список расписаний (каждая таблица - отдельное расписание)
    """
    lines = markdown_text.split('\n')

    # Собираем все таблицы
    all_tables = []
    in_table = False
    current_table_lines = []

    for i, line in enumerate(lines):
        if '|' in line and 'Д/Н' in line and 'пара' in line and 'дисциплина' in line:
            if current_table_lines:
                if len(current_table_lines) > 2:
                    all_tables.append(current_table_lines)
                current_table_lines = []
            in_table = True
            current_table_lines.append(line)

        elif in_table and '|' in line:
            current_table_lines.append(line)

            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if (not next_line or
                        next_line.startswith('Примечание') or
                        next_line.startswith('Директор') or
                        next_line.startswith('#') or
                        next_line.startswith('---') or
                        '|' not in next_line):
                    if len(current_table_lines) > 2:
                        all_tables.append(current_table_lines)
                    current_table_lines = []
                    in_table = False

        elif line.strip().startswith('---') and current_table_lines:
            if len(current_table_lines) > 2:
                all_tables.append(current_table_lines)
            current_table_lines = []
            in_table = False

    if len(current_table_lines) > 2:
        all_tables.append(current_table_lines)

    print(f"📊 Найдено таблиц: {len(all_tables)}")

    # Парсим каждую таблицу в отдельное расписание
    schedules = []
    for table_idx, table_lines in enumerate(all_tables):
        parsed = parse_markdown_table(table_lines)
        if parsed:
            schedules.append({
                'table_index': table_idx,
                'schedule': parsed
            })

    return schedules


def parse_markdown_table(table_lines: List[str]) -> List[Dict]:
    """Парсит markdown таблицу"""
    schedule = []
    current_day = None

    for line in table_lines:
        line = line.strip()
        if not line or not line.startswith('|'):
            continue

        parts = [p.strip() for p in line.split('|')]
        while parts and parts[0] == '':
            parts.pop(0)
        while parts and parts[-1] == '':
            parts.pop()

        if len(parts) < 2 or '---' in line:
            continue

        first_col = parts[0]

        if first_col in ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']:
            current_day = first_col
            lesson_num = parts[1] if len(parts) > 1 else ''
            subject1 = parts[2] if len(parts) > 2 else ''
            subject2 = parts[3] if len(parts) > 3 else ''
            add_schedule_entry(schedule, current_day, lesson_num, subject1, subject2)

        elif current_day and (first_col.isdigit() or (first_col and '-' in first_col)):
            lesson_num = first_col
            subject1 = parts[1] if len(parts) > 1 else ''
            subject2 = parts[2] if len(parts) > 2 else ''
            add_schedule_entry(schedule, current_day, lesson_num, subject1, subject2)

        elif current_day and (first_col == '' or first_col == '—' or first_col == '-' or first_col == ' '):
            lesson_num = parts[1] if len(parts) > 1 else ''
            subject1 = parts[2] if len(parts) > 2 else ''
            subject2 = parts[3] if len(parts) > 3 else ''

            if lesson_num and lesson_num != '' and not lesson_num[0].isdigit():
                subject1 = lesson_num
                lesson_num = ''

            if lesson_num and (lesson_num.isdigit() or '-' in lesson_num):
                add_schedule_entry(schedule, current_day, lesson_num, subject1, subject2)
            elif not lesson_num and subject1:
                add_schedule_entry(schedule, current_day, '', subject1, subject2)

    return schedule


def add_schedule_entry(schedule: List, day: str, lesson_num: str, subject1: str, subject2: str):
    """Добавляет запись в расписание"""
    if not lesson_num and not subject1 and not subject2:
        return

    if not lesson_num or lesson_num == '':
        schedule.append({
            'day': day,
            'lesson': '0',
            'subject1': subject1,
            'subject2': subject2
        })
        return

    if '-' in lesson_num:
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


def process_schedule_with_alternation(schedule: List) -> List:
    """ Обрабатывает чередование предметов """
    processed_schedule = []

    for item in schedule:
        subject1_clean, sub1_alt, sub1_num, sub1_den = clean_and_analyze_subject(item['subject1'])
        subject2_clean, sub2_alt, sub2_num, sub2_den = clean_and_analyze_subject(item['subject2'])

        processed_schedule.append({
            'day': item['day'],
            'lesson': item['lesson'],
            'subject1': subject1_clean,
            'subject2': subject2_clean,
            'subject1_alternating': sub1_alt,
            'subject2_alternating': sub2_alt,
            'subject1_numerator': sub1_num,
            'subject1_denominator': sub1_den,
            'subject2_numerator': sub2_num,
            'subject2_denominator': sub2_den
        })

    return processed_schedule


def clean_and_analyze_subject(subject: str) -> Tuple[str, bool, Optional[str], Optional[str]]:
    """ Анализирует предмет, сохраняя информацию о чередовании """
    if not subject:
        return '', False, None, None

    original = subject
    has_alternation = '//' in original

    if not has_alternation:
        cleaned = ' '.join(original.split())
        return cleaned, False, None, None

    # Разделяем на части по //
    parts = original.split('//')
    parts = [p.strip() for p in parts]

    # Понедельное чередование: предмет1 // предмет2
    numerator = parts[0] if len(parts) > 0 and parts[0] else None
    denominator = parts[1] if len(parts) > 1 and parts[1] else None

    if numerator:
        numerator = ' '.join(numerator.split())
    if denominator:
        denominator = ' '.join(denominator.split())

    # Для отображения в schedule.json берем numerator (если есть) или denominator
    cleaned = numerator if numerator else (denominator if denominator else '')
    if cleaned:
        cleaned = ' '.join(cleaned.split())

    return cleaned, True, numerator, denominator


def create_calendar_json(schedule_data: List, metadata: Dict, year: int = 2026) -> Dict:
    """ Создает JSON структуру, готовую для конвертации в ICS календарь """

    day_mapping = {
        'ПН': 0, 'ВТ': 1, 'СР': 2, 'ЧТ': 3, 'ПТ': 4, 'СБ': 5
    }

    regular_lesson_times = {
        '1': {'start': '08:30', 'end': '09:50'},
        '2': {'start': '10:00', 'end': '11:20'},
        '3': {'start': '11:30', 'end': '12:50'},
        '4': {'start': '13:20', 'end': '14:40'},
        '5': {'start': '14:50', 'end': '16:10'},
        '6': {'start': '16:20', 'end': '17:40'},
        '7': {'start': '18:00', 'end': '19:20'},
        '8': {'start': '19:30', 'end': '20:50'}
    }

    elective_lesson_times = {
        '1': {'start': '09:00', 'end': '10:20'},
        '2': {'start': '10:30', 'end': '11:50'},
        '3': {'start': '12:00', 'end': '13:20'},
        '4': {'start': '13:30', 'end': '14:50'},
        '5': {'start': '15:00', 'end': '16:20'},
        '6': {'start': '16:30', 'end': '17:50'}
    }

    calendar_events = []

    # Определяем дату начала семестра
    if metadata.get('start_date'):
        start_date_parts = metadata['start_date'].split('.')
        start_date = datetime(int(start_date_parts[2]), int(start_date_parts[1]), int(start_date_parts[0]))
    else:
        # Если дата не указана, используем примерную (начало февраля 2026)
        start_date = datetime(year, 2, 2)

    # Находим первую дату для каждого дня недели
    first_week_dates = {}
    for day_name, day_num in day_mapping.items():
        days_ahead = (day_num - start_date.weekday()) % 7
        first_week_dates[day_name] = start_date + timedelta(days=days_ahead)

    # Группируем занятия по дням недели
    schedule_by_day = {}
    for item in schedule_data:
        day = item['day']
        if day not in schedule_by_day:
            schedule_by_day[day] = []
        schedule_by_day[day].append(item)

    # Определяем дату окончания семестра
    end_date = None
    if metadata.get('end_date'):
        end_date_parts = metadata['end_date'].split('.')
        end_date = datetime(int(end_date_parts[2]), int(end_date_parts[1]), int(end_date_parts[0]))

    # Определяем общее количество недель в семестре
    if end_date:
        delta = end_date - start_date
        total_weeks = delta.days // 7 + 1
    else:
        total_weeks = 16

    # Создаем события для каждой недели
    for week_num in range(total_weeks):
        # Определяем тип недели: 0 - числитель, 1 - знаменатель
        week_type = "numerator" if week_num % 2 == 0 else "denominator"

        for day_name, events in schedule_by_day.items():
            event_date = first_week_dates[day_name] + timedelta(weeks=week_num)

            if end_date and event_date > end_date:
                continue

            if event_date < datetime.now().replace(hour=0, minute=0, second=0, microsecond=0):
                continue

            for event in events:
                lesson_num = event['lesson']

                subjects_to_add = []

                # Обрабатываем subject1
                if event['subject1_alternating']:
                    # Чередование для subject1
                    if week_type == "numerator" and event['subject1_numerator']:
                        subjects_to_add.append(event['subject1_numerator'])
                    elif week_type == "denominator" and event['subject1_denominator']:
                        subjects_to_add.append(event['subject1_denominator'])
                else:
                    # Нет чередования - каждую неделю
                    if event['subject1'] and event['subject1'] != '':
                        subjects_to_add.append(event['subject1'])

                # Обрабатываем subject2
                if event['subject2_alternating']:
                    # Чередование для subject2
                    if week_type == "numerator" and event['subject2_numerator']:
                        subjects_to_add.append(event['subject2_numerator'])
                    elif week_type == "denominator" and event['subject2_denominator']:
                        subjects_to_add.append(event['subject2_denominator'])
                else:
                    # Нет чередования - каждую неделю
                    if event['subject2'] and event['subject2'] != '':
                        subjects_to_add.append(event['subject2'])

                # Пропускаем, если нет предметов на этой неделе
                if not subjects_to_add:
                    continue

                # Выбираем расписание в зависимости от типа предмета
                is_elective = is_elective_discipline(subjects_to_add[0]) if subjects_to_add else False
                lesson_times = elective_lesson_times if is_elective else regular_lesson_times
                time_slot = lesson_times.get(lesson_num, {'start': '00:00', 'end': '00:00'})

                # Создаем события для каждого предмета
                for subject in subjects_to_add:
                    if not subject or subject == '':
                        continue

                    # Очищаем предмет от маркеров чередования
                    subject_clean = subject.strip()
                    if subject_clean.startswith('//'):
                        subject_clean = subject_clean[2:].strip()
                    if subject_clean.endswith('//'):
                        subject_clean = subject_clean[:-2].strip()

                    # Пропускаем, если после очистки осталась пустая строка
                    if not subject_clean:
                        continue

                    event_start = datetime(
                        event_date.year, event_date.month, event_date.day,
                        int(time_slot['start'].split(':')[0]),
                        int(time_slot['start'].split(':')[1])
                    )
                    event_end = datetime(
                        event_date.year, event_date.month, event_date.day,
                        int(time_slot['end'].split(':')[0]),
                        int(time_slot['end'].split(':')[1])
                    )

                    # Создаем уникальный ID для события
                    event_uid = f"{event_start.strftime('%Y%m%d')}-{lesson_num}-{day_name}-{hash(subject_clean)}-week{week_num}@schedule"

                    # Проверяем, является ли этот предмет чередующимся
                    is_alternating = False
                    if event['subject1_alternating'] and subject_clean in [event['subject1_numerator'],
                                                                           event['subject1_denominator']]:
                        is_alternating = True
                    if event['subject2_alternating'] and subject_clean in [event['subject2_numerator'],
                                                                           event['subject2_denominator']]:
                        is_alternating = True

                    # Формируем описание
                    description_parts = [subject_clean, f"Пара {lesson_num}"]
                    if is_alternating:
                        description_parts.append(f"Неделя: {week_type.capitalize()} (неделя #{week_num + 1})")
                    if is_elective:
                        description_parts.append("Элективная дисциплина")

                    calendar_events.append({
                        'uid': event_uid,
                        'summary': subject_clean,
                        'description': '\n'.join(description_parts),
                        'location': extract_location(subject_clean),
                        'start': event_start.isoformat(),
                        'end': event_end.isoformat(),
                        'start_date': event_start.strftime('%Y%m%dT%H%M%S'),
                        'end_date': event_end.strftime('%Y%m%dT%H%M%S'),
                        'dtstamp': datetime.now().strftime('%Y%m%dT%H%M%S'),
                        'week_number': week_num + 1,
                        'week_type': week_type if is_alternating else None,
                        'lesson_number': lesson_num,
                        'is_alternating': is_alternating,
                        'is_elective': is_elective
                    })

    # Сортируем события по дате
    calendar_events.sort(key=lambda x: x['start'])

    calendar_json = {
        "metadata": metadata,
        "calendar": {
            "name": f"Расписание {metadata['group']}",
            "timezone": "Europe/Yekaterinburg",
            "total_weeks": total_weeks,
            "total_events": len(calendar_events),
            "events": calendar_events
        }
    }

    return calendar_json


def is_elective_discipline(subject: str) -> bool:
    if not subject:
        return False
    keywords = ['Элективные дисциплины', 'физической культуре', 'физкультура', 'спорт', 'Элект.']
    return any(keyword in subject for keyword in keywords)


def extract_location(subject: str) -> str:
    """ Извлекает аудиторию из названия предмета """
    patterns = [
        r'([УАЕ][0-9]{3})',  # У408, А304
        r'(ЭОиДОТ)',  # ЭОиДОТ
        r',\s*([А-Я][0-9]+)',  # , С, , У903
        r'\s([А-Я]{1,2}[0-9]{3})'  # У903, А504
    ]

    for pattern in patterns:
        match = re.search(pattern, subject)
        if match:
            return match.group(1)

    return ""


def save_as_ics(calendar_json: Dict, file_name: str):
    """ Сохраняет календарь в ICS формате """
    ics_content = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Schedule Parser//RU", "CALSCALE:GREGORIAN",
                   f"X-WR-CALNAME:{calendar_json['calendar']['name']}",
                   f"X-WR-TIMEZONE:{calendar_json['calendar']['timezone']}",
                   "X-WR-CALDESC:Расписание с учетом чередования числитель/знаменатель"]

    # Добавляем информацию о чередовании в описание календаря

    for event in calendar_json['calendar']['events']:
        ics_content.extend([
            "BEGIN:VEVENT",
            f"UID:{event['uid']}",
            f"DTSTART:{event['start_date']}",
            f"DTEND:{event['end_date']}",
            f"DTSTAMP:{event['dtstamp']}",
            f"SUMMARY:{event['summary']}",
            f"DESCRIPTION:{event['description']}",
            f"LOCATION:{event['location']}",
            "END:VEVENT"
        ])

    ics_content.append("END:VCALENDAR")

    with open(f'{file_name}_calendar.ics', 'w', encoding='utf-8') as f:
        f.write('\n'.join(ics_content))

    print(f"✅ ICS файл сохранен в {file_name}_calendar.ics")
