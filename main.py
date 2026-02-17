
import features
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return "The sever is working here"

@app.get("/generate")
async def generate_new_reviewer():
    with open("sample-vast-item-structure.json", "r") as file:
        data = json.load(file)
        return data

@app.get("/chunks")
async def get_chunks():
    return {"chunks": features.extract_chunks()}

@app.get("/flashcards")
async def generate_flashcards():
    chunks = features.extract_chunks();
    print("chunks are loaded")
    # return await features.generate_flashcards_parallel(chunks)
    # return await features.safe_generate(chunks[7])
    return StreamingResponse(
        features.generate_flashcards_parallel(chunks),
        media_type="text/event-stream"
    )

@app.get("/module")
async def generate_module():
    chunks = features.extract_chunks();
    print("chunks are loaded")

    # return await features.safe_generate_module(chunks[9])
    return StreamingResponse(
        features.generate_modules_parallel(chunks),
        media_type="text/event-stream"
    )
