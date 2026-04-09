import asyncio
from kreuzberg import extract_file
import json
from datetime import datetime
# from ics import Calendar, Event

# poppler_path = r"C:\Program Files (x86)\Poppler\poppler-25.12.0\Library\bin"

async def extract_schedule(pdf_path):
    print(f"🔍 Анализирую файл: {pdf_path}")

    # === Способ 1: Kreuzberg (отлично для OCR и текста) ===
    result_kreuz = await extract_file(pdf_path)
    text_kreuz = result_kreuz.content
    print(f"✅ Kreuzberg извлёк {len(text_kreuz)} символов")

    # Берём лучший результат (где больше текста)
    final_text = text_kreuz # text_kreuz if len(text_kreuz) > len(text_lite) else text_lite

    # Сохраняем raw-текст для отладки
    with open("extracted_text.txt", "w", encoding="utf-8") as f:
        f.write(final_text)

    return final_text


# def parse_schedule_with_llm(raw_text):
#     """
#     Отправляем текст в локальную LLM для структурирования
#     """
#     # Здесь вы можете использовать Ollama с любой бесплатной моделью
#     # Например: llama3.2, qwen2.5, mistral
#     import ollama
#
#     prompt = f"""
#     Ты — ассистент. Извлеки расписание занятий из текста.
#     Верни ТОЛЬКО JSON-массив.
#
#     Формат каждой записи:
#     {{"day": "Понедельник", "time": "09:00-10:30", "subject": "Математика", "room": "301", "teacher": "Иванов"}}
#
#     Текст расписания:
#     {raw_text[:4000]}
#
#     JSON:
#     """
#
#     response = ollama.chat(model='llama3.2', messages=[{'role': 'user', 'content': prompt}])
#
#     # Извлекаем JSON из ответа
#     import re
#     json_match = re.search(r'\[[\s\S]*\]', response['message']['content'])
#     if json_match:
#         return json.loads(json_match.group())
#     return []


# def create_ics_file(lessons, semester_start='2026-09-01'):
#     """
#     Создаёт файл календаря .ics (открывается в Google/Apple/Outlook)
#     """
#     cal = Calendar()
#     start_date = datetime.strptime(semester_start, '%Y-%m-%d')
#
#     day_map = {
#         'понедельник': 0, 'вторник': 1, 'среда': 2,
#         'четверг': 3, 'пятница': 4, 'суббота': 5, 'воскресенье': 6
#     }
#
#     for lesson in lessons:
#         # Определяем день недели
#         day_name = lesson.get('day', '').lower()
#         weekday = day_map.get(day_name, 0)
#
#         # Находим первую дату
#         days_until = (weekday - start_date.weekday()) % 7
#         first_date = start_date + timedelta(days=days_until)
#
#         # Парсим время
#         time_parts = lesson.get('time', '09:00-10:30').split('-')
#         start_time = time_parts[0].strip()
#         end_time = time_parts[1].strip() if len(time_parts) > 1 else "10:30"
#
#         # Создаём событие
#         event = Event()
#         event.name = f"{lesson['subject']}"
#         event.location = lesson.get('room', '')
#         event.description = f"Преподаватель: {lesson.get('teacher', '')}"
#         event.begin = f"{first_date.strftime('%Y-%m-%d')} {start_time}"
#         event.end = f"{first_date.strftime('%Y-%m-%d')} {end_time}"
#
#         # Повтор каждую неделю
#         event.make_recurring(rule="FREQ=WEEKLY", until=start_date + timedelta(days=120))
#
#         cal.events.add(event)
#         print(f"  ✓ {lesson['day']}: {lesson['subject']} — {start_time}")
#
#     # Сохраняем файл
#     with open('schedule.ics', 'w', encoding='utf-8') as f:
#         f.writelines(cal)
#
#     print(f"\n📅 Календарь создан: schedule.ics")
#     print("   Просто откройте этот файл — он добавится в ваш календарь!")


# ========== ЗАПУСК ==========

if __name__ == "__main__":
    # Шаг 1: Извлекаем текст из PDF
    text = asyncio.run(extract_schedule("../materials/Programmnaya inzheneriya-20-02-26.pdf"))

    # # Шаг 2: Структурируем через локальную LLM
    # lessons = parse_schedule_with_llm(raw_text)
    #
    # # Шаг 3: Создаём календарь
    # if lessons:
    #     create_ics_file(lessons)
    # else:
    #     print("❌ Не удалось распознать расписание")
    #     print("Проверьте extracted_text.txt — возможно, нужно улучшить OCR")