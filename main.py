
import features
import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated
import asyncio
from dotenv import load_dotenv
import os
import time
from fastapi.concurrency import run_in_threadpool

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

@app.post("/generate-modules")
async def generate_module_blocks(file: UploadFile):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a pdf")

    pdf_content = await file.read()
    chunks = await run_in_threadpool(features.extract_page_chunk_pdf, pdf_content)
    return StreamingResponse(
        features.generate_modules_parallel(chunks),
        media_type="text/event-stream"
    )

@app.post("/generate-flashcard")
async def generate_flashcard(file: UploadFile):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a pdf")

    pdf_content = await file.read()
    chunks = await run_in_threadpool(features.extract_page_chunk_pdf, pdf_content)
    return StreamingResponse(
        features.generate_flashcards_parallel(chunks),
        media_type="text/event-stream"
    )

@app.get("/wakeup")
async def wake_up_server():
    return {"status": "awake"}

@app.get("/module")
def generate_module():
    chunks = []
    try:
        with open("sample2.pdf", 'rb') as file:
            chunks = features.extract_page_chunk_pdf(file.read())
    except FileNotFoundError:
        return {"message": "file not found"}
    except PermissionError:
        return {"message": "permission error"}
    
    return StreamingResponse(
        features.generate_modules_parallel(chunks),
        media_type="text/event-stream"
    )