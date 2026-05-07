import asyncio
import io
import json
import os
import random
import re

import httpx
import pdfplumber
from dotenv import load_dotenv

# =========================================================
# CONFIG
# =========================================================

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPEN_ROUTER_API")

if not OPENROUTER_API_KEY:
    raise Exception("OPEN_ROUTER_API missing in .env")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Lightweight reliable models
MODELS = [
    "google/gemini-2.0-flash-001",
    "openai/gpt-4o-mini",
    "anthropic/claude-3-haiku",
]

# IMPORTANT:
# Keep low for free-tier models
MAX_CONCURRENCY = 1

# HARD STOP
# Entire request pipeline stops after this
TOTAL_MAX_ATTEMPTS = 5

# Chunk size
CHUNK_SIZE = 1200

# Shared HTTP client
client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

# Global semaphore
semaphore = asyncio.Semaphore(MAX_CONCURRENCY)


# =========================================================
# PDF EXTRACTION
# =========================================================


def extract_page_chunk_pdf(pdf_bytes: bytes):

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf_file:
        for page in pdf_file.pages:
            text = page.extract_text()

            if text and text.strip():
                yield text.strip()


# =========================================================
# TEXT CHUNKING
# =========================================================


def split_text(text: str, chunk_size: int = CHUNK_SIZE):

    text = text.strip()

    if not text:
        return []

    chunks = []

    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size].strip()

        if chunk:
            chunks.append(chunk)

    return chunks


def extract_and_chunk_pdf(pdf_bytes: bytes):

    chunks = []

    for page_text in extract_page_chunk_pdf(pdf_bytes):
        chunks.extend(split_text(page_text))

    return chunks


# =========================================================
# JSON HELPERS
# =========================================================


def parse_json(content: str):

    if not content:
        return []

    content = content.strip()

    # Direct parse
    try:
        return json.loads(content)
    except Exception:
        pass

    # Extract array
    array_match = re.search(r"\[.*\]", content, re.DOTALL)

    if array_match:
        try:
            return json.loads(array_match.group())
        except Exception:
            pass

    # Extract object
    object_match = re.search(r"\{.*\}", content, re.DOTALL)

    if object_match:
        try:
            return json.loads(object_match.group())
        except Exception:
            pass

    return []


def normalize_ai_list(data):

    if data is None:
        return []

    if isinstance(data, dict):
        return [data]

    if isinstance(data, list):
        cleaned = []

        for item in data:
            if isinstance(item, dict):
                cleaned.append(item)

        return cleaned

    return []


# =========================================================
# OPENROUTER REQUEST
# =========================================================


async def call_openrouter(prompt: str):

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error = None

    total_attempts = 0

    while total_attempts < TOTAL_MAX_ATTEMPTS:
        model = random.choice(MODELS)

        try:
            # jitter
            await asyncio.sleep(random.uniform(0.1, 0.4))

            response = await client.post(
                url=OPENROUTER_URL,
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    "temperature": 0.0,
                },
            )

            # =====================================
            # SUCCESS
            # =====================================

            if response.status_code == 200:
                data = response.json()

                if "choices" not in data:
                    raise Exception(f"Invalid response: {data}")

                return data["choices"][0]["message"]["content"]

            # =====================================
            # RATE LIMITED
            # =====================================

            elif response.status_code == 429:
                wait_time = min(2**total_attempts, 10)

                print(f"[429] Attempt={total_attempts + 1} Retrying in {wait_time}s...")

                await asyncio.sleep(wait_time)

            # =====================================
            # MODEL NOT FOUND
            # =====================================

            elif response.status_code == 404:
                print(f"[404] Model unavailable: {model}")

            # =====================================
            # OTHER ERRORS
            # =====================================

            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

        except Exception as e:
            last_error = e

            print(f"[ERROR] Attempt={total_attempts + 1} Error={e}")

            await asyncio.sleep(1)

        total_attempts += 1

    # =========================================
    # HARD STOP
    # =========================================

    raise Exception(f"MAX RETRIES EXCEEDED: {last_error}")


# =========================================================
# FLASHCARD GENERATION
# =========================================================


