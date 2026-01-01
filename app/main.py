# app/main.py

import os
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Internal modules
from app.clone_repo import clone_repo_for_user
from app.ingest import run_ingest
from app.build_vector_index import build_faiss_index
from app.query_search import answer_question
from app.db import init_db   # ✅ ONLY ADDITION


# ======================= Lifespan (startup / shutdown) =======================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🔹 Startup
    init_db()   # creates tables if not present
    yield
    # 🔹 Shutdown (nothing needed now)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================= Request Models =======================

class IngestRequest(BaseModel):
    user_id: str
    github_url: str


class QueryRequest(BaseModel):
    user_id: str
    question: str


# ========================= Health Check ========================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "message": "CodeRAG backend is running 🚀",
        "docs": "/docs",
        "endpoints": {
            "POST /ingest": "Clone repo → parse → build FAISS → store metadata",
            "POST /query": "Ask a question about the ingested repository",
        }
    }


# ========================== INGEST API ==========================

@app.post("/ingest")
def ingest_api(req: IngestRequest):
    user_id = req.user_id
    github_url = req.github_url

    repo_path = None
    try:
        repo_path = clone_repo_for_user(user_id, github_url)
        chunks = run_ingest(repo_path)

        if not chunks:
            raise HTTPException(400, "No parsable code found")

        build_faiss_index(user_id, chunks)

        return {"status": "success"}

    finally:
        # 🔥 ALWAYS CLEAN TEMP REPO
        if repo_path and os.path.exists(repo_path):
            shutil.rmtree(repo_path, ignore_errors=True)


# =========================== QUERY API ==========================

@app.post("/query")
def query_api(req: QueryRequest):
    try:
        answer = answer_question(req.user_id, req.question)
        return {
            "user_id": req.user_id,
            "answer": answer
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
