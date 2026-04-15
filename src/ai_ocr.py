import base64
import os
from dotenv import load_dotenv
from pathlib import Path
from mistralai.client import Mistral

load_dotenv()
os.getenv('MISTRAL_API_KEY')
api_key = os.environ['MISTRAL_API_KEY']

client = Mistral(api_key=api_key)


def encode_pdf(pdf_path: str):
    with open(pdf_path, "rb") as pdf_file:
        return base64.b64encode(pdf_file.read()).decode("utf-8")


def make_markdown(pdf_name: str, pdf_path: str) -> str:
    print("\n" + "=" * 70)
    print(f"🤖 НАЧИНАЕМ СКАНИРОВАНИЕ: {pdf_name}")
    print("=" * 70)

    temp_dir = Path('../materials/temp_markdown')
    temp_dir.mkdir(parents=True, exist_ok=True)

    base_name = Path(pdf_name).stem
    output_path = temp_dir / f'{base_name}.md'

    print(f"📄 Обработка PDF: {pdf_path}")
    print(f"📝 Выходной файл: {output_path}")

    try:
        print("📤 Кодирование PDF в base64...")
        base64_pdf = encode_pdf(pdf_path)

        print("🔄 Отправка запроса в Mistral AI OCR...")
        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "document_name": pdf_name,
                "type": "document_url",
                "document_url": f'data:application/pdf;base64,{base64_pdf}'
            },
            table_format="markdown",
            include_image_base64=False
        )

        print(f"✅ OCR завершен. Получено {len(ocr_response.pages)} страниц")

        print(ocr_response)

        full_content = []

        for page_idx, page in enumerate(ocr_response.pages):
            page_content = page.markdown

            if page.tables:
                for table in page.tables:
                    table_content = table.content

                    table_markdown = f"\n{table_content}\n"
                    page_content = page_content.replace(f'[{table.id}]({table.id})', table_markdown)

            full_content.append(f"# Page {page_idx + 1}\n\n{page_content}\n\n---\n\n")

        print(f"💾 Сохранение в {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(''.join(full_content))

        print(f"✅ Файл {base_name}.md был записан в директорию: {temp_dir}")
        print(f"   Полный путь: {output_path}")
        print("\n" + "=" * 70)

        return str(output_path)

    except Exception as e:
        print(f"❌ Ошибка при обработке PDF: {str(e)}")
        raise


def test_ocr(pdf_name: str, pdf_path: str):
    """ Тестовая функция для проверки OCR """
    print(f"Тестирование OCR для {pdf_name}")
    print(f"Путь к PDF: {pdf_path}")
    print(f"Файл существует: {Path(pdf_path).exists()}")

    try:
        result = make_markdown(pdf_name, pdf_path)
        print(f"Результат: {result}")
        print(f"Файл создан: {Path(result).exists()}")
        return result
    except Exception as e:
        print(f"Ошибка: {e}")
        return None


if __name__ == "__main__":
    test_ocr("test.pdf", "../materials/pdf/Programmnaya inzheneriya-20-02-26.pdf")
