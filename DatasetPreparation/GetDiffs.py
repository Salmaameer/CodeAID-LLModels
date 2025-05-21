import json
from collections import defaultdict

def load_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f]

def group_by_main_file(data):
    grouped = defaultdict(list)
    for obj in data:
        main_path = obj["content"]["main_file_path"]
        grouped[main_path].append(obj)
    return grouped

def total_dependencies(chunks):
    return sum(len(chunk["content"].get("dependencies", [])) for chunk in chunks)

def compare_and_save(old_path, new_path, output_path):
    old_data = load_jsonl(old_path)
    new_data = load_jsonl(new_path)

    old_grouped = group_by_main_file(old_data)
    new_grouped = group_by_main_file(new_data)

    output = []

    for main_file_path, new_chunks in new_grouped.items():
        old_chunks = old_grouped.get(main_file_path, [])

        new_deps_count = total_dependencies(new_chunks)
        old_deps_count = total_dependencies(old_chunks)

        if new_deps_count != old_deps_count:
            output.extend(new_chunks)  # Write all new chunks for this file

    with open(output_path, "w", encoding="utf-8") as f:
        for obj in output:
            f.write(json.dumps(obj) + "\n")

    print(f"✅ Done. {len(output)} objects written to {output_path}.")

# compare_and_save("old/small.jsonl", "new/small.jsonl", "diffs/small.jsonl")
compare_and_save("old/medium.jsonl", "new/medium.jsonl", "diffs/medium.jsonl")
compare_and_save("old/large.jsonl", "new/large.jsonl", "diffs/large.jsonl")


