#! /usr/bin/env python3

import json

def is_valid_item(file_obj):
    return (
        isinstance(file_obj, dict)
        and "filePath" in file_obj
        and "fileContent" in file_obj
        and isinstance(file_obj["filePath"], str)
        and isinstance(file_obj["fileContent"], str)
    )

def is_valid_obj(input_obj):
    files = input_obj.get("refactored_files")
    if isinstance(files, list) and all(is_valid_item(f) for f in files):
        return True
    else:
        return False
