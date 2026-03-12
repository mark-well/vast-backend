import pdfplumber
import os
import json
import os
from dotenv import load_dotenv
import re
import httpx
import asyncio
import io
import json

# Load environment variables
load_dotenv()
api_token = os.getenv('OPEN_ROUTER_API')
model = "stepfun/step-3.5-flash:free"
semaphore = asyncio.Semaphore(5)

# Extract all the contents of a pdf file, per page and store it in a list
def extract_page_chunk_pdf(pdf: bytes):
    page_chunks = []
    with pdfplumber.open(io.BytesIO(pdf)) as pdf_file:
        for page in pdf_file.pages:
            chunk = ""
            for line in page.extract_text_lines():
                chunk += line['text']
            page_chunks.append(chunk)
    return page_chunks

# Clean json
def parse_json(content):
    try:
        return json.loads(content)
    except:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())

async def safe_generate_flashcard(chunk):
    async with semaphore:
        return await generate_flashcard(chunk)

async def safe_generate_module(chunk):
    async with semaphore:
        return await generate_module(chunk)

# Generate flashcards from chunks (uses AI)
async def generate_flashcard(chunk):
    promt = f"""
Create ONE flashcard from the text. flashcard must be short.
Return ONLY JSON.
Schema:
[
    {{
        "front": "string",
        "back": "string"
    }}
]
Text:
{chunk}
"""
    client = httpx.AsyncClient(timeout=60.0)
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

async def generate_flashcards_parallel(chunks):
    sent = 0
    max_cards = 10
    tasks = [asyncio.create_task(safe_generate_flashcard(chunk)) for chunk in chunks ]

    try:
        for future in asyncio.as_completed(tasks):
            try:
                result = await future
                if not result:
                    continue

                for card in result:
                    if sent >= max_cards:
                        yield "data: {\"done\": true}\n\n"
                        return
                    
                    yield f"data: {json.dumps(card)}\n\n"
                    sent += 1
                    await asyncio.sleep(0)
            
            except Exception as e:
                print(f"Task falied: {e}")
                continue

        yield "data: {\"done\": true}\n\n"

    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

            if task:
                await asyncio.gather(*tasks, return_exceptions=True)

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
    client = httpx.AsyncClient(timeout=60.0)
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

async def generate_modules_parallel(chunks):
    max_cards = 15
    sent_count = 0
    # Create tasks immediately to start parallel execution
    tasks = [asyncio.create_task(safe_generate_module(chunk)) for chunk in chunks]

    try:
        # as_completed yields results as soon as they are ready
        for future in asyncio.as_completed(tasks):
            try:
                result = await future
                if not result:
                    continue

                for card in result:
                    if sent_count >= max_cards:
                        return # Exit the generator; finally block handles cleanup

                    yield f"data: {json.dumps(card)}\n\n"
                    sent_count += 1
                    await asyncio.sleep(0)

            except Exception as e:
                # Log individual task failures without crashing the whole stream
                print(f"Task failed: {e}")

    finally:
        # --- Clean Shutdown ---
        # 1. Cancel anything still running
        for t in tasks:
            if not t.done():
                t.cancel()
        
        # 2. Wait for all tasks to acknowledge cancellation/finish
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        # 3. Always send a final closing signal
        yield "data: {\"done\": true}\n\n"

def main():
    return