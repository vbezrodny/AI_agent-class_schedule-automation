import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='torch.utils.data.dataloader')

import os
import cv2
import numpy as np
import re
import easyocr
from pdf2image import convert_from_path
from typing import List, Dict, Any
from collections import defaultdict


# from datetime import datetime
# from ics import Calendar, Event


class ScheduleParser:
    def __init__(self, language='ru', use_gpu=False):
        """
        language: 'ru' для русского, 'en' для английского
        """
        lang_list = ['ru', 'en']  # Russian and English
        print("Initializing EasyOCR (this may take a moment on first run)...")
        self.ocr = easyocr.Reader(lang_list, gpu=use_gpu, verbose=False)
        self.use_easyocr = True
        print("✓ EasyOCR ready")

    def pdf_to_images(self, pdf_path: str, dpi: int = 200) -> List[np.ndarray]:
        """Конвертирует PDF в список изображений OpenCV"""
        print(f"Converting PDF to images (DPI={dpi})...")
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=2)

        save_images = input("Do you want to save the images? [y/n]: ") if len(images) > 0 else 'n'
        if save_images.lower() == 'y':
            for i, image in enumerate(images):
                image.save(f'page_{i}.jpg', 'JPEG', quality=90)
                print(f"Saved page_{i}.jpg")

        cv_images = []
        for img in images:
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            cv_images.append(cv_img)

        print(f"Converted {len(cv_images)} pages")
        return cv_images

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Улучшает качество изображения для OCR
        """
        # Resize if too large (speed up processing)
        h, w = image.shape[:2]
        if w > 2000 or h > 2000:
            scale = min(2000 / w, 2000 / h)
            new_w, new_h = int(w * scale), int(h * scale)
            image = cv2.resize(image, (new_w, new_h))
            print(f"Resized image from {w}x{h} to {new_w}x{new_h}")

        # Convert to grayscale for better OCR
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Apply adaptive thresholding to improve text
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)

        # Denoise
        denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)

        return denoised

    def extract_text_with_easyocr(self, image: np.ndarray) -> List[Dict]:
        """
        Извлекает текст с координатами используя EasyOCR
        """
        # Preprocess image
        processed = self.preprocess_image(image)

        print(f"Running OCR on image of size {processed.shape}...")

        # Run OCR
        try:
            # EasyOCR returns list of (bbox, text, confidence)
            results = self.ocr.readtext(processed, paragraph=False)

            if not results:
                print("No text detected")
                return []

            print(f"Detected {len(results)} text elements")

            # Parse results
            items = []
            for bbox, text, confidence in results:
                if confidence < 0.5 or len(text.strip()) < 2:
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

            return items

        except Exception as e:
            print(f"EasyOCR failed: {e}")
            return []

    def extract_table_structure(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Извлекает структурированную таблицу из изображения
        """
        # Extract text using EasyOCR
        items = self.extract_text_with_easyocr(image)

        if not items:
            return {"cells": []}

        # Sort by Y (top to bottom) then X (left to right)
        items.sort(key=lambda p: (p["y"], p["x"]))

        # Group into rows (vertical grouping)
        rows = []
        current_row = []
        last_y = None
        y_threshold = 40  # Pixel threshold for grouping into same row

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
                    "confidence": item["confidence"],
                    "x": item["x"],
                    "y": item["y"]
                })

        print(f"Organized into {len(rows)} rows")

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
            print(f"\n{'=' * 60}")
            print(f"Processing page {page_num + 1}")
            print(f"{'=' * 60}")

            table_data = self.extract_table_structure(img)

            print(f"Detected structure: {table_data.get('rows', 0)} rows, {table_data.get('cols', 0)} columns")

            # Show detected text
            cells = table_data.get('cells', [])
            if cells:
                print("\nFirst 50 detected text elements:")
                for i, cell in enumerate(cells[:50]):
                    print(f"  Row {cell['row']:2d}, Col {cell['col']:2d}: {cell['text'][:60]}")

            # Parse lessons
            lessons = self.convert_table_to_lessons_v2(table_data, page_num + 1)
            if lessons:
                print(f"\n✓ Found {len(lessons)} lessons on page {page_num + 1}")
                for lesson in lessons[:10]:
                    print(f"  {lesson['day']:3s} | {lesson['time']:12s} | {lesson['subject'][:50]}")
            else:
                print(f"\n✗ No lessons found on page {page_num + 1}")

            all_lessons.extend(lessons)

        return all_lessons

    def convert_table_to_lessons_v2(self, table: Dict, page_num: int) -> List[Dict]:
        """
        Improved version for parsing schedule based on actual PDF structure
        """
        cells = table.get("cells", [])
        if not cells:
            return []

        # Group cells by row
        rows_dict = {}
        for cell in cells:
            row = cell["row"]
            if row not in rows_dict:
                rows_dict[row] = {}
            rows_dict[row][cell["col"]] = cell["text"]

        # Define Russian day names and their variations
        day_patterns = {
            'ПН': ['ПН', 'ПОНЕДЕЛЬНИК'],
            'ВТ': ['ВТ', 'ВТОРНИК'],
            'СР': ['СР', 'СРЕДА'],
            'ЧТ': ['ЧТ', 'ЧЕТВЕРГ'],
            'ПТ': ['ПТ', 'ПЯТНИЦА'],
            'СБ': ['СБ', 'СУББОТА'],
            'ВС': ['ВС', 'ВОСКРЕСЕНЬЕ']
        }

        # Find day headers
        day_columns = {}
        for row_idx, row_data in rows_dict.items():
            if row_idx < 3:  # Check first few rows for headers
                for col_idx, text in row_data.items():
                    text_upper = text.upper().strip()
                    for day, patterns in day_patterns.items():
                        if text_upper in patterns or text_upper[:2] == day:
                            day_columns[col_idx] = day
                            print(f"Found day {day} at column {col_idx} (row {row_idx}): '{text}'")
                            break

        # If no day headers found, try to identify by pattern
        if not day_columns:
            print("No day headers found, looking for schedule pattern...")
            # Look for time column and assume columns after are days
            time_column = None
            for row_idx, row_data in rows_dict.items():
                for col_idx, text in row_data.items():
                    if re.search(r'\d{1,2}:\d{2}', text) or re.search(r'\d{1,2}\s*-\s*\d{1,2}', text):
                        time_column = col_idx
                        print(f"Found time column at index {time_column}")
                        break
                if time_column is not None:
                    break

            if time_column is not None:
                # Assume columns after time column are days
                max_col = max([col for row in rows_dict.values() for col in row.keys()])
                for col in range(time_column + 1, max_col + 1):
                    day_columns[col] = f"Day_{col - time_column}"

        # Parse lessons
        lessons = []
        for row_idx, row_data in rows_dict.items():
            # Find time (usually in first column)
            time_text = ""
            for col_idx in sorted(row_data.keys()):
                text = row_data[col_idx].strip()
                # Check if this looks like time
                if re.search(r'\d{1,2}:\d{2}', text) or re.search(r'^\d{1,2}$', text) or re.search(
                        r'\d{1,2}\s*-\s*\d{1,2}', text):
                    time_text = text
                    break

            if not time_text:
                continue

            # Check each column for subjects
            for col_idx, subject in row_data.items():
                # Skip time column
                if col_idx == 0 or (time_text and row_data.get(0) == time_text):
                    if col_idx == 0 or (col_idx == 0 and time_text):
                        continue

                subject = subject.strip()
                # Filter out non-subject text
                if (subject and len(subject) > 2 and
                        subject not in ["", "-", "—", "//", "/", "|"] and
                        not subject.isdigit() and
                        len(subject) < 100):  # Avoid very long strings

                    day = day_columns.get(col_idx, f"Day_{col_idx}")

                    # Clean up subject text
                    subject = re.sub(r'\s+', ' ', subject)  # Remove extra spaces

                    lessons.append({
                        "day": day,
                        "time": time_text,
                        "subject": subject,
                        "page": page_num,
                        "row": row_idx,
                        "col": col_idx
                    })

        return lessons


if __name__ == "__main__":
    parser = ScheduleParser(language='ru')

    pdf_path = "../materials/Programmnaya inzheneriya-20-02-26.pdf"

    try:
        schedule = parser.parse_schedule(pdf_path)

        print(f"\n{'=' * 60}")
        print(f"TOTAL LESSONS FOUND: {len(schedule)}")
        print(f"{'=' * 60}")

        # # Print all lessons grouped by day
        # if schedule:
        #     by_day = defaultdict(list)
        #     for lesson in schedule:
        #         by_day[lesson['day']].append(lesson)
        #
        #     for day in sorted(by_day.keys()):
        #         print(f"\n📅 {day}:")
        #         for lesson in by_day[day]:
        #             print(f"   ⏰ {lesson['time']} - 📚 {lesson['subject']}")
        # else:
        #     print("\n⚠️ No lessons were extracted.")
        #     print("\nTroubleshooting tips:")
        #     print("1. Check if the PDF contains extractable text")
        #     print("2. Try increasing DPI in pdf_to_images()")
        #     print("3. Check if the schedule format matches expected pattern")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
