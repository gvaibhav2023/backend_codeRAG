# app/build_vector_index.py

import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from app.db import SessionLocal
from app.models import CodeChunk

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Load model globally once (fast)
model = SentenceTransformer(MODEL_NAME)


def build_faiss_index(user_id: str, chunks: list):
    """
    Build FAISS index + store metadata in PostgreSQL.

    ✔ Supports ONE repo per user
    ✔ Deletes previous FAISS + metadata
    ✔ Stores FAISS under: app/repos/<user_id>/faiss/
    ✔ Does NOT save chunks.json or metadata.json
    """

    print(f"\n[FAISS] === Building new FAISS index for user {user_id} ===")

    # ============================================================
    # CHECK — If no chunks extracted, fail early
    # ============================================================

    if not chunks:
        raise ValueError("[FAISS ERROR] No chunks received. Repo may be empty or unsupported.")

    # ============================================================
    # STEP 1 — Delete old FAISS files + DB metadata
    # ============================================================

    session = SessionLocal()

    print("[DB] Removing old metadata for this user...")
    session.query(CodeChunk).filter(CodeChunk.user_id == user_id).delete()
    session.commit()

    # Prepare FAISS folder
    base_dir = f"app/repos/{user_id}/faiss"
    os.makedirs(base_dir, exist_ok=True)

    # Clean old FAISS files
    for file in ["embeddings.npy", "code_index.faiss"]:
        path = os.path.join(base_dir, file)
        if os.path.exists(path):
            os.remove(path)

    # ============================================================
    # STEP 2 — Generate embeddings
    # ============================================================

    print(f"[FAISS] Generating embeddings for {len(chunks)} chunks...")

    texts = [c.get("text_to_embed", "") for c in chunks]

    embeddings = model.encode(
        texts,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True
    ).astype("float32")

    # Save embeddings (optional but useful for debugging)
    emb_path = os.path.join(base_dir, "embeddings.npy")
    np.save(emb_path, embeddings)

    # ============================================================
    # STEP 3 — Create FAISS index
    # ============================================================

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    faiss_path = os.path.join(base_dir, "code_index.faiss")
    faiss.write_index(index, faiss_path)

    print("[FAISS] Index built and stored successfully.")

    # ============================================================
    # STEP 4 — Store metadata into PostgreSQL
    # ============================================================

    print("[DB] Storing metadata in PostgreSQL...")

    for i, c in enumerate(chunks):
        entry = CodeChunk(
            user_id=user_id,
            chunk_index=i,
            file_name=c.get("file"),
            symbol_name=c.get("name"),
            start_line=c.get("lineno_start"),
            end_line=c.get("lineno_end"),
            code_snippet=c.get("code")
        )
        session.add(entry)

    session.commit()
    session.close()

    print(f"[FAISS] Metadata stored. Total chunks: {len(chunks)}")

    # ============================================================
    # STEP 5 — Return summary
    # ============================================================

    return {
        "user_id": user_id,
        "faiss_index": faiss_path,
        "embeddings_file": emb_path,
        "total_chunks": len(chunks),
    }
