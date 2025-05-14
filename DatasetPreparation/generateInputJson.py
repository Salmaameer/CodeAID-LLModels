import json
import tiktoken
import re
from pathlib import Path
import javalang
CLEANED_DIR = "New folder2"
METADATA_FILE = "datasetMetadata2.json"
TOKENIZER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text):
    return len(TOKENIZER.encode(text))


def read_file(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def clean_java_code(code):
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'System\.out\.print\s*\(.*?\)\s*;', 'sout("")', code)
    code = re.sub(r'System\.out\.println\s*\(.*?\)\s*;', 'soutl("")', code)
    code = re.sub(r"[=_\-]{5,}", "", code)
    code = re.sub(r'\n\s*\n', '\n', code)
    code = re.sub(r'\t', '    ', code)
    return code.strip()


def escape_newlines(text):
    # Escape actual newlines and carriage returns to avoid wrapping
    return text.replace('\n', '\\n').replace('\r', '\\r')

def extract_import_dependencies(java_file_content, all_files):
    dependencies = []
    import_matches = re.findall(r'import\s+((?!java)[\w\.]+);', java_file_content)
    for imp in import_matches:
        imp_path = imp.replace('.', '/') + '.java'
        for file_name, file_data in all_files.items():
            normalized_file_name = file_name.replace("\\", "/")
            if normalized_file_name.endswith(imp_path):
                dependencies.append({
                    "file_path": file_name,
                    "file_content": file_data["content"]
                })
                break

    return dependencies


def extract_direct_new_class_references(java_file_content, all_files):
    dependencies = []
    lines = java_file_content.splitlines()

    for line in lines:
        if '= new ' in line:
            # Try to extract the FQCN after '= new '
            match = re.search(r'=\s*new\s+([\w\.]+)', line)
            if match:
                fqcn = match.group(1)
                class_path = fqcn.replace('.', '/') + '.java'

                for file_name, file_data in all_files.items():
                    normalized_file = file_name.replace("\\", "/")
                    if normalized_file.endswith(class_path):
                        dependencies.append({
                            "file_path": file_name,
                            "file_content": file_data["content"]
                        })
                        break  # Stop once matched

    return dependencies



def generate_chunks(project_id, main_file_path, main_file_content, dependencies):
    main_file_tokens = count_tokens(main_file_content)

    prompt_chunks = []
    current_chunk_tokens = main_file_tokens

    chunk = {
        "project_id": project_id,
        "chunk_id": 0,
        "content": {
            "main_file_path": main_file_path,
            "main_file_content": escape_newlines(main_file_content),  # Escape newlines
            "dependencies": []
        }
    }

    for dep in dependencies:
        dep["file_content"] = escape_newlines(dep["file_content"])  # Escape newlines in dependencies
        dep_tokens = count_tokens(dep["file_content"])
        if current_chunk_tokens + dep_tokens > 5000:
            prompt_chunks.append(chunk)
            current_chunk_tokens = main_file_tokens
            chunk_id = len(prompt_chunks)

            chunk = {
                "project_id": project_id,
                "chunk_id": chunk_id,
                "content": {
                    "main_file_path": main_file_path,
                    "main_file_content": escape_newlines(main_file_content),  # Escape newlines
                    "dependencies": [dep]
                }
            }
            current_chunk_tokens += dep_tokens
        else:
            chunk["content"]["dependencies"].append(dep)
            current_chunk_tokens += dep_tokens

    prompt_chunks.append(chunk)
    return prompt_chunks


def process_projects(metadata):
    small_file = open("small.jsonl", "a", encoding="utf-8")
    medium_file = open("medium.jsonl", "a", encoding="utf-8")
    large_file = open("large.jsonl", "a", encoding="utf-8")

    project_id = 0

    for project_info in metadata:
        project_name = project_info["project_id"]
        size_class = project_info["project_size"]

        project_path = Path(CLEANED_DIR) / project_name
        if not project_path.is_dir():
            continue

        all_files = {}
        for java_file in project_path.rglob("*.java"):
            if java_file.is_file():
                file_name = str(java_file.relative_to(CLEANED_DIR))
                all_files[file_name] = {"content": read_file(java_file)}

        for main_file in all_files:
            main_file_path = main_file
            main_file_content = clean_java_code(all_files[main_file]["content"])

            import_dependencies = extract_import_dependencies(main_file_content, all_files)
            new_dependencies = extract_direct_new_class_references(main_file_content, all_files)
            combined = import_dependencies + new_dependencies
            unique_dependencies = {}
            for dep in combined:
                file_path = dep["file_path"]
                if file_path not in unique_dependencies:
                    unique_dependencies[file_path] = dep
            dependencies = list(unique_dependencies.values())
            chunks = generate_chunks(project_id, main_file_path, main_file_content, dependencies)

            if size_class == "small":
                for chunk in chunks:
                    small_file.write(json.dumps(chunk, ensure_ascii=False, separators=(',', ':')) + "\n")
            elif size_class == "medium":
                for chunk in chunks:
                    medium_file.write(json.dumps(chunk, ensure_ascii=False, separators=(',', ':')) + "\n")
            else:
                for chunk in chunks:
                    large_file.write(json.dumps(chunk, ensure_ascii=False, separators=(',', ':')) + "\n")

        project_id += 1

    small_file.close()
    medium_file.close()
    large_file.close()

    print("Generated prompts stored in small.jsonl, medium.jsonl, and large.jsonl.")


def load_metadata():
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    metadata = load_metadata()
    process_projects(metadata)
