# app/ingest.py

import ast
import os


# ================================================================
# === PART 1 — PYTHON AST PARSING ================================
# ================================================================

def get_names_from_calls(node):
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.append(child.func.attr)
    return list(set(calls))


def get_variable_names(node):
    return list({n.id for n in ast.walk(node) if isinstance(n, ast.Name)})


def get_constants(node):
    consts = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Constant) and isinstance(c.value, (str, int, float)):
            consts.add(c.value)
    return list(consts)


def parse_python_file(file_path):
    try:
        source = open(file_path, "r", encoding="utf-8").read()
    except:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    chunks = []

    for node in ast.walk(tree):

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            code = ast.get_source_segment(source, node) or ""
            snippet = code[:250].replace("\n", " ")

            parent_class = None
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef) and node in parent.body:
                    parent_class = parent.name

            chunks.append({
                "kind": "method" if parent_class else "function",
                "name": node.name,
                "class": parent_class,
                "file": os.path.basename(file_path),
                "lineno_start": node.lineno,
                "lineno_end": node.end_lineno,
                "code": code,
                "text_to_embed": f"""
Function: {node.name}
Class: {parent_class or "None"}
Args: {', '.join(a.arg for a in node.args.args)}
Calls: {', '.join(get_names_from_calls(node))}
Vars: {', '.join(get_variable_names(node))}
Consts: {', '.join(map(str, get_constants(node)))}
Snippet: {snippet}
""".strip()
            })

        elif isinstance(node, ast.ClassDef):
            code = ast.get_source_segment(source, node) or ""
            snippet = code[:250].replace("\n", " ")

            chunks.append({
                "kind": "class",
                "name": node.name,
                "file": os.path.basename(file_path),
                "lineno_start": node.lineno,
                "lineno_end": node.end_lineno,
                "code": code,
                "text_to_embed": f"Class: {node.name}\nSnippet: {snippet}"
            })

    return chunks


# ================================================================
# === PART 2 — GENERIC CODE FALLBACK (NO TREE-SITTER) ============
# ================================================================

SUPPORTED_CODE_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx",
    ".java", ".c", ".h", ".cpp", ".cc",
    ".go", ".rs", ".php", ".rb", ".css", ".html"
}


def parse_generic_code_file(file_path):
    """
    Simple, robust fallback chunker:
    - splits file into ~40 line blocks
    - works for ALL languages
    """
    try:
        lines = open(file_path, "r", encoding="utf-8", errors="ignore").readlines()
    except:
        return []

    chunks = []
    chunk_size = 40

    for i in range(0, len(lines), chunk_size):
        block = lines[i:i + chunk_size]
        code = "".join(block)
        snippet = code[:250].replace("\n", " ")

        chunks.append({
            "kind": "code_block",
            "name": f"block_{i // chunk_size}",
            "file": os.path.basename(file_path),
            "lineno_start": i + 1,
            "lineno_end": i + len(block),
            "code": code,
            "text_to_embed": f"""
Code block from {os.path.basename(file_path)}
Lines {i + 1} to {i + len(block)}
Snippet: {snippet}
""".strip()
        })

    return chunks


# ================================================================
# === PART 3 — MAIN INGEST FUNCTION ===============================
# ================================================================

SKIP_EXTENSIONS = {
    ".txt", ".md", ".csv", ".png", ".jpg", ".jpeg",
    ".gif", ".pdf", ".ipynb", ".svg"
}

SKIP_FOLDERS = {
    "node_modules", "dist", "build", "__pycache__", ".git", ".idea"
}


def run_ingest(cloned_repo_path):
    chunks = []

    for root, dirs, files in os.walk(cloned_repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            fpath = os.path.join(root, file)

            if ext in SKIP_EXTENSIONS:
                continue

            # ---------- File-level chunk ----------
            try:
                content = open(fpath, "r", encoding="utf-8", errors="ignore").read()
                snippet = content[:400].replace("\n", " ")

                chunks.append({
                    "kind": "file",
                    "name": file,
                    "file": file,
                    "lineno_start": 1,
                    "lineno_end": content.count("\n") + 1,
                    "code": content[:2000],
                    "text_to_embed": f"""
File: {file}
Snippet: {snippet}
""".strip()
                })
            except:
                pass

            # ---------- Language-specific ----------
            if ext == ".py":
                chunks.extend(parse_python_file(fpath))

            elif ext in SUPPORTED_CODE_EXTENSIONS:
                chunks.extend(parse_generic_code_file(fpath))

    print(f"[INGEST] Total chunks extracted: {len(chunks)}")
    return chunks
