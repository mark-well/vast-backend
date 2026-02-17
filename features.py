import pdfplumber
import os
import json
import os
from dotenv import load_dotenv
import re
import httpx
import asyncio

# Load environment variables
load_dotenv()

api_token = os.getenv('OPEN_ROUTER_API')
model = "stepfun/step-3.5-flash:free"
# model = "liquid/lfm-2.5-1.2b-thinking:free"
# model = "arcee-ai/trinity-large-preview:free"
semaphore = asyncio.Semaphore(10)

# Extract from a pdf file
def extract_text_from_pdf(pdf):
    with pdfplumber.open(pdf) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(
            use_text_flow = True,
            keep_blank_chars = False
        )

    for w in words:
        print(w)

# Extract a block of text from pdf
def extract_block_of_text_from_pdf(pdf):
    blocks=[]
    with pdfplumber.open(pdf) as pdf:
        for page in pdf.pages:
            for line in page.extract_text_lines():
                blocks.append({
                    "text": line["text"],
                    "top": line["top"],
                    "size": line["chars"][0]["size"]
                })
    return blocks

def chunk_blocks(blocks, max_char=1000, overlap=100):
    chunks = []
    current = ""

    for block in blocks:
        text = block["text"]

        if len(current) + len(text) > max_char:
            chunks.append(current)
            overlap_text = current[-overlap:] if overlap > 0 else ""
            current = overlap_text + text + "\n"
        else:
            current += text + "\n"

    if current:
        current = re.sub(r'\s+', ' ', current).strip()
        chunks.append(current)
    return chunks

def create_output_file(file_name):
    if not os.path.exists(file_name):
        open(file_name, "x")

# extract blocks of text then save to a file (for debugging only)
def extract_block_text_save_to_file():
    file_name = "blocks.json"
    blocks = extract_block_of_text_from_pdf("sample.pdf")
    create_output_file(file_name)

    with open(file_name, "w") as f:
        for block in blocks:
            f.write(json.dumps(block))
            f.write("\n")

def extract_chunks():
    blocks = extract_block_of_text_from_pdf("sample2.pdf")
    chunks = chunk_blocks(blocks)
    return chunks

# Clean json
def parse_json(content):
    try:
        return json.loads(content)
    except:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())

# Generate flashcards from chunks (uses AI)
async def generate_flashcard(chunk):
    promt = f"""
Create ONE flashcard from the text. flashcard must be short. id is incremental
Return ONLY JSON.
Schema:
[
    {{
        "id": int,
        "front": "string",
        "back": "string"
    }}
]
Text:
{chunk}
"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps({
                "model": f"{model}",
                "messages": [
                    {
                        "role": "user",
                        "content": promt
                    }
                ],
                "temperature": 0.0,
                "reasoning": {
                    "enabled": True,
                    "effort": "minimal"
                }
            })
        )

        response = response.json()
        raw = response['choices'][0]['message']
        return parse_json(raw['content'])

async def safe_generate(chunk):
    async with semaphore:
        return await generate_flashcard(chunk)

async def generate_flashcards_parallel(chunks):
    # all_cards = []
    # tasks = [
    #     safe_generate(chunk)
    #     for chunk in chunks
    # ]

    # result = await asyncio.gather(*tasks, return_exceptions=True)

    # for r in result:
    #     if isinstance(r, Exception):
    #         print("Error: ", r)
    #         continue
    #     all_cards.extend(r)
    # return all_cards

    sent = 0
    max_cards = 10
    # Create actual tasks
    tasks = [
        asyncio.create_task(safe_generate(chunk))
        for chunk in chunks
    ]

    # Process results as they finish
    for future in asyncio.as_completed(tasks):
        try:
            result = await future
        except Exception as e:
            print("Error:", e)
            continue

        if not result:
            continue

        for card in result:

            if sent >= max_cards:
                return  # stop streaming

            yield f"data: {json.dumps(card)}\n\n"
            sent += 1

# Generate module blocks from chunks (uses AI)
async def generate_module(chunk):
    promt = f"""
Aanalyze the provided text and convert it into structured learning block. generate only exactly one or none.
Goal is to extract the important information while preserving meaning, logical structure.
IMPORTANT RULE: Identify paragraphs, ordered lists, unordered lists, and key concepts.
OUTPUT FORMAT RULES: Return ONLY valid JSON. No markdown. No explanations. No extra text.
Allowed block_type values: "paragraph", "ordered_list", "unordered_list", "definition", "note"
SCHEMA:
[
  {{
    "block_type": "paragraph/ordered_list/unordered_list/definition/note",
    "title": "Optional heading title",
    "content": <string if paragraph array of strin if list>
  }}
]
If no meaningful content exists, return:
[]
TEXT TO PROCESS:
{chunk}
"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps({
                "model": f"{model}",
                "messages": [
                    {
                        "role": "user",
                        "content": promt
                    }
                ],
                "temperature": 0.0,
                "reasoning": {
                    "enabled": True,
                    "effort": "minimal"
                }
            })
        )

        response = response.json()
        raw = response['choices'][0]['message']
        return parse_json(raw['content'])

async def safe_generate_module(chunk):
    async with semaphore:
        return await generate_module(chunk)

async def generate_modules_parallel(chunks):
    sent = 0
    max_cards = 10
    # Create actual tasks
    tasks = [
        asyncio.create_task(safe_generate_module(chunk))
        for chunk in chunks
    ]

    # Process results as they finish
    for future in asyncio.as_completed(tasks):
        try:
            result = await future
        except Exception as e:
            print("Error:", e)
            continue

        if not result:
            continue

        for card in result:

            if sent >= max_cards:
                return  # stop streaming

            yield f"data: {json.dumps(card)}\n\n"
            sent += 1

def main():
    return