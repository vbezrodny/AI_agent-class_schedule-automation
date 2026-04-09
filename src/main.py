import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

import cv2
import numpy as np
from paddleocr import PaddleOCR
from pdf2image import convert_from_path  # Poppler
from typing import List, Dict, Any


# from datetime import datetime
# from ics import Calendar, Event


class ScheduleParser:
    def __init__(self, language='ru', use_gpu=False):
        """
        language: 'ru' для русского, 'en' для английского, 'ch' для китайского
        """
        # self.ocr = PaddleOCR(
        #     use_angle_cls=True,  # определение угла наклона страницы
        #     lang=language,  # язык
        #     use_gpu=use_gpu,  # используйте GPU, если есть
        #     show_log=False  # отключаем лишние логи
        # )

    def pdf_to_images(self, pdf_path: str, dpi: int = 300) -> List[np.ndarray]:
        """Конвертирует PDF в список изображений OpenCV"""
        images = convert_from_path(pdf_path, dpi=dpi)

        if (input("do you want to save the images ? [y/n]: ") == 'y'):
            for i, image in enumerate(images):
                image.save(f'page_{i}.jpg', 'JPEG')

        return [cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR) for img in images]

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Улучшает качество изображения для OCR"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)  # Преобразование в оттенки серого
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)  # Удаление шума
        _, binary = cv2.threshold(denoised, 0, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)  # Бинаризация (чёрный текст на белом фоне)
        return binary

    def extract_table_structure(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Извлекает структурированную таблицу из изображения
        Возвращает список ячеек с координатами (строка, колонка, текст)
        """
        # Предобработка
        processed = self.preprocess_image(image)

        # Распознавание текста с позициями
        result = self.ocr.ocr(processed, cls=True)

        if not result or not result[0]:
            return {"cells": []}

        # Группировка по строкам и столбцам на основе Y и X координат
        items = []
        for line in result[0]:
            bbox = line[0]  # координаты прямоугольника
            text = line[1][0]  # распознанный текст
            confidence = line[1][1]  # уверенность

            if confidence < 0.5:
                continue

            # Центр ячейки
            center_x = (bbox[0][0] + bbox[2][0]) / 2
            center_y = (bbox[0][1] + bbox[2][1]) / 2

            items.append({
                "x": center_x,
                "y": center_y,
                "text": text,
                "bbox": bbox
            })

        # Сортируем по Y (сверху вниз) и X (слева направо)
        items.sort(key=lambda p: (p["y"], p["x"]))

        # Определяем строки и столбцы (группировка по вертикали)
        rows = []
        current_row = []
        last_y = None

        for item in items:
            if last_y is None or abs(item["y"] - last_y) > 30:  # порог в пикселях
                if current_row:
                    rows.append(current_row)
                current_row = [item]
            else:
                current_row.append(item)
            last_y = item["y"]

        if current_row:
            rows.append(current_row)

        # Преобразуем в структуру таблицы
        cells = []
        for row_idx, row in enumerate(rows):
            for col_idx, item in enumerate(row):
                cells.append({
                    "row": row_idx,
                    "col": col_idx,
                    "text": item["text"],
                    "confidence": item.get("confidence", 1.0)
                })

        return {"cells": cells, "rows": len(rows), "cols": max(len(r) for r in rows) if rows else 0}

    def parse_schedule(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Основной метод: из PDF в список занятий"""
        images = self.pdf_to_images(pdf_path)
        all_lessons = []

        for page_num, img in enumerate(images):
            table_data = self.extract_table_structure(img)
            lessons = self.convert_table_to_lessons(table_data, page_num)
            all_lessons.extend(lessons)

        return all_lessons

    def convert_table_to_lessons(self, table: Dict, page_num: int) -> List[Dict]:
        """
        Преобразует таблицу в список занятий.
        ВАЖНО: этот метод нужно адаптировать под реальную структуру вашего расписания.
        """
        cells = table.get("cells", [])
        if not cells:
            return []

        # Группируем по строкам
        rows_dict = {}
        for cell in cells:
            row = cell["row"]
            if row not in rows_dict:
                rows_dict[row] = {}
            rows_dict[row][cell["col"]] = cell["text"]

        lessons = []
        # Предполагаем, что первая строка — заголовки (дни недели)
        headers = rows_dict.get(0, {})

        # Остальные строки — занятия
        for row_idx, row_data in rows_dict.items():
            if row_idx == 0:  # пропускаем заголовки
                continue

            # В первом столбце может быть время
            time = row_data.get(0, "").strip()
            if not time:
                continue

            # По каждому дню (столбцу, начиная с 1)
            for col_idx in range(1, len(headers)):
                subject = row_data.get(col_idx, "").strip()
                if subject and subject not in ["", "-", "—"]:
                    day = headers.get(col_idx, f"day_{col_idx}")
                    lessons.append({
                        "day": day,
                        "time": time,
                        "subject": subject,
                        "page": page_num,
                        "raw_data": row_data
                    })

        return lessons


if __name__ == "__main__":
    parser = ScheduleParser(language='ru')

    schedule_images = parser.pdf_to_images("../materials/Programmnaya inzheneriya-20-02-26.pdf")

    if schedule_images:
        shedule_preprocess = parser.preprocess_image(schedule_images[0])  # Take first image
        print(f"Processed image shape: {shedule_preprocess.shape}")
        print(f"Image type: {type(shedule_preprocess)}")

        # Optional: Save the preprocessed image to see the result
        cv2.imwrite('preprocessed_page_0.jpg', shedule_preprocess)
        print("Saved preprocessed image as 'preprocessed_page_0.jpg'")
    else:
        print("No images were extracted from the PDF")

    # schedule = parser.parse_schedule("raspisanie.pdf")

    # for lesson in schedule:
    #     print(f"{lesson['day']} | {lesson['time']} | {lesson['subject']}")
