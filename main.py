
import features
import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated
import asyncio
from dotenv import load_dotenv
import os

load_dotenv()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv('ALLOWED_ORIGIN')],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return "The sever is working here"

@app.post("/generate")
async def generate_new_reviewer(file: UploadFile):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a pdf")

    pdf_content = await file.read()
    async with asyncio.TaskGroup() as tg:
        module_task = tg.create_task(generate_module_block(pdf_content))
        flashcard_task = tg.create_task(generate_flashcards(pdf_content))
    
    return {
        "fileName": file.filename,
        "flashcards": flashcard_task.result(),
        "moduleBlocks": module_task.result()
    }

@app.get("/chunks")
async def get_chunks():
    return "Not Implemented yet"
    # return {"chunks": features.extract_chunks()}

async def generate_flashcards(pdf):
    chunks = features.extract_chunks(pdf);
    print("chunks are loaded")
    flashcards = []

    async for module in features.generate_flashcards_parallel(chunks):
        clean_data = module.replace("data: ", "").strip()
        flashcards.append(features.parse_json(clean_data))

    return flashcards

async def generate_module_block(pdf):
    chunks = features.extract_chunks(pdf);
    print("chunks are loaded")
    modules = []

    async for module in features.generate_modules_parallel(chunks):
        clean_data = module.replace("data: ", "").strip()
        modules.append(features.parse_json(clean_data))

    return modules