import os
import json
import re
import tiktoken
from pathlib import Path

RAW_PROJECTS_DIR = "miniDataset"
CLEANED_DIR = "New folder2"
METADATA_FILE = "datasetMetadata2.json"
TOKENIZER = tiktoken.get_encoding("cl100k_base")

def classify_project(token_count):
    if token_count <= 8000:
        return "small"
    elif token_count <= 20000:
        return "medium"
    else:
        return "large"

def clean_java_code(code: str) -> str:
    code = re.sub(r'//.*', '', code)  # Remove single-line comments
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)  # Remove block comments
    code = re.sub(r"[=_\-]{5,}", "", code)  # Remove visual separators
    code = re.sub(r'\s+', ' ', code)  # Collapse all whitespace (tabs, newlines, multiple spaces) into one space
    return code.strip()


def count_tokens(text):
    return len(TOKENIZER.encode(text))

def process_projects():
    metadata = []
    os.makedirs(CLEANED_DIR, exist_ok=True)

    for project_name in os.listdir(RAW_PROJECTS_DIR):
        project_path = Path(RAW_PROJECTS_DIR) / project_name
        if not project_path.is_dir():
            continue

        cleaned_project_path = Path(CLEANED_DIR) / project_name
        os.makedirs(cleaned_project_path, exist_ok=True)

        total_tokens = 0
        java_files = []

        for java_file in project_path.rglob("*.java"):
            if not java_file.is_file():
                continue

            rel_path = java_file.relative_to(project_path)
            cleaned_file_path = cleaned_project_path / rel_path

            os.makedirs(cleaned_file_path.parent, exist_ok=True)

            with open(java_file, "r", encoding="utf-8", errors="ignore") as f:
                raw_code = f.read()

            cleaned_code = clean_java_code(raw_code)
            token_count = count_tokens(cleaned_code)
            total_tokens += token_count

            with open(cleaned_file_path, "w", encoding="utf-8") as f:
                f.write(cleaned_code)

            java_files.append(str(rel_path))

        project_size = classify_project(total_tokens)
        metadata.append({
            "project_id": project_name,
            "total_tokens": total_tokens,
            "project_size": project_size,
            "java_files": java_files
        })

    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Processed {len(metadata)} projects. Metadata saved to {METADATA_FILE}.")

if __name__ == "__main__":
    process_projects()
