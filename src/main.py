# Suppress warnings
import warnings

warnings.filterwarnings('ignore', category=UserWarning)

import os
import cv2
import numpy as np
import re
import pytesseract
from pdf2image import convert_from_path
from typing import List, Dict, Any
from collections import defaultdict

# from datetime import datetime
# from ics import Calendar, Event

# Configure Tesseract path (adjust for your system)
# Windows example:
if os.name == 'nt':  # Windows
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class ScheduleParser:
    def __init__(self, language='ru', use_gpu=False):
        """
        language: 'rus' для русского, 'eng' для английского
        """
        self.language = language
        self.use_gpu = use_gpu
        print(f"Using Tesseract OCR with language: {language}")

    def pdf_to_images(self, pdf_path: str, dpi: int = 300) -> List[np.ndarray]:
        """Конвертирует PDF в список изображений OpenCV"""
        print(f"Converting PDF to images (DPI={dpi})...")
        images = convert_from_path(pdf_path, dpi=dpi, first_page=4, last_page=4)

        save_images = input("Do you want to save the images? [y/n]: ") if len(images) > 0 else 'n'
        if save_images.lower() == 'y':
            for i, image in enumerate(images):
                image.save(f'page_{i}.jpg', 'JPEG', quality=95)
                print(f"Saved page_{i}.jpg")

        cv_images = []
        for img in images:
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            cv_images.append(cv_img)

        print(f"Converted {len(cv_images)} pages")
        return cv_images

    def preprocess_for_tesseract(self, image: np.ndarray) -> np.ndarray:
        """
        Специальная предобработка для Tesseract OCR
        """
        # Resize if too large (Tesseract works better with higher resolution)
        h, w = image.shape[:2]
        if w < 1500 or h < 1500:
            # Upscale for better recognition
            scale = max(1500 / w, 1500 / h)
            new_w, new_h = int(w * scale), int(h * scale)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            print(f"Upscaled image from {w}x{h} to {new_w}x{new_h}")

        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Apply different preprocessing techniques
        # 1. Denoise
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # 2. Apply adaptive thresholding
        binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 15, 2)

        # 3. Morphological operations to clean up text
        kernel = np.ones((1, 1), np.uint8)
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        # 4. Optional: Invert if needed (white text on black background)
        # If most pixels are black, invert
        if np.mean(cleaned) < 127:
            cleaned = cv2.bitwise_not(cleaned)

        return cleaned

    def extract_text_with_tesseract(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Извлекает текст с позициями используя Tesseract OCR
        """
        # Preprocess image
        processed = self.preprocess_for_tesseract(image)

        print(f"Running Tesseract OCR on image of size {processed.shape}...")

        # Get detailed data including bounding boxes
        try:
            # Configure Tesseract for better table recognition
            custom_config = r'--oem 3 --psm 6'  # PSM 6 = Uniform block of text
            if self.language == 'rus':
                custom_config += f' -l rus+eng'  # Russian and English
            else:
                custom_config += f' -l {self.language}'

            # Get detailed OCR data
            data = pytesseract.image_to_data(processed, config=custom_config, output_type=pytesseract.Output.DICT)

            # Also get full text for debugging
            full_text = pytesseract.image_to_string(processed, config=custom_config)

            items = []
            n_boxes = len(data['text'])

            for i in range(n_boxes):
                # Filter out empty text and low confidence
                text = data['text'][i].strip()
                confidence = int(data['conf'][i]) if data['conf'][i] != '-1' else 0

                if confidence < 30 or len(text) < 2:
                    continue

                # Get bounding box coordinates
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]

                # Calculate center
                center_x = x + w / 2
                center_y = y + h / 2

                items.append({
                    "x": center_x,
                    "y": center_y,
                    "text": text,
                    "bbox": [x, y, x + w, y + h],
                    "confidence": confidence / 100,
                    "width": w,
                    "height": h
                })

            print(f"Detected {len(items)} text elements")

            return {
                "items": items,
                "full_text": full_text,
                "num_items": len(items)
            }

        except Exception as e:
            print(f"Tesseract OCR failed: {e}")
            return {"items": [], "full_text": "", "num_items": 0}

    def extract_table_structure(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Извлекает структурированную таблицу из изображения
        """
        # Extract text using Tesseract
        ocr_result = self.extract_text_with_tesseract(image)
        items = ocr_result.get("items", [])

        if not items:
            return {"cells": [], "full_text": ocr_result.get("full_text", "")}

        # Sort by Y (top to bottom) then X (left to right)
        items.sort(key=lambda p: (p["y"], p["x"]))

        # Group into rows (vertical grouping)
        rows = []
        current_row = []
        last_y = None
        y_threshold = 30  # Pixel threshold for grouping into same row

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
                    "y": item["y"],
                    "width": item.get("width", 0),
                    "height": item.get("height", 0)
                })

        print(f"Organized into {len(rows)} rows with {len(cells)} total cells")

        # Print full text for debugging
        if ocr_result.get("full_text"):
            print("\n--- Full OCR Text ---")
            print(ocr_result["full_text"])
            print("--- End of OCR Text ---\n")

        return {
            "cells": cells,
            "rows": len(rows),
            "cols": max(len(r) for r in rows) if rows else 0,
            "full_text": ocr_result.get("full_text", "")
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

            # print(f"Detected structure: {table_data.get('rows', 0)} rows, {table_data.get('cols', 0)} columns")
            #
            # # Show detected text for debugging
            # cells = table_data.get('cells', [])
            # if cells:
            #     print("\nFirst 50 detected text elements:")
            #     for i, cell in enumerate(cells[:50]):
            #         print(f"  Row {cell['row']:2d}, Col {cell['col']:2d}: {cell['text'][:60]}")
            # else:
            #     print("No cells detected on this page")
            #     continue
            #
            # # Parse lessons
            # lessons = self.convert_table_to_lessons_tesseract(table_data, page_num + 1)
            # if lessons:
            #     print(f"\n✓ Found {len(lessons)} lessons on page {page_num + 1}")
            #     for lesson in lessons[:10]:
            #         print(f"  {lesson['day']:3s} | {lesson['time']:12s} | {lesson['subject'][:50]}")
            # else:
            #     print(f"\n✗ No lessons found on page {page_num + 1}")

            # all_lessons.extend(lessons)

        # return all_lessons

    # def convert_table_to_lessons_tesseract(self, table: Dict, page_num: int) -> List[Dict]:
    #     """
    #     Parses schedule from Tesseract OCR results
    #     """
    #     cells = table.get("cells", [])
    #     if not cells:
    #         return []
    #
    #     # Also check full text for table structure
    #     full_text = table.get("full_text", "")
    #
    #     # Group cells by row
    #     rows_dict = {}
    #     for cell in cells:
    #         row = cell["row"]
    #         if row not in rows_dict:
    #             rows_dict[row] = {}
    #         rows_dict[row][cell["col"]] = cell["text"]
    #
    #     # Define Russian day names
    #     day_patterns = {
    #         'ПН': ['ПН', 'ПНД', 'ПОНЕДЕЛЬНИК', 'ПОНЕДЕЛЬНИК'],
    #         'ВТ': ['ВТ', 'ВТР', 'ВТОРНИК'],
    #         'СР': ['СР', 'СРЕДА'],
    #         'ЧТ': ['ЧТ', 'ЧЕТВЕРГ'],
    #         'ПТ': ['ПТ', 'ПЯТНИЦА'],
    #         'СБ': ['СБ', 'СУББОТА'],
    #         'ВС': ['ВС', 'ВОСКРЕСЕНЬЕ']
    #     }
    #
    #     # Find day headers
    #     day_columns = {}
    #     for row_idx, row_data in rows_dict.items():
    #         if row_idx < 5:  # Check first few rows for headers
    #             for col_idx, text in row_data.items():
    #                 text_upper = text.upper().strip()
    #                 for day, patterns in day_patterns.items():
    #                     if any(pattern in text_upper for pattern in patterns):
    #                         day_columns[col_idx] = day
    #                         print(f"Found day {day} at column {col_idx} (row {row_idx}): '{text}'")
    #                         break
    #
    #     # If still no day columns, try to infer from full text
    #     if not day_columns and full_text:
    #         print("Looking for day names in full text...")
    #         lines = full_text.split('\n')
    #         for line_idx, line in enumerate(lines[:10]):  # Check first 10 lines
    #             for day, patterns in day_patterns.items():
    #                 for pattern in patterns:
    #                     if pattern in line.upper():
    #                         print(f"Found day {day} in line: {line}")
    #                         # Assume columns are separated by spaces/tabs
    #                         day_columns[line_idx] = day
    #                         break
    #
    #     # Parse lessons
    #     lessons = []
    #     for row_idx, row_data in rows_dict.items():
    #         # Find time column
    #         time_text = ""
    #         time_col = None
    #
    #         for col_idx, text in row_data.items():
    #             text_clean = text.strip()
    #             # Check for time patterns
    #             if (re.search(r'\d{1,2}:\d{2}', text_clean) or  # 09:00
    #                     re.search(r'^\d{1,2}$', text_clean) or  # 1, 2
    #                     re.search(r'\d{1,2}-\d{1,2}', text_clean) or  # 1-2
    #                     re.search(r'[12]\s*пар', text_clean, re.IGNORECASE) or  # 1 пара
    #                     re.search(r'^\d{1,2}\.', text_clean)):  # 1.
    #                 time_text = text_clean
    #                 time_col = col_idx
    #                 break
    #
    #         if not time_text:
    #             continue
    #
    #         # Check each column for subjects
    #         for col_idx, subject in row_data.items():
    #             if time_col is not None and col_idx == time_col:
    #                 continue
    #             if col_idx == 0 and time_text:  # Skip first column if it contains time
    #                 continue
    #
    #             subject = subject.strip()
    #             # Filter valid subjects
    #             if (subject and len(subject) > 2 and
    #                     subject not in ["", "-", "—", "//", "/", "|", "\\", "—"] and
    #                     not subject.isdigit() and
    #                     len(subject) < 150):
    #
    #                 day = day_columns.get(col_idx, f"Day_{col_idx}")
    #
    #                 # Clean subject text
    #                 subject = re.sub(r'\s+', ' ', subject)
    #                 subject = re.sub(r'[|/\\]+', ' ', subject)
    #                 subject = subject.strip()
    #
    #                 # Remove common noise
    #                 noise_words = ['лей', 'лек', 'пр', 'лаб', 'п/г', 'учебная']
    #                 for noise in noise_words:
    #                     subject = re.sub(rf'\b{noise}\b', '', subject, flags=re.IGNORECASE)
    #                 subject = re.sub(r'\s+', ' ', subject).strip()
    #
    #                 if subject:
    #                     lessons.append({
    #                         "day": day,
    #                         "time": time_text,
    #                         "subject": subject,
    #                         "page": page_num,
    #                         "row": row_idx,
    #                         "col": col_idx
    #                     })
    #
    #     # Remove duplicates
    #     unique_lessons = []
    #     seen = set()
    #     for lesson in lessons:
    #         key = (lesson['day'], lesson['time'], lesson['subject'][:50])
    #         if key not in seen:
    #             seen.add(key)
    #             unique_lessons.append(lesson)
    #
    #     return unique_lessons


if __name__ == "__main__":
    parser = ScheduleParser(language='rus', use_gpu=False)

    pdf_path = "../materials/Programmnaya inzheneriya-20-02-26.pdf"

    try:
        schedule = parser.parse_schedule(pdf_path)

        # print(f"\n{'=' * 60}")
        # print(f"TOTAL LESSONS FOUND: {len(schedule)}")
        # print(f"{'=' * 60}")

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
        #     print("1. Check if Tesseract is installed with Russian language")
        #     print("2. Verify the Tesseract path in the code")
        #     print("3. Try increasing DPI to 400 in pdf_to_images()")
        #     print("4. Check the full OCR text output above for recognition quality")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
