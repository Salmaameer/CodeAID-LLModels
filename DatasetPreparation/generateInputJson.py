import json
import tiktoken
import re
from pathlib import Path
import javalang
import os
import jpype
from jpype.types import JString
from jpype.imports import registerDomain

# ========== CONFIG ==========
CLEANED_DIR = "../Dataset"
METADATA_FILE = "JSON Files/datasetMetadata.json"
DEPENDENCY_CACHE_FILE = "dependencies.json"
JAR = "libs/javaparser-core-3.26.4.jar"
TOKENIZER = tiktoken.get_encoding("cl100k_base")
# ============================

# Start JVM once
if not jpype.isJVMStarted():
    jpype.startJVM(classpath=[JAR])


# Java imports
from com.github.javaparser import StaticJavaParser
from com.github.javaparser.ast.body import ClassOrInterfaceDeclaration, AnnotationDeclaration
from com.github.javaparser.ast.expr import (
    ObjectCreationExpr, InstanceOfExpr, CastExpr, ClassExpr,
    MethodReferenceExpr, VariableDeclarationExpr,MethodCallExpr, NameExpr
)
from com.github.javaparser.ast.type import ReferenceType
from com.github.javaparser import ParserConfiguration

# Create parser configuration and set language level
config = ParserConfiguration()
config.setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17)

# Pass config to JavaParser
StaticJavaParser.setConfiguration(config)


def count_tokens(text):
    return len(TOKENIZER.encode(text))


def read_file(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def clean_java_code(code: str):
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r"[=_\-]{5,}", "", code)
    code = re.sub(r'\n\s*\n', ' ', code)
    code = re.sub(r'\n\s*', ' ', code)
    code = re.sub(r'\s+', ' ', code)
    code = re.sub(r'\t', ' ', code)
    code = re.sub(r'(\"{3}|\'{3})(.*?)\1', '', code, flags=re.DOTALL)
    return code.strip()


def escape_newlines(text):
    return text.replace('\n', '\\n').replace('\r', '\\r')


def generate_chunks(project_id, main_file_path, main_file_content, dependencies):
    main_file_tokens = count_tokens(main_file_content)
    prompt_chunks = []
    current_chunk_tokens = main_file_tokens

    chunk = {
        "project_id": project_id,
        "chunk_id": 0,
        "content": {
            "main_file_path": main_file_path,
            "main_file_content": escape_newlines(clean_java_code(main_file_content)),
            "dependencies": []
        }
    }

    for dep in dependencies:
        dep["file_content"] = escape_newlines(clean_java_code(dep.get("file_content")))
        dep_tokens = count_tokens(dep["file_content"])
        if current_chunk_tokens + dep_tokens > 5000:
            prompt_chunks.append(chunk)
            chunk_id = len(prompt_chunks)
            current_chunk_tokens = main_file_tokens
            chunk = {
                "project_id": project_id,
                "chunk_id": chunk_id,
                "content": {
                    "main_file_path": main_file_path,
                    "main_file_content": escape_newlines(main_file_content),
                    "dependencies": [dep]
                }
            }
            current_chunk_tokens += dep_tokens
        else:
            chunk["content"]["dependencies"].append(dep)
            current_chunk_tokens += dep_tokens

    prompt_chunks.append(chunk)
    return prompt_chunks


def find_java_files(root):
    return [str(p) for p in Path(root).rglob("*.java")]


def build_fqn_map(root):
    fqn_map = {}
    for p in find_java_files(root):
        try:
            cu = StaticJavaParser.parse(JString(read_file(p)))
            pkg = cu.getPackageDeclaration().map(lambda d: d.getNameAsString()).orElse("")
            for t in cu.getTypes():
                name = str(t.getNameAsString())
                key = f"{pkg}.{name}" if pkg else name
                fqn_map[key] = p
        except Exception as e:
            print(f"[FQN MAP] Failed to parse file: {p}\nError: {e}\n")
    return fqn_map


