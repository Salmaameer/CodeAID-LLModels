#! /usr/bin/env python3
import os, sys, json
import jpype, jpype.imports
from jpype.types import JString
# 1️⃣ Start JVM with JavaParser
JAR = "libs/javaparser-core-3.25.4.jar"

if not jpype.isJVMStarted():
    jpype.startJVM(classpath=[JAR])

# 2️⃣ Import JavaParser
from com.github.javaparser import StaticJavaParser

def is_valid_java_code(code):
    try:
        cu = StaticJavaParser.parse(code)
        return True
    except Exception as e:
        # print(f"Error parsing code: {e}")
        return False


def is_valid_code(inputObj):
    files = inputObj.get("refactored_files", [])
    for f in files:
        content = f.get("fileContent")
        if not is_valid_java_code(content):
            return False
    return True