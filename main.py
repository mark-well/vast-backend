
import json
from fastapi import FastAPI

import features

app = FastAPI()

@app.get("/")
async def root():
    return "The sever is working here"

@app.get("/generate")
async def generate_new_reviewer():
    with open("sample-vast-item-structure.json", "r") as file:
        data = json.load(file)
        return data["modules"][0]
    
@app.get("/chunks")
async def get_chunks():
    return {"chunks": features.extract_chunks()}