import pdfplumber
import os
import json
from dotenv import load_dotenv
import re
import httpx
import asyncio
import io

# Load environment variables
load_dotenv()
api_token = os.getenv('OPEN_ROUTER_API')
model = "stepfun/step-3.5-flash:free"
semaphore = asyncio.Semaphore(5)
client = httpx.AsyncClient(timeout=60.0)

# Extract all the contents of a pdf file, per page and store it in a list
def extract_page_chunk_pdf(pdf: bytes):
    with pdfplumber.open(io.BytesIO(pdf)) as pdf_file:
        for page in pdf_file.pages:
            text = page.extract_text()
            if text:
                yield text

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
    response = await client.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        json={
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
        }
    )

    response = response.json()
    raw = response['choices'][0]['message']
    return parse_json(raw['content'])

async def generate_flashcards_parallel(chunks):
    max_cards = 10
    concurrency = 5
    sent = 0

    active_tasks = set()

    try:
        for chunk in chunks:
            # start new task
            task = asyncio.create_task(generate_flashcard(chunk))
            active_tasks.add(task)

            # enforce concurrency limit
            if len(active_tasks) >= concurrency:
                done, active_tasks = await asyncio.wait(
                    active_tasks,
                    return_when=asyncio.FIRST_COMPLETED
                )

                for finished in done:
                    try:
                        result = await finished
                        if not result:
                            continue

                        for card in result:
                            if sent >= max_cards:
                                return

                            yield f"data: {json.dumps(card)}\n\n"
                            sent += 1

                    except Exception as e:
                        print(f"Task failed: {e}")

        # process remaining tasks
        while active_tasks:
            done, active_tasks = await asyncio.wait(
                active_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )

            for finished in done:
                try:
                    result = await finished
                    if not result:
                        continue

                    for card in result:
                        if sent >= max_cards:
                            return

                        yield f"data: {json.dumps(card)}\n\n"
                        sent += 1

                except Exception as e:
                    print(f"Task failed: {e}")

    finally:
        # cancel anything still running
        for t in active_tasks:
            if not t.done():
                t.cancel()

        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)

        yield "data: {\"done\": true}\n\n"

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
    response = await client.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        json={
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
        }
    )

    response = response.json()
    raw = response['choices'][0]['message']
    return parse_json(raw['content'])

async def generate_modules_parallel(chunks):
    max_cards = 15
    concurrency = 5
    sent = 0

    active_tasks = set()

    try:
        for chunk in chunks:
            # start new task
            task = asyncio.create_task(generate_module(chunk))
            active_tasks.add(task)

            # enforce concurrency limit
            if len(active_tasks) >= concurrency:
                done, active_tasks = await asyncio.wait(
                    active_tasks,
                    return_when=asyncio.FIRST_COMPLETED
                )

                for finished in done:
                    try:
                        result = await finished
                        if not result:
                            continue

                        for card in result:
                            if sent >= max_cards:
                                return

                            yield f"data: {json.dumps(card)}\n\n"
                            sent += 1

                    except Exception as e:
                        print(f"Task failed: {e}")

        # process remaining tasks
        while active_tasks:
            done, active_tasks = await asyncio.wait(
                active_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )

            for finished in done:
                try:
                    result = await finished
                    if not result:
                        continue

                    for card in result:
                        if sent >= max_cards:
                            return

                        yield f"data: {json.dumps(card)}\n\n"
                        sent += 1

                except Exception as e:
                    print(f"Task failed: {e}")

    finally:
        # cancel anything still running
        for t in active_tasks:
            if not t.done():
                t.cancel()

        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)

        yield "data: {\"done\": true}\n\n"
