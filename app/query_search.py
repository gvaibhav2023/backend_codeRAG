# app/query_search.py

import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
from dotenv import load_dotenv

from app.db import SessionLocal
from app.models import CodeChunk

load_dotenv()

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5

# ===== GEMINI SETUP =====
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY not found in .env file")

genai.configure(api_key=gemini_api_key)
llm = genai.GenerativeModel("gemini-2.5-flash")

# Load embedding model once globally
embed_model = SentenceTransformer(MODEL_NAME)


def answer_question(user_id: str, question: str) -> str:
    """
    For a given user_id:
    - Load FAISS index
    - Embed the question
    - Retrieve top-k chunks
    - Fetch chunk metadata from the database
    - Build context + query Gemini
    """

    print(f"\n[QUERY] Answering question for user: {user_id}")

    # ===============================
    # STEP 1 — Load FAISS index
    # ===============================

    faiss_path = f"app/repos/{user_id}/faiss/code_index.faiss"

    if not os.path.exists(faiss_path):
        return "No FAISS index found for this user. Please ingest a repository first."

    try:
        index = faiss.read_index(faiss_path)
    except Exception:
        return "FAISS index is corrupted. Please rebuild by re-ingesting the repository."

    # ===============================
    # STEP 2 — Embed the question
    # ===============================

    query_emb = embed_model.encode(
        [question],
        normalize_embeddings=True,
        convert_to_numpy=True
    ).astype("float32")

    # ===============================
    # STEP 3 — Search FAISS
    # ===============================

    try:
        _, I = index.search(query_emb, TOP_K)
    except Exception:
        return "Error during FAISS search. Try re-ingesting the repository."

    chunk_indices = [int(idx) for idx in I[0]]

    print(f"[QUERY] Top-{TOP_K} FAISS matches: {chunk_indices}")

    # ===============================
    # STEP 4 — Fetch metadata from DB
    # ===============================

    session = SessionLocal()

    chunks = (
        session.query(CodeChunk)
        .filter(
            CodeChunk.user_id == user_id,
            CodeChunk.chunk_index.in_(chunk_indices)
        )
        .all()
    )

    session.close()

    if not chunks:
        return "No relevant code found for your question."

    # ===============================
    # STEP 5 — Build LLM context
    # ===============================

    context = ""
    for chunk in chunks:
        context += f"""
FILE: {chunk.file_name}
SYMBOL: {chunk.symbol_name}
LINES: {chunk.start_line}–{chunk.end_line}

CODE SNIPPET:
{chunk.code_snippet}

------------------------------------------
"""

    # ===============================
    # STEP 6 — Build Gemini prompt
    # ===============================

    prompt = f"""
You are a highly accurate senior code assistant.

Use ONLY the provided code snippets to answer the user's question.
Do NOT fabricate code. Do NOT hallucinate missing details.

RULES:
- Start with the file name + function/class name.
- Keep the explanation sharp and focused.
- Avoid unnecessary code expansions.
- Only use information present in the context.

CODE CONTEXT:
{context}

QUESTION:
{question}

Give the most accurate answer possible using the code context above.
if query is completely unrelated to the context,respond as you normally do on gemini as a normal human does...
"""

    # ===============================
    # STEP 7 — Query Gemini
    # ===============================

    try:
        response = llm.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Gemini API error: {e}"
