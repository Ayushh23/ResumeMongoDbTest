import base64
import io
import fitz  # PyMuPDF
import os
from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pymongo import MongoClient
from bson.objectid import ObjectId
import google.generativeai as genai

# ================== CONFIG ======================
MONGO_URI = "mongodb+srv://ayushsuryavanshi03:ayushsuryavanshi03@cluster0.i9n9dqa.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "resume_analyzer"
COLLECTION_NAME = "prompts"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
prompt_collection = db[COLLECTION_NAME]

ADMIN_TOKEN = "drdoom"

genai.configure(api_key="AIzaSyCcoQ40u_iM1BIvp26iLqVTWdHp3Ky0TAw")

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============== DATABASE LOGIC =================

def initialize_prompts():
    if prompt_collection.count_documents({}) == 0:
        prompts = [
            {"prompt_text": "Is the resume tailored to the target job description?"},
            {"prompt_text": "Are there any red flags like gaps or poor formatting?"},
            {"prompt_text": "What improvements can enhance clarity or impact?"}
        ]
        prompt_collection.insert_many(prompts)

def get_prompts_from_db():
    return [doc["prompt_text"] for doc in prompt_collection.find().sort("_id", 1)]

# ================ MAIN ROUTES ===================

@app.post("/evaluate")
async def evaluate_resume(base64_pdf: str = Form(...)):
    try:
        pdf_bytes = base64.b64decode(base64_pdf)
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        first_page = pdf_doc[0].get_pixmap()
        img_byte_arr = io.BytesIO(first_page.tobytes("jpeg"))
        image_base64 = base64.b64encode(img_byte_arr.getvalue()).decode()
    except Exception as e:
        return {"error": f"PDF processing failed: {str(e)}"}

    prompts = get_prompts_from_db()
    if len(prompts) < 3:
        return {"error": "Not enough prompts in database."}

    master_prompt = f"""
You are a highly skilled HR professional, career coach, and ATS expert.

1. {prompts[0]}
2. {prompts[1]}
3. {prompts[2]}

Provide a detailed report that includes:
- Job-fit analysis
- Improvement suggestions
    """

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([
            "Analyze this resume carefully:",
            {"mime_type": "image/jpeg", "data": image_base64},
            master_prompt
        ])
        response_text = response.text
    except Exception as e:
        return {"error": f"Gemini API error: {str(e)}"}

    return {"response": response_text}

# ============== ADMIN ROUTES ======================

class PromptUpdate(BaseModel):
    prompt_text: str
    prompt_id: str

@app.post("/update_prompt")
async def update_prompt(data: PromptUpdate, request: Request):
    try:
        result = prompt_collection.update_one({"_id": ObjectId(data.prompt_id)}, {"$set": {"prompt_text": data.prompt_text}})
        if result.modified_count == 1:
            return {"status": True}
        return {"status": False, "error": "Prompt not found or unchanged."}
    except Exception as e:
        return {"status": False, "error": str(e)}

@app.get("/debug_prompts")
async def debug_prompts():
    try:
        prompts = list(prompt_collection.find({}, {"prompt_text": 1}))
        for prompt in prompts:
            prompt["prompt_id"] = str(prompt["_id"])
            del prompt["_id"]
        return {"prompts": prompts}
    except Exception as e:
        return {"status": False, "error": str(e)}

# =============== FRONTEND SERVING ================
current_dir = os.path.dirname(os.path.abspath(__file__))


# ================ INIT ON START ==================
initialize_prompts()
