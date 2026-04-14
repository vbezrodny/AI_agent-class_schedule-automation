import base64
import os
from dotenv import load_dotenv
from mistralai.client import Mistral

load_dotenv()
os.getenv('MISTRAL_API_KEY')
api_key = os.environ['MISTRAL_API_KEY']

client = Mistral(api_key=api_key)


def encode_pdf(pdf_path):
    with open(pdf_path, "rb") as pdf_file:
        return base64.b64encode(pdf_file.read()).decode("utf-8")


pdf_path = "../materials/Programmnaya inzheneriya-20-02-26.pdf"
pdf_name = pdf_path.split("/")[-1]
base64_pdf = encode_pdf(pdf_path)

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

with open('../materials/parsing_results/mistral_ai.md', 'w', encoding='utf-8') as f:
    for page in ocr_response.pages:
        f.write(f"# Page {page.index + 1}\n\n")
        f.write(page.markdown)
        f.write("\n\n---\n\n")

print("file was written successfully")
