import os
import javalang
from collections import defaultdict

def list_java_files(root_dir):
    java_files = []
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".java"):
                java_files.append(os.path.join(subdir, file))
    print(java_files)
    return java_files

def get_class_names_from_ast(tree):
    return [path.name for path in tree.types if hasattr(path, 'name')]

def extract_dependencies(file_content, project_class_names):
    dependencies = set()
    try:
        tree = javalang.parse.parse(file_content)


        # Look for all type usages (e.g., variables, fields, parameters, return types)
        for _, node in tree.filter(javalang.tree.ReferenceType):
            if hasattr(node, 'name') and node.name in project_class_names:
                dependencies.add(node.name)

        # Also include object instantiations: new SomeClass()
        for _, node in tree.filter(javalang.tree.ClassCreator):
            if hasattr(node, 'type') and node.type.name in project_class_names:
                dependencies.add(node.type.name)

    except javalang.parser.JavaSyntaxError as e:
        print(f"Syntax error in file: {e}")
    except Exception as e:
        print(f"Error parsing file: {e}")

    return dependencies


def extract_all_dependencies(project_path):
    java_files = list_java_files(project_path)
    file_to_classes = {}
    class_to_file = {}

    # First pass: collect all class names and their files
    for file in java_files:
        with open(file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            try:
                tree = javalang.parse.parse(content)
                class_names = get_class_names_from_ast(tree)
                file_to_classes[file] = class_names
                for cls in class_names:
                    class_to_file[cls] = file
            except:
                continue

    project_class_names = set(class_to_file.keys())

    # Second pass: extract dependencies for each file
    class_dependencies = defaultdict(set)
    for file, classes in file_to_classes.items():
        with open(file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            deps = extract_dependencies(content, project_class_names)
            for cls in classes:
                class_dependencies[cls].update(deps)

    return dict(class_dependencies)
# Usage
if __name__ == "__main__":
    project_path = "test\Instapay"
    deps = extract_all_dependencies(project_path)

    for cls, dep in deps.items():
        print(f"{cls} depends on: {list(dep)}")
