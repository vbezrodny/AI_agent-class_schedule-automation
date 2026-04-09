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

        return denoised

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
            result = self.ocr.predict(processed)
        except Exception as e:
            print(f"OCR prediction failed: {e}")
            return {"cells": []}

        # Handle different return formats
        if not result:
            return {"cells": []}

        items = []

        # Parse the result based on common PaddleOCR output formats
        try:
            # Try to iterate through the results
            if isinstance(result, (list, tuple)):
                for item in result:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        # Format: [[bbox], (text, confidence)]
                        bbox = item[0]
                        text_info = item[1]

                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                            text = text_info[0]
                            confidence = text_info[1]
                        else:
                            text = str(text_info)
                            confidence = 1.0

                        # Calculate center of bounding box
                        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                            center_x = (bbox[0][0] + bbox[2][0]) / 2
                            center_y = (bbox[0][1] + bbox[2][1]) / 2

                            items.append({
                                "x": center_x,
                                "y": center_y,
                                "text": text,
                                "bbox": bbox,
                                "confidence": confidence
                            })
                    elif isinstance(item, dict) and 'bbox' in item and 'text' in item:
                        # Alternative format
                        bbox = item['bbox']
                        text = item['text']
                        confidence = item.get('confidence', 1.0)

                        center_x = (bbox[0][0] + bbox[2][0]) / 2
                        center_y = (bbox[0][1] + bbox[2][1]) / 2

                        items.append({
                            "x": center_x,
                            "y": center_y,
                            "text": text,
                            "bbox": bbox,
                            "confidence": confidence
                        })
        except Exception as e:
            print(f"Error parsing OCR results: {e}")
            print(f"Result structure: {type(result)}")
            if hasattr(result, '__len__') and len(result) > 0:
                print(f"First item type: {type(result[0])}")
                print(f"First item: {result[0]}")
            return {"cells": []}

        if not items:
            print("No text detected in image")
            return {"cells": []}

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

    # First convert PDF to images
    pdf_path = "../materials/Programmnaya inzheneriya-20-02-26.pdf"
    images = parser.pdf_to_images(pdf_path)

    try:
        images = parser.pdf_to_images(pdf_path)

        # Process each page
        for page_num, img in enumerate(images):
            print(f"\n{'=' * 50}")
            print(f"Processing page {page_num}")
            print(f"{'=' * 50}")

            # Extract table structure from the image
            table_data = parser.extract_table_structure(img)

            print(f"\nResults for page {page_num}:")
            print(f"  Rows: {table_data.get('rows', 0)}")
            print(f"  Columns: {table_data.get('cols', 0)}")
            print(f"  Total cells: {len(table_data.get('cells', []))}")

            # Print first few cells to see what was detected
            if table_data.get('cells'):
                print("\nFirst 15 detected cells:")
                for i, cell in enumerate(table_data.get('cells', [])[:15]):
                    print(f"  [{cell['row']},{cell['col']}]: '{cell['text']}'")

            # Convert to lessons if needed
            lessons = parser.convert_table_to_lessons(table_data, page_num)
            if lessons:
                print(f"\nFound {len(lessons)} lessons on page {page_num}:")
                for lesson in lessons[:5]:  # Show first 5 lessons
                    print(f"  {lesson['day']} | {lesson['time']} | {lesson['subject']}")
            else:
                print("\nNo lessons found on this page")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
