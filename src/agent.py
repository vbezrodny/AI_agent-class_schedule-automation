import os
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import json

import ai_ocr
import schedule_parser


class ScheduleAgent:
    """
    Агент для автоматического парсинга расписания из PDF файлов
    """

    def __init__(self, base_path: str = '../materials'):
        """
        Args:
            base_path: базовый путь к директории с материалами
        """
        self.base_path = Path(base_path)
        self.pdf_dir = self.base_path / 'pdf'
        self.processed_dir = self.base_path / 'processed'

        # Создаем директории
        self._ensure_directories()

        # История обработки
        self.processing_history = []
        self.history_file = self.base_path / 'processing_history.json'
        self._load_history()

    def _ensure_directories(self):
        """ Создает необходимые директории """
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        print(f"✅ Директории готовы:")
        print(f"   PDF: {self.pdf_dir}")
        print(f"   Processed: {self.processed_dir}")

    def _sanitize_folder_name(self, name: str) -> str:
        """ Очищает имя папки от недопустимых символов """
        # Заменяем недопустимые символы на _
        invalid_chars = r'[<>:"/\\|?*]'
        name = re.sub(invalid_chars, '_', name)
        name = ' '.join(name.split())
        return name.strip()

    def _get_output_paths(self, metadata: Dict, pdf_name: str) -> Dict[str, Path]:
        """ Определяет пути для сохранения файлов на основе metadata """
        profile = metadata.get('profile', 'Неизвестный профиль') if metadata else 'Неизвестный профиль'
        group = metadata.get('group', 'Неизвестное направление') if metadata else 'Неизвестное направление'

        # Если профиль или группа пустые, используем имя PDF файла
        if not profile or profile == 'Неизвестный профиль':
            profile = Path(pdf_name).stem
        if not group or group == 'Неизвестное направление':
            group = Path(pdf_name).stem

        profile_clean = self._sanitize_folder_name(profile)
        group_clean = self._sanitize_folder_name(group)

        output_dir = self.processed_dir / profile_clean / group_clean
        output_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = f"{group_clean}_{date_str}"

        return {
            'directory': output_dir,
            'base_name': base_name,
            'markdown': output_dir / f'{base_name}_source.md',
            'schedule_json': output_dir / f'{base_name}_schedule.json',
            'calendar_json': output_dir / f'{base_name}_calendar.json',
            'ics': output_dir / f'{base_name}_calendar.ics',
            'latest_markdown': output_dir / 'latest_source.md',
            'latest_schedule_json': output_dir / 'latest_schedule.json',
            'latest_calendar_json': output_dir / 'latest_calendar.json',
            'latest_ics': output_dir / 'latest_calendar.ics'
        }

    def _load_history(self):
        """ Загружает историю обработки файлов """
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.processing_history = json.load(f)
                print(f"📜 Загружена история обработки ({len(self.processing_history)} файлов)")
            except:
                self.processing_history = []
        else:
            self.processing_history = []

    def _save_history(self):
        """ Сохраняет историю обработки """
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.processing_history, f, ensure_ascii=False, indent=2)

    def _is_already_processed(self, pdf_name: str) -> bool:
        """ Проверяет, был ли файл уже обработан """
        for record in self.processing_history:
            if record['pdf_name'] == pdf_name:
                return True
        return False

    def _add_to_history(self, pdf_name: str, success: bool, output_paths: Dict, metadata: Dict):
        """Добавляет запись в историю обработки"""
        history_entry = {
            'pdf_name': pdf_name,
            'processed_at': datetime.now().isoformat(),
            'success': success,
            'profile': metadata.get('profile', '') if metadata else '',
            'group': metadata.get('group', '') if metadata else '',
        }

        # Добавляем output_directory и output_files только если они есть и success=True
        if success and output_paths and 'directory' in output_paths:
            history_entry['output_directory'] = str(output_paths['directory'])
            history_entry['output_files'] = [str(p) for p in output_paths.values() if
                                             p and hasattr(p, 'exists') and p.exists()]
        else:
            history_entry['output_directory'] = ''
            history_entry['output_files'] = []

        self.processing_history.append(history_entry)
        self._save_history()

    def get_pdf_files(self) -> List[Dict]:
        """ Получает список PDF файлов с информацией о них """
        pdf_files = []

        for file_path in self.pdf_dir.glob('*.pdf'):
            stat = file_path.stat()
            pdf_files.append({
                'name': file_path.name,
                'path': str(file_path),
                'size_mb': stat.st_size / (1024 * 1024),
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'is_processed': self._is_already_processed(file_path.name)
            })

        pdf_files.sort(key=lambda x: x['modified'], reverse=True)
        return pdf_files

    def display_pdf_list(self, pdf_files: List[Dict]):
        """ Отображает список PDF файлов """
        print("\n" + "=" * 70)
        print("📚 ДОСТУПНЫЕ РАСПИСАНИЯ")
        print("=" * 70)

        for i, pdf in enumerate(pdf_files, start=1):
            status = "✅" if pdf['is_processed'] else "🆕"
            print(f"{i:2d}. {status} {pdf['name']}")
            print(f"     📅 {pdf['modified'].strftime('%d.%m.%Y %H:%M')} | 📦 {pdf['size_mb']:.2f} MB")

        print("=" * 70)

    def select_pdf_file(self, pdf_files: List[Dict]) -> Optional[Dict]:
        """ Интерактивный выбор PDF файла """
        while True:
            self.display_pdf_list(pdf_files)

            choice = input("\n📌 Выберите расписание:\n"
                           "   • Введите номер файла (1, 2, 3...)\n"
                           "   • Или введите название файла\n"
                           "   • Или введите 'all' для обработки всех новых\n"
                           "   • Или 'history' для просмотра истории\n"
                           "   • Или 'q' для выхода\n\n"
                           "👉 Ваш выбор: ").strip()

            if choice.lower() == 'q':
                return None

            if choice.lower() == 'history':
                self.show_history()
                continue

            if choice.lower() == 'all':
                unprocessed = [f for f in pdf_files if not f['is_processed']]
                if not unprocessed:
                    print("❌ Нет новых файлов для обработки!")
                    continue
                return {'all_unprocessed': unprocessed}

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(pdf_files):
                    return pdf_files[idx]
                else:
                    print(f"❌ Неверный номер. Введите число от 1 до {len(pdf_files)}")
                    continue

            for pdf in pdf_files:
                if choice.lower() in pdf['name'].lower():
                    return pdf

            print("❌ Файл не найден. Попробуйте снова.")

    def process_pdf(self, pdf_info: Dict) -> bool:
        """ Обрабатывает один PDF файл """
        pdf_name = pdf_info['name']
        pdf_path = pdf_info['path']

        print("\n" + "=" * 70)
        print(f"🚀 НАЧАЛО ОБРАБОТКИ: {pdf_name}")
        print("=" * 70)

        # Инициализируем переменные для блока except
        temp_markdown_path = None
        output_paths = None
        metadata = {}

        try:
            # Шаг 1: OCR -> Markdown
            print("\n📖 Шаг 1: OCR обработка PDF...")
            temp_markdown_path = ai_ocr.make_markdown(pdf_name, pdf_path)

            if not temp_markdown_path or not Path(temp_markdown_path).exists():
                raise Exception("⚠️ Ошибка при создании Markdown файла")

            print(f"✅ Временный Markdown создан: {temp_markdown_path}")

            # Шаг 2: Извлечение метаданных
            print("\n📊 Шаг 2: Извлечение метаданных...")
            with open(temp_markdown_path, 'r', encoding='utf-8') as f:
                text = f.read()

            metadata = schedule_parser.extract_metadata_from_md(text)

            print(f"📋 Найден профиль: {metadata.get('profile', 'Не указан')}")
            print(f"📋 Направление: {metadata.get('group', 'Не указано')}")

            # Шаг 3: Парсинг всех таблиц
            print("\n📊 Шаг 3: Парсинг расписаний...")
            schedules = schedule_parser.parse_schedule_to_json(text)

            if not schedules:
                raise Exception("⚠️ Расписания не найдены в markdown файле")

            print(f"📊 Найдено расписаний: {len(schedules)}")

            # Шаг 4: Сохранение каждого расписания
            print("\n📝 Шаг 4: Сохранение результатов...")

            output_paths = self._get_output_paths(metadata, pdf_name)
            output_paths['directory'].mkdir(parents=True, exist_ok=True)

            saved_files = []

            for schedule_item in schedules:
                table_idx = schedule_item['table_index']
                schedule_data = schedule_item['schedule']

                # Обрабатываем чередование
                final_schedule = schedule_parser.process_schedule_with_alternation(schedule_data)

                # Создаем имя файла для этой таблицы
                if len(schedules) > 1:
                    suffix = f"_table_{table_idx + 1}"
                else:
                    suffix = ""

                # Сохраняем JSON
                result = {
                    "metadata": metadata,
                    "table_index": table_idx,
                    "schedule": final_schedule
                }

                json_path = output_paths['directory'] / f"{output_paths['base_name']}{suffix}_schedule.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                saved_files.append(json_path)
                print(f"✅ JSON сохранен: {json_path.name}")

                # Создаем календарь
                calendar_json = schedule_parser.create_calendar_json(final_schedule, metadata)

                # Сохраняем Calendar JSON
                calendar_json_path = output_paths['directory'] / f"{output_paths['base_name']}{suffix}_calendar.json"
                with open(calendar_json_path, 'w', encoding='utf-8') as f:
                    json.dump(calendar_json, f, ensure_ascii=False, indent=2)
                saved_files.append(calendar_json_path)

                # Сохраняем ICS
                ics_path = output_paths['directory'] / f"{output_paths['base_name']}{suffix}_calendar.ics"
                schedule_parser.save_as_ics(calendar_json, str(ics_path).replace('.ics', ''))
                saved_files.append(ics_path)
                print(f"✅ ICS сохранен: {ics_path.name}")

            # Сохраняем также исходный markdown
            import shutil
            shutil.copy2(Path(temp_markdown_path), output_paths['markdown'])
            saved_files.append(output_paths['markdown'])
            print(f"✅ Markdown сохранен: {output_paths['markdown'].name}")

            # Очищаем временный файл
            if temp_markdown_path and Path(temp_markdown_path).exists():
                Path(temp_markdown_path).unlink()

            # Сохраняем историю
            self._add_to_history(pdf_name, True, output_paths, metadata)

            print("\n" + "=" * 70)
            print(f"✅ ОБРАБОТКА ЗАВЕРШЕНА: {pdf_name}")
            print("=" * 70)
            print(f"\n📁 Результаты сохранены в:")
            print(f"   {output_paths['directory']}")
            print(f"\n📄 Создано файлов: {len(saved_files)}")
            for f in saved_files:
                print(f"   • {f.name}")

            return True

        except Exception as e:
            print(f"\n❌ ОШИБКА при обработке {pdf_name}: {str(e)}")
            import traceback
            traceback.print_exc()

            # Передаем пустой словарь для output_paths при ошибке
            self._add_to_history(pdf_name, False, {}, metadata)
            return False

    def process_multiple_pdfs(self, pdf_list: List[Dict]) -> Dict:
        """ Обрабатывает несколько PDF файлов """
        results = {
            'total': len(pdf_list),
            'success': 0,
            'failed': 0,
            'files': []
        }

        for i, pdf_info in enumerate(pdf_list, start=1):
            print(f"\n{'=' * 70}")
            print(f"📄 Обработка {i}/{len(pdf_list)}: {pdf_info['name']}")
            print(f"{'=' * 70}")
            success = self.process_pdf(pdf_info)

            if success:
                results['success'] += 1
                results['files'].append({'name': pdf_info['name'], 'status': 'success'})
            else:
                results['failed'] += 1
                results['files'].append({'name': pdf_info['name'], 'status': 'failed'})

        return results

    def show_history(self):
        """ Показывает историю обработки """
        if not self.processing_history:
            print("\n📜 История обработки пуста")
            return

        print("\n" + "=" * 70)
        print("📜 ИСТОРИЯ ОБРАБОТКИ (последние 20)")
        print("=" * 70)

        for record in self.processing_history[-20:]:  # последние 20 записей
            status = "✅" if record['success'] else "❌"
            print(f"\n{status} {record['pdf_name']}")
            print(f"   📅 {record['processed_at']}")
            if record.get('profile'):
                print(f"   📁 {record.get('profile', '?')} / {record.get('group', '?')}")
            if record.get('output_directory'):
                print(f"   📂 {record['output_directory']}")

    def run(self):
        """ Основной цикл работы агента """
        print("\n" + "=" * 70)
        print("🤖 АГЕНТ ПАРСИНГА РАСПИСАНИЯ")
        print("=" * 70)

        while True:
            pdf_files = self.get_pdf_files()

            if not pdf_files:
                print("\n❌ Нет PDF файлов в директории!")
                print(f"📁 Положите PDF файлы в: {self.pdf_dir}")
                input("\nНажмите Enter для повтора или Ctrl+C для выхода...")
                continue

            selected = self.select_pdf_file(pdf_files)

            if selected is None:
                print("\n👋 До свидания!")
                break

            if 'all_unprocessed' in selected:
                results = self.process_multiple_pdfs(selected['all_unprocessed'])
                print("\n" + "=" * 70)
                print("📊 ИТОГИ ОБРАБОТКИ")
                print("=" * 70)
                print(f"   ✅ Успешно: {results['success']}")
                print(f"   ❌ Ошибок: {results['failed']}")
                print(f"   📊 Всего: {results['total']}")
            else:
                self.process_pdf(selected)

            choice = input("\n\n🔄 Продолжить работу? (y/n): ").strip().lower()
            if choice != 'y':
                print("\n👋 До свидания!")
                break


def main():
    agent = ScheduleAgent(base_path='../materials')
    agent.run()


if __name__ == "__main__":
    main()
