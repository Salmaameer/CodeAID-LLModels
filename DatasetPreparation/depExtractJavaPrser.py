#!/usr/bin/env python3
import os, sys, json
import jpype, jpype.imports
from jpype.types import JString

# 1️⃣ Start the JVM with JavaParser on the classpath
JAR = "DatasetPreparation/lib/javaparser-core-3.25.4.jar"
if not jpype.isJVMStarted():
    jpype.startJVM(classpath=[JAR])

# 2️⃣ Import the JavaParser types we need
from com.github.javaparser import StaticJavaParser
from com.github.javaparser.ast.body import ClassOrInterfaceDeclaration, AnnotationDeclaration
from com.github.javaparser.ast.expr import (
    ObjectCreationExpr, InstanceOfExpr, CastExpr, ClassExpr,
    MethodReferenceExpr, VariableDeclarationExpr
)
from com.github.javaparser.ast.type import ReferenceType

# 3️⃣ Utility: find all .java files

def find_java_files(root):
    """
    Recursively discover all module roots (folders with pom.xml or build.gradle),
    then collect .java files under each module's src/main/java and src/test/java.
    If no modules are found, do a full recursive scan under `root`.
    Yields each path exactly once, sorted.
    """
    # 1) find all module roots
    module_roots = []
    for dirpath, dirnames, filenames in os.walk(root):
        if 'pom.xml' in filenames or 'build.gradle' in filenames:
            module_roots.append(dirpath)

    java_paths = set()

    if module_roots:
        for module in module_roots:
            # scan standard java source dirs
            scanned = False
            for sub in ('src/main/java', 'src/test/java'):
                base = os.path.join(module, sub)
                if os.path.isdir(base):
                    scanned = True
                    for dp, _, files in os.walk(base):
                        for f in files:
                            if f.endswith('.java'):
                                java_paths.add(os.path.join(dp, f))

            # if this module had no src dirs, fall back to full scan
            if not scanned:
                for dp, _, files in os.walk(module):
                    for f in files:
                        if f.endswith('.java'):
                            java_paths.add(os.path.join(dp, f))

    else:
        # no modules: scan everything
        for dp, _, files in os.walk(root):
            for f in files:
                if f.endswith('.java'):
                    java_paths.add(os.path.join(dp, f))

    for path in sorted(java_paths):
        yield path

# 4️⃣ Build FQN → file map
def build_fqn_map(root):
    fqn_map = {}
    for p in find_java_files(root):
        cu = StaticJavaParser.parse(JString(open(p, 'r').read()))
        pkg = cu.getPackageDeclaration().map(lambda d: d.getNameAsString()).orElse("")
        for t in cu.getTypes():
            raw = t.getNameAsString()
            name = str(raw)
            key = f"{pkg}.{name}" if pkg else name
            fqn_map[key] = p
    return fqn_map

# 5️⃣ Extract imports and usage sets
def extract_type_names(cu):
    # fq imports, wildcard packages, simple type names
    fq_imports = set()
    wildcard_pkgs = set()
    simple_names = set()

    # imports
    for imp in cu.getImports():
        raw = imp.getNameAsString()
        name = str(raw)
        if imp.isAsterisk():
            wildcard_pkgs.add(name)
        else:
            fq_imports.add(name)

    # inheritance & implements
    for cid in cu.findAll(ClassOrInterfaceDeclaration):
        for t in cid.getExtendedTypes():
            simple_names.add(t.getNameAsString())
        for t in cid.getImplementedTypes():
            simple_names.add(t.getNameAsString())

    # annotations
    for ann in cu.findAll(AnnotationDeclaration):
        simple_names.add(ann.getNameAsString())

    # fields and local vars
    for vd in cu.findAll(VariableDeclarationExpr):
        simple_names.add(vd.getElementType().asString())

    # object creation
    for oc in cu.findAll(ObjectCreationExpr):
        simple_names.add(oc.getType().getNameAsString())

    # instanceof
    for io in cu.findAll(InstanceOfExpr):
        simple_names.add(io.getType().asString())

    # casts
    for c in cu.findAll(CastExpr):
        simple_names.add(c.getType().asString())

    # class literals
    for cl in cu.findAll(ClassExpr):
        simple_names.add(cl.getType().asString())

    # method references
    for mr in cu.findAll(MethodReferenceExpr):
        scope = mr.getScope()
        if scope.isTypeExpr():
            simple_names.add(scope.asTypeExpr().getType().asString())

    # generics / reference types
    for rt in cu.findAll(ReferenceType):
        simple_names.add(rt.getElementType().asString())

    # normalize to Python str
    fq_imports = {str(x) for x in fq_imports}
    wildcard_pkgs = {str(x) for x in wildcard_pkgs}
    simple_names = {str(x) for x in simple_names}

    return fq_imports, wildcard_pkgs, simple_names

# 6️⃣ Build dependency graph
def build_dependencies(root):
    fqn_map = build_fqn_map(root)
    deps = {}
    for src in find_java_files(root):
        cu = StaticJavaParser.parse(JString(open(src, 'r').read()))
        fq_imports, wildcard_pkgs, simple_names = extract_type_names(cu)
        file_deps = set()

        # direct FQ imports
        for fqn in fq_imports:
            if fqn in fqn_map:
                file_deps.add(fqn_map[fqn])

        # simple names resolution
        for name in simple_names:
            # exact FQN (same-package inner classes)
            if name in fqn_map:
                file_deps.add(fqn_map[name])
            # suffix match
            for fq, path in fqn_map.items():
                if fq.endswith("." + name):
                    file_deps.add(path)
            # wildcard pkg
            for pkg in wildcard_pkgs:
                candidate = f"{pkg}.{name}"
                if candidate in fqn_map:
                    file_deps.add(fqn_map[candidate])

        deps[src] = sorted(file_deps)
    return deps

# 7️⃣ Main
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: extractor.py /path/to/java/project", file=sys.stderr)
        sys.exit(1)
    root = sys.argv[1]
    if not os.path.isdir(root):
        print(f"Not a directory: {root}", file=sys.stderr)
        sys.exit(1)
    graph = build_dependencies(root)
    print(json.dumps(graph, indent=2))
