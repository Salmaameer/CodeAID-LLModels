#!/usr/bin/env python3
import os, sys, json
import jpype, jpype.imports
from jpype.types import JString

# 1️⃣ Start the JVM with JavaParser on the classpath
JAR = "libs/javaparser-core-3.25.4.jar"
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
    module_roots = []
    for dirpath, dirnames, filenames in os.walk(root):
        if 'pom.xml' in filenames or 'build.gradle' in filenames:
            module_roots.append(dirpath)

    java_paths = set()

    if module_roots:
        for module in module_roots:
            scanned = False
            for sub in ('src/main/java', 'src/test/java'):
                base = os.path.join(module, sub)
                if os.path.isdir(base):
                    scanned = True
                    for dp, _, files in os.walk(base):
                        for f in files:
                            if f.endswith('.java'):
                                java_paths.add(os.path.join(dp, f))
            if not scanned:
                for dp, _, files in os.walk(module):
                    for f in files:
                        if f.endswith('.java'):
                            java_paths.add(os.path.join(dp, f))
    else:
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
    fq_imports = set()
    wildcard_pkgs = set()
    simple_names = set()

    for imp in cu.getImports():
        raw = imp.getNameAsString()
        name = str(raw)
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
        scope = mr.getScope()
        if scope.isTypeExpr():
            simple_names.add(scope.asTypeExpr().getType().asString())

    for rt in cu.findAll(ReferenceType):
        simple_names.add(rt.getElementType().asString())

    fq_imports = {str(x) for x in fq_imports}
    wildcard_pkgs = {str(x) for x in wildcard_pkgs}
    simple_names = {str(x) for x in simple_names}

    return fq_imports, wildcard_pkgs, simple_names

# 6️⃣ Build dependency graph
def build_dependencies(root):
    fqn_map = build_fqn_map(root)
    deps = {}

    def add_dep(deps_set, candidate_path, src_path):
        if candidate_path != src_path:
            deps_set.add(candidate_path)

    for src in find_java_files(root):
        cu = StaticJavaParser.parse(JString(open(src, 'r').read()))
        fq_imports, wildcard_pkgs, simple_names = extract_type_names(cu)
        file_deps = set()
        covered_simple = set()
        current_pkg = cu.getPackageDeclaration().map(lambda p: p.getNameAsString()).orElse("")

        # 1. Process FQ imports
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

# 7️⃣ Main
if __name__ == "__main__":
    # root = "../Dataset/Admission-counselling-system"
    root = "test\Instapay"
    graph = build_dependencies(root)
    print(json.dumps(graph, indent=2))