async def generate_flashcard(chunk: str):

    prompt = f"""
Create AT MOST ONE flashcard from the text.

Rules:
- Flashcard must be concise
- Focus only on important information
- Return ONLY valid JSON
- No markdown
- No explanations
- No extra text

Schema:
[
    {{
        "front": "string",
        "back": "string"
    }}
]

If no useful flashcard exists:
[]

TEXT:
{chunk}
"""

    raw = await call_openrouter(prompt)

    parsed = parse_json(raw)

    return normalize_ai_list(parsed)


# =========================================================
# MODULE GENERATION
# =========================================================


async def generate_module(chunk: str):

    prompt = f"""
Analyze the provided text and convert it into structured learning blocks.

Generate AT MOST ONE learning block.

Goal:
Extract important information while preserving meaning and structure.

Allowed block_type values:
- "paragraph"
- "ordered_list"
- "unordered_list"
- "definition"
- "note"

Rules:
- Return ONLY valid JSON
- No markdown
- No explanations
- No extra text

Schema:
[
    {{
        "block_type": "paragraph | ordered_list | unordered_list | definition | note",
        "title": "optional title",
        "content": "string OR array of strings"
    }}
]

If no meaningful content exists:
[]

TEXT:
{chunk}
"""

    raw = await call_openrouter(prompt)

    parsed = parse_json(raw)

    return normalize_ai_list(parsed)


# =========================================================
# SAFE WRAPPERS
# =========================================================


async def safe_generate_flashcard(chunk):

    async with semaphore:
        return await generate_flashcard(chunk)


async def safe_generate_module(chunk):

    async with semaphore:
        return await generate_module(chunk)


# =========================================================
# STREAM ENGINE
# =========================================================


async def stream_parallel(
    chunks,
    worker,
    max_items=10,
):

    sent = 0

    active_tasks = set()

    try:
        for chunk in chunks:
            task = asyncio.create_task(worker(chunk))

            active_tasks.add(task)

            # =====================================
            # Concurrency enforcement
            # =====================================

            if len(active_tasks) >= MAX_CONCURRENCY:
                done, active_tasks = await asyncio.wait(
                    active_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for finished in done:
                    try:
                        result = await finished

                        if not result:
                            continue

                        for item in result:
                            if not isinstance(item, dict):
                                continue

                            if sent >= max_items:
                                return

                            yield (f"data: {json.dumps(item)}\n\n")

                            sent += 1

                    except Exception as e:
                        # IMPORTANT:
                        # frontend receives failure
                        yield (f"data: {json.dumps({'error': str(e)})}\n\n")

        # =========================================
        # Drain remaining tasks
        # =========================================

        while active_tasks:
            done, active_tasks = await asyncio.wait(
                active_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for finished in done:
                try:
                    result = await finished

                    if not result:
                        continue

                    for item in result:
                        if not isinstance(item, dict):
                            continue

                        if sent >= max_items:
                            return

                        yield (f"data: {json.dumps(item)}\n\n")

                        sent += 1

                except Exception as e:
                    yield (f"data: {json.dumps({'error': str(e)})}\n\n")

    finally:
        # Cleanup
        for task in active_tasks:
            if not task.done():
                task.cancel()

        if active_tasks:
            await asyncio.gather(
                *active_tasks,
                return_exceptions=True,
            )

        yield 'data: {"done": true}\n\n'


# =========================================================
# PUBLIC STREAM FUNCTIONS
# =========================================================


async def generate_flashcards_parallel(chunks):

    async for item in stream_parallel(
        chunks=chunks,
        worker=safe_generate_flashcard,
        max_items=10,
    ):
        yield item


async def generate_modules_parallel(chunks):

    async for item in stream_parallel(
        chunks=chunks,
        worker=safe_generate_module,
        max_items=15,
    ):
        yield item


# =========================================================
# CLEANUP
# =========================================================


async def close_client():
    await client.aclose()


# =========================================================
# TEST
# =========================================================


async def main():

    sample = """
Why is everyone descending on a land hospitable only
to the giant hairy scorpion?

Like all good things in America,
it is because of a Facebook meme.

The locals were not amused.

There are rumors of homesteaders planning
to light up their property and shoo off
interlopers with birdshot.
"""

    try:
        result = await generate_module(sample)

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
