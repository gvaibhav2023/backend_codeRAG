# app/models.py
from sqlalchemy import Column, Integer, String, Text
from pgvector.sqlalchemy import Vector
from app.db import Base

class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)       # identify which user's repo
    chunk_index = Column(Integer, index=True)  # FAISS index position
    file_name = Column(String)
    symbol_name = Column(String)
    start_line = Column(Integer)
    end_line = Column(Integer)
    code_snippet = Column(Text)
