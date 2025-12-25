# app/injest.py

import ast
import os
from tree_sitter_languages import get_parser


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
    """
    Parse a Python file into semantic chunks using AST.
    Returns a list of chunk dictionaries.
    """
    try:
        source = open(file_path, "r", encoding="utf-8").read()
    except:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        print(f"[AST] Skipping invalid Python file: {file_path}")
        return []

    chunks = []

    for node in ast.walk(tree):

        # FUNCTIONS
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

        # CLASSES
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
# === PART 2 — TREE-SITTER PARSING FOR OTHER LANGUAGES ===========
# ================================================================

SUPPORTED_LANGUAGES = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".html": "html",
    ".css": "css",
    ".php": "php",
    ".rb": "ruby",
}


def parse_with_treesitter(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    lang_name = SUPPORTED_LANGUAGES.get(ext)

    if not lang_name:
        return []

    try:
        parser = get_parser(lang_name)
    except:
        print(f"[TS] Unsupported language for file: {file_path}")
        return []

    try:
        source_bytes = open(file_path, "rb").read()
    except:
        return []

    try:
        tree = parser.parse(source_bytes)
    except:
        print(f"[TS] Failed to parse file: {file_path}")
        return []

    root = tree.root_node
    text = source_bytes.decode("utf-8", errors="ignore")

    chunks = []

    for child in root.children:
        if child.type in [
            "function_declaration",
            "method_definition",
            "class_declaration",
            "function_definition"
        ]:
            code = text[child.start_byte:child.end_byte]
            snippet = code[:250].replace("\n", " ")

            chunks.append({
                "kind": child.type,
                "name": f"{child.type}_{child.start_point[0]}",
                "file": os.path.basename(file_path),
                "lineno_start": child.start_point[0],
                "lineno_end": child.end_point[0],
                "code": code,
                "text_to_embed": f"{child.type}: {snippet}"
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
    """
    Parse a fully cloned repo directory → return CHUNKS as a list.

    This version:
    - DOES NOT create chunks.json
    - DOES NOT write anything to disk
    - Returns Python objects directly
    """
    chunks = []

    for root, dirs, files in os.walk(cloned_repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            fpath = os.path.join(root, file)

            if ext in SKIP_EXTENSIONS:
                continue

            # =======================
            # ✅ NEW: FILE-LEVEL CHUNK
            # =======================
            try:
                content = open(fpath, "r", encoding="utf-8", errors="ignore").read()
                snippet = content[:400].replace("\n", " ")

                chunks.append({
                    "kind": "file",
                    "name": os.path.basename(fpath),
                    "file": os.path.basename(fpath),
                    "lineno_start": 1,
                    "lineno_end": content.count("\n") + 1,
                    "code": content[:2000],
                    "text_to_embed": f"""
File: {os.path.basename(fpath)}
This file contains the following code.
Snippet: {snippet}
""".strip()
                })
            except:
                pass

            # Existing logic (UNCHANGED)
            if ext == ".py":
                chunks.extend(parse_python_file(fpath))

            elif ext in SUPPORTED_LANGUAGES:
                chunks.extend(parse_with_treesitter(fpath))

    print(f"[INGEST] Total chunks extracted: {len(chunks)}")
    return chunks