def extract_type_names(cu):
    fq_imports, wildcard_pkgs, simple_names = set(), set(), set()

    for imp in cu.getImports():
        name = str(imp.getNameAsString())
        if imp.isAsterisk():
            wildcard_pkgs.add(name)
        else:
            fq_imports.add(name)

    for cid in cu.findAll(ClassOrInterfaceDeclaration):
        for t in cid.getExtendedTypes():
            simple_names.add(t.getNameAsString())
        for t in cid.getImplementedTypes():
            simple_names.add(t.getNameAsString())
    for ann in cu.findAll(AnnotationDeclaration):
        simple_names.add(ann.getNameAsString())
    for vd in cu.findAll(VariableDeclarationExpr):
        simple_names.add(vd.getElementType().asString())
    for oc in cu.findAll(ObjectCreationExpr):
        simple_names.add(oc.getType().getNameAsString())
    for io in cu.findAll(InstanceOfExpr):
        simple_names.add(io.getType().asString())
    for c in cu.findAll(CastExpr):
        simple_names.add(c.getType().asString())
    for cl in cu.findAll(ClassExpr):
        simple_names.add(cl.getType().asString())
    for mr in cu.findAll(MethodReferenceExpr):
        if mr.getScope().isTypeExpr():
            simple_names.add(mr.getScope().asTypeExpr().getType().asString())
    for mc in cu.findAll(MethodCallExpr):
        if mc.getScope().isPresent() and isinstance(mc.getScope().get(), NameExpr):
            simple_names.add(mc.getScope().get().getNameAsString())
    for rt in cu.findAll(ReferenceType):
        simple_names.add(rt.getElementType().asString())

    return fq_imports, wildcard_pkgs, simple_names


def build_dependencies(project_root):
    fqn_map = build_fqn_map(project_root)
    deps = {}
    def add_dep(deps_set, candidate_path, src_path):
        if candidate_path != src_path:
            deps_set.add(candidate_path)
    for src in find_java_files(project_root):
        cu = StaticJavaParser.parse(JString(read_file(src)))
        fq_imports, wildcard_pkgs, simple_names = extract_type_names(cu)
        file_deps, covered_simple = set(), set()
        current_pkg = cu.getPackageDeclaration().map(lambda p: p.getNameAsString()).orElse("")

        for fqn in fq_imports:
            simple = fqn.split('.')[-1]
            if simple in simple_names and fqn in fqn_map:
                add_dep(file_deps, fqn_map[fqn], src)
                covered_simple.add(simple)

        # 2. Wildcard imports
        wildcard_resolutions = set()
        for pkg in wildcard_pkgs:
            for name in simple_names:
                if name in covered_simple:
                    continue
                candidate = f"{pkg}.{name}"
                if candidate in fqn_map:
                    wildcard_resolutions.add((name, fqn_map[candidate]))

        for name, path in wildcard_resolutions:
            add_dep(file_deps, path, src)
            covered_simple.add(name)

        # 3. Same-package classes
        for name in simple_names:
            if name in covered_simple:
                continue
            same_pkg_candidate = f"{current_pkg}.{name}" if current_pkg else name
            if same_pkg_candidate in fqn_map:
                add_dep(file_deps, fqn_map[same_pkg_candidate], src)
                covered_simple.add(name)

        # 4. Fallback suffix match
        for name in simple_names:
            if name in covered_simple:
                continue
            for fq, path in fqn_map.items():
                if fq.endswith(f".{name}") and path != src:
                    add_dep(file_deps, path, src)
                    break

        deps[src] = sorted(file_deps)

    return deps


def process_projects(metadata):
    # Load or build dependency cache
    if os.path.exists(DEPENDENCY_CACHE_FILE):
        with open(DEPENDENCY_CACHE_FILE, "r", encoding="utf-8") as f:
            all_dependencies = json.load(f)
    else:
        all_dependencies = {}
        for project_info in metadata:
            project_name = project_info["project_id"]
            project_path = str(Path(CLEANED_DIR) / project_name)
            deps = build_dependencies(project_path)
            all_dependencies[project_name] = deps
        with open(DEPENDENCY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(all_dependencies, f, indent=2)

    # Output files
    small_file = open("small.jsonl", "a", encoding="utf-8")
    medium_file = open("medium.jsonl", "a", encoding="utf-8")
    large_file = open("large.jsonl", "a", encoding="utf-8")

    project_id = 0
    for project_info in metadata:
        project_name = project_info["project_id"]
        size_class = project_info["project_size"]
        project_path = str(Path(CLEANED_DIR) / project_name)

        file_contents = {}
        for java_file in Path(project_path).rglob("*.java"):
            file_contents[str(java_file)] = read_file(java_file)

        dependency_map = all_dependencies.get(project_name, {})

        for main_path in dependency_map:
            main_file_content = clean_java_code(file_contents.get(main_path, ""))
            dep_paths = dependency_map[main_path]
            dependencies = [
                {
                    "file_path": str(Path(dep).relative_to(CLEANED_DIR)),
                    "file_content": clean_java_code(file_contents.get(dep, ""))
                }
                for dep in dep_paths if dep in file_contents
            ]
            rel_main_path = str(Path(main_path).relative_to(CLEANED_DIR))
            chunks = generate_chunks(project_id, rel_main_path, main_file_content, dependencies)

            target_file = {"small": small_file, "medium": medium_file, "large": large_file}[size_class]
            for chunk in chunks:
                target_file.write(json.dumps(chunk, ensure_ascii=False, separators=(',', ':')) + "\n")

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
