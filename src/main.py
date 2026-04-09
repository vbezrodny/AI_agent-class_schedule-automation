import os
# Disable problematic optimizations
os.environ['FLAGS_use_mkldnn'] = '0'  # Disable MKLDNN
os.environ['FLAGS_use_mkldnn_quantizer'] = '0'
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

import cv2
import numpy as np
from paddleocr import PaddleOCR
from pdf2image import convert_from_path  # Poppler
from typing import List, Dict, Any
import re


# from datetime import datetime
# from ics import Calendar, Event


class ScheduleParser:
    def __init__(self, language='ru', use_gpu=False):
        """
        language: 'ru' для русского, 'en' для английского, 'ch' для китайского
        """
        self.ocr = PaddleOCR(
            use_textline_orientation=True,  # определение угла наклона страницы
            lang=language,  # язык
            det_db_thresh=0.3,  # Lower threshold for better detection
            det_db_box_thresh=0.3,
            rec_batch_num=1  # Process one at a time
        )

    def pdf_to_images(self, pdf_path: str, dpi: int = 300) -> List[np.ndarray]:
        """Конвертирует PDF в список изображений OpenCV"""
        # images = convert_from_path(pdf_path, dpi=dpi)
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=2)  # First 2 pages only

        if input("do you want to save the images (pdf -> page images) ? [y/n]: ") == 'y':
            for i, image in enumerate(images):
                image.save(f'page_{i}.jpg', 'JPEG', quality=90)

        return [cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR) for img in images]

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Улучшает качество изображения для OCR
        IMPORTANT: Returns RGB image (3 channels) for PaddleOCR
        """
        # Resize if too large (speed up processing)
        h, w = image.shape[:2]
        if w > 2000 or h > 2000:
            scale = min(2000 / w, 2000 / h)
            new_w, new_h = int(w * scale), int(h * scale)
            image = cv2.resize(image, (new_w, new_h))
            print(f"Resized image from {w}x{h} to {new_w}x{new_h}")

        # Simple denoising while keeping color
        if len(image.shape) == 3:
            image = cv2.fastNlMeansDenoisingColored(image, None, 5, 5, 7, 21)

        return image

    def extract_table_structure(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Извлекает структурированную таблицу из изображения
        Возвращает список ячеек с координатами (строка, колонка, текст)
        """
        # Предобработка - сохраняем цветное изображение для OCR
        processed = self.preprocess_image(image)

        print(f"Image shape for OCR: {processed.shape}, dtype: {processed.dtype}")

        # Распознавание текста с позициями
        try:
            # Try different OCR methods
            result = None

            # Method 1: Simple OCR
            try:
                result = self.ocr.predict(processed)
            except Exception as e1:
                print(f"Method 1 failed: {e1}")

                # Method 2: Try without text detection orientation
                try:
                    result = self.ocr.predict(processed)
                except Exception as e2:
                    print(f"Method 2 failed: {e2}")
                    return {"cells": []}

            if not result or not result[0]:
                print("No text detected")
                return {"cells": []}

        except Exception as e:
            print(f"OCR failed: {e}")
            return {"cells": []}

        # Parse OCR results
        items = []

        for line in result[0]:
            try:
                # PaddleOCR format: [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], (text, confidence)]
                bbox = line[0]
                text_info = line[1]

                text = text_info[0] if isinstance(text_info, (list, tuple)) else str(text_info)
                confidence = text_info[1] if isinstance(text_info, (list, tuple)) and len(text_info) > 1 else 1.0

                if confidence < 0.5 or len(text.strip()) < 1:
                    continue

                # Calculate center of bounding box
                x_coords = [point[0] for point in bbox]
                y_coords = [point[1] for point in bbox]
                center_x = sum(x_coords) / len(x_coords)
                center_y = sum(y_coords) / len(y_coords)

                items.append({
                    "x": center_x,
                    "y": center_y,
                    "text": text,
                    "bbox": bbox,
                    "confidence": confidence
                })
            except Exception as e:
                print(f"Error parsing line: {e}")
                continue

        if not items:
            print("No valid text items detected")
            return {"cells": []}

        print(f"Detected {len(items)} text items")

        # Sort by Y (top to bottom) then X (left to right)
        items.sort(key=lambda p: (p["y"], p["x"]))

        # Group into rows (vertical grouping)
        rows = []
        current_row = []
        last_y = None
        y_threshold = 50  # Pixel threshold for grouping into same row

        for item in items:
            if last_y is None or abs(item["y"] - last_y) > y_threshold:
                if current_row:
                    # Sort current row by X coordinate
                    current_row.sort(key=lambda p: p["x"])
                    rows.append(current_row)
                current_row = [item]
            else:
                current_row.append(item)
            last_y = item["y"]

        if current_row:
            current_row.sort(key=lambda p: p["x"])
            rows.append(current_row)

        # Convert to cells
        cells = []
        for row_idx, row in enumerate(rows):
            for col_idx, item in enumerate(row):
                cells.append({
                    "row": row_idx,
                    "col": col_idx,
                    "text": item["text"],
                    "confidence": item["confidence"]
                })

        return {
            "cells": cells,
            "rows": len(rows),
            "cols": max(len(r) for r in rows) if rows else 0
        }

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
    # Disable additional problematic features
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

    parser = ScheduleParser(language='ru')

    pdf_path = "../materials/Programmnaya inzheneriya-20-02-26.pdf"

    try:
        schedule = parser.parse_schedule(pdf_path)

        print(f"\n{'=' * 60}")
        print(f"TOTAL LESSONS FOUND: {len(schedule)}")
        print(f"{'=' * 60}")

        # Print all lessons grouped by day
        if schedule:
            from collections import defaultdict

            by_day = defaultdict(list)
            for lesson in schedule:
                by_day[lesson['day']].append(lesson)

            for day in sorted(by_day.keys()):
                print(f"\n{day}:")
                for lesson in by_day[day]:
                    print(f"  {lesson['time']} - {lesson['subject']}")
        else:
            print("\nNo lessons were extracted. This might be because:")
            print("1. The PDF structure is different than expected")
            print("2. OCR detection failed due to quality issues")
            print("3. Need to adjust preprocessing parameters")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
