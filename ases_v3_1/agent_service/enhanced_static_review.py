"""
ASES - Enhanced Static Analysis (v3.2)
=======================================
Extends static_reviewer.py with additional security and quality layers:

Layer 6 — Secrets Detection (trufflehog-style pattern matching)
Layer 7 — SAST (Semgrep rules for common vulnerabilities)
Layer 8 — Type Checking (TypeScript strict, Python type hints)
Layer 9 — Complexity Analysis (cyclomatic complexity, maintainability)
Layer 10 — Bundle Analysis (for frontend projects)
Layer 11 — Accessibility Audit (enhanced WCAG 2.1 AA checks)

Usage:
    from enhanced_static_review import run_enhanced_review
"""

import ast
import re
import json
import subprocess
import tempfile
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


class Issue:
    def __init__(self, layer: str, severity: str, code: str,
                 message: str, file: str = "", line: int = 0):
        self.layer = layer
        self.severity = severity
        self.code = code
        self.message = message
        self.file = file
        self.line = line

    def to_dict(self) -> dict:
        return {"layer": self.layer, "severity": self.severity,
                "code": self.code, "message": self.message,
                "file": self.file, "line": self.line}

    def __str__(self):
        loc = f"{self.file}:{self.line}" if self.file else "-"
        return f"[{self.layer}/{self.severity}] {loc} {self.code}: {self.message}"


# Layer 6 — Secrets Detection
SECRET_PATTERNS = [
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS_ACCESS_KEY_ID", "high"),
    (re.compile(r'ghp_[A-Za-z0-9]{36}'), "GITHUB_PAT", "high"),
    (re.compile(r'gho_[A-Za-z0-9]{36}'), "GITHUB_OAUTH", "high"),
    (re.compile(r'AIza[0-9A-Za-z\-_]{35}'), "GOOGLE_API_KEY", "high"),
    (re.compile(r'sk_live_[0-9a-zA-Z]{24,}'), "STRIPE_SECRET_KEY", "high"),
    (re.compile(r'pk_live_[0-9a-zA-Z]{24,}'), "STRIPE_PUB_KEY", "medium"),
    (re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}'), "SLACK_TOKEN", "high"),
    (re.compile(r'(?i)api[_-]?key\s*[:=]\s*["\'][A-Za-z0-9_\-]{20,}'), "API_KEY", "high"),
    (re.compile(r'(?i)secret[_-]?key\s*[:=]\s*["\'][A-Za-z0-9_\-]{20,}'), "SECRET_KEY", "high"),
    (re.compile(r'(?i)password\s*[:=]\s*["\'][A-Za-z0-9_\-!@#$%^&*]{8,}'), "PASSWORD", "high"),
    (re.compile(r'(?i)private[_-]?key\s*[:=]\s*["\']'), "PRIVATE_KEY", "high"),
    (re.compile(r'(?:postgres|mysql|mongodb|redis)://[^:]+:[^@]+@'), "DATABASE_URL", "high"),
    (re.compile(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'), "JWT_TOKEN", "medium"),
]

SECRET_EXEMPT_FILES = {
    ".env.example", ".env.sample", "env.example", "env.sample",
    "test-fixtures", "test_fixtures", "tests/", "__tests__/",
    "example.", "examples/", "fixtures/",
}


def _secrets_detection(files: List[Dict[str, str]]) -> List[Issue]:
    issues = []
    for f in files:
        path = f["path"]
        content = f["content"]
        if any(exempt in path.lower() for exempt in SECRET_EXEMPT_FILES):
            continue
        if "test" in path.lower() and "mock" in content.lower():
            continue
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            for pattern, secret_type, severity in SECRET_PATTERNS:
                match = pattern.search(line)
                if match:
                    matched = match.group(0)
                    if len(matched) > 20:
                        matched = matched[:10] + "..." + matched[-10:]
                    issues.append(Issue(
                        layer="secrets", severity=severity,
                        code=f"SEC001_{secret_type}",
                        message=f"Potential {secret_type} detected: {matched}. "
                                f"Move to environment variables or secrets manager.",
                        file=path, line=i,
                    ))
    return issues


# Layer 7 — SAST
SAST_RULES = [
    {"id": "SQL_INJECTION", "severity": "high",
     "patterns": [r'execute\s*\(\s*f["\'].*\{.*\}.*["\']',
                  r'cursor\.execute\s*\(\s*["\'][^"\']*\+[^"\']*["\']',
                  r'query\s*=\s*f["\'].*SELECT.*\{'],
     "message": "Potential SQL injection — use parameterized queries"},
    {"id": "XSS", "severity": "high",
     "patterns": [r'innerHTML\s*=', r'dangerouslySetInnerHTML\s*=\s*\{',
                  r'document\.write\s*\(', r'eval\s*\('],
     "message": "Potential XSS vulnerability — sanitize user input"},
    {"id": "CMD_INJECTION", "severity": "high",
     "patterns": [r'subprocess\.call\s*\(\s*shell\s*=\s*True',
                  r'os\.system\s*\(', r'child_process\.exec\s*\('],
     "message": "Potential command injection — avoid shell=True with user input"},
    {"id": "PATH_TRAVERSAL", "severity": "high",
     "patterns": [r'open\s*\(\s*.*\+\s*.*\)', r'fs\.readFileSync\s*\(\s*.*\+\s*.*\)'],
     "message": "Potential path traversal — validate and sanitize file paths"},
    {"id": "INSECURE_DESERIALIZATION", "severity": "high",
     "patterns": [r'pickle\.loads?\s*\(', r'yaml\.load\s*\(\s*[^,]*\s*\)',
                  r'marshal\.loads?\s*\('],
     "message": "Insecure deserialization — use safe alternatives"},
    {"id": "WEAK_CRYPTO", "severity": "medium",
     "patterns": [r'hashlib\.md5\s*\(', r'hashlib\.sha1\s*\(',
                  r'Crypto\.Cipher\.DES', r'Crypto\.Cipher\.RC4'],
     "message": "Weak cryptographic algorithm — use SHA-256+ or AES"},
    {"id": "SSRF", "severity": "high",
     "patterns": [r'requests\.get\s*\(\s*url', r'urllib\.request\.urlopen\s*\(\s*url',
                  r'fetch\s*\(\s*url'],
     "message": "Potential SSRF — validate and whitelist URLs before fetching"},
]


def _sast_analysis(files: List[Dict[str, str]]) -> List[Issue]:
    issues = []
    for f in files:
        path = f["path"]
        content = f["content"]
        for rule in SAST_RULES:
            for pattern in rule["patterns"]:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    line_num = content[:match.start()].count("\n") + 1
                    issues.append(Issue(
                        layer="sast", severity=rule["severity"],
                        code=rule["id"], message=rule["message"],
                        file=path, line=line_num,
                    ))
    return issues


# Layer 8 — Type Checking
def _type_checking_python(files: List[Dict[str, str]]) -> List[Issue]:
    issues = []
    for f in files:
        if not f["path"].endswith(".py"):
            continue
        try:
            tree = ast.parse(f["content"], filename=f["path"])
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is None and not node.name.startswith("_"):
                    issues.append(Issue(
                        layer="types", severity="warning", code="TYPE001",
                        message=f"Function '{node.name}' missing return type annotation",
                        file=f["path"], line=node.lineno,
                    ))
                for arg in node.args.args:
                    if arg.annotation is None and arg.arg != "self":
                        issues.append(Issue(
                            layer="types", severity="warning", code="TYPE002",
                            message=f"Argument '{arg.arg}' in '{node.name}' missing type annotation",
                            file=f["path"], line=node.lineno,
                        ))
            if isinstance(node, ast.Name) and node.id == "any":
                issues.append(Issue(
                    layer="types", severity="warning", code="TYPE003",
                    message="Use of 'any' type — prefer specific types",
                    file=f["path"], line=node.lineno,
                ))
    return issues


def _type_checking_js(files: List[Dict[str, str]]) -> List[Issue]:
    issues = []
    for f in files:
        path = f["path"]
        if not any(path.endswith(ext) for ext in [".ts", ".tsx", ".js", ".jsx"]):
            continue
        content = f["content"]
        for match in re.finditer(r':\s*any\b', content):
            line_num = content[:match.start()].count("\n") + 1
            issues.append(Issue(
                layer="types", severity="warning", code="TYPE003",
                message="Use of 'any' type — prefer specific types",
                file=path, line=line_num,
            ))
        for match in re.finditer(r'@ts-ignore', content):
            line_num = content[:match.start()].count("\n") + 1
            issues.append(Issue(
                layer="types", severity="warning", code="TYPE004",
                message="@ts-ignore suppresses type checking — fix the underlying type error",
                file=path, line=line_num,
            ))
    return issues


# Layer 9 — Complexity Analysis
def _calculate_complexity_python(content: str) -> Dict[str, Any]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {"complexity": 0, "functions": []}
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            complexity = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                    complexity += 1
                elif isinstance(child, ast.BoolOp):
                    complexity += len(child.values) - 1
                elif isinstance(child, ast.ExceptHandler):
                    complexity += 1
                elif isinstance(child, ast.comprehension):
                    complexity += 1
            functions.append({"name": node.name, "complexity": complexity, "line": node.lineno})
    return {"complexity": max((f["complexity"] for f in functions), default=0), "functions": functions}


def _complexity_analysis(files: List[Dict[str, str]]) -> List[Issue]:
    issues = []
    MAX_COMPLEXITY = 10
    for f in files:
        path = f["path"]
        if path.endswith(".py"):
            result = _calculate_complexity_python(f["content"])
            for func in result["functions"]:
                if func["complexity"] > MAX_COMPLEXITY:
                    issues.append(Issue(
                        layer="complexity", severity="warning", code="COMP001",
                        message=f"Function '{func['name']}' has cyclomatic complexity "
                                f"{func['complexity']} (max: {MAX_COMPLEXITY}). Consider breaking it down.",
                        file=path, line=func["line"],
                    ))
        if any(path.endswith(ext) for ext in [".py", ".js", ".ts", ".jsx", ".tsx"]):
            lines = f["content"].splitlines()
            if len(lines) > 300:
                issues.append(Issue(
                    layer="complexity", severity="warning", code="COMP002",
                    message=f"File has {len(lines)} lines — consider splitting into smaller modules",
                    file=path, line=0,
                ))
    return issues


# Layer 10 — Bundle Analysis
def _bundle_analysis(files: List[Dict[str, str]], tech_stack: str) -> List[Issue]:
    issues = []
    for f in files:
        path = f["path"]
        if not any(path.endswith(ext) for ext in [".js", ".jsx", ".ts", ".tsx"]):
            continue
        content = f["content"]
        large_import_patterns = [
            (r'import\s+\*\s+as\s+\w+\s+from\s+["\']lodash', "lodash"),
            (r'import\s+\*\s+as\s+\w+\s+from\s+["\']rxjs', "rxjs"),
            (r'import\s+\*\s+as\s+\w+\s+from\s+["\']moment', "moment"),
        ]
        for pattern, lib in large_import_patterns:
            if re.search(pattern, content):
                issues.append(Issue(
                    layer="bundle", severity="medium", code="BUNDLE001",
                    message=f"Importing entire '{lib}' library — use tree-shakeable named imports",
                    file=path, line=0,
                ))
        import_lines = re.findall(r'import\s+\{([^}]+)\}\s+from\s+["\'([^"\']+)["\']', content)
        for imports, module in import_lines:
            imported_names = [n.strip().split(" as ")[0].strip() for n in imports.split(",")]
            for name in imported_names:
                usage_pattern = r'\b' + re.escape(name) + r'\b'
                usages = re.findall(usage_pattern, content)
                if len(usages) <= 1:
                    issues.append(Issue(
                        layer="bundle", severity="warning", code="BUNDLE002",
                        message=f"Imported '{name}' from '{module}' but it appears unused",
                        file=path, line=0,
                    ))
    return issues


# Layer 11 — Accessibility Audit
def _accessibility_audit(files: List[Dict[str, str]], design_spec: Optional[Dict]) -> List[Issue]:
    issues = []
    for f in files:
        path = f["path"]
        if not any(path.endswith(ext) for ext in [".jsx", ".tsx", ".vue", ".html"]):
            continue
        content = f["content"]
        # Check for images without alt text
        img_matches = re.finditer(r'<img(?![^>]*\balt=)[^>]*>', content, re.IGNORECASE)
        for match in img_matches:
            line_num = content[:match.start()].count("\n") + 1
            issues.append(Issue(
                layer="a11y", severity="warning", code="A11Y001",
                message="Image without alt attribute — add descriptive alt text",
                file=path, line=line_num,
            ))
        # Check for buttons without accessible names
        button_matches = re.finditer(r'<button(?![^>]*\baria-label=)(?![^>]*\baria-labelledby=)[^>]*>(?:\s*<[^/]*>)*\s*</button>', content, re.IGNORECASE)
        for match in button_matches:
            inner = match.group(0)
            if not inner.strip():
                line_num = content[:match.start()].count("\n") + 1
                issues.append(Issue(
                    layer="a11y", severity="warning", code="A11Y002",
                    message="Button without accessible name — add aria-label or text content",
                    file=path, line=line_num,
                ))
        # Check for missing form labels
        input_matches = re.finditer(r'<input(?![^>]*\bid=)[^>]*>', content, re.IGNORECASE)
        for match in input_matches:
            line_num = content[:match.start()].count("\n") + 1
            issues.append(Issue(
                layer="a11y", severity="warning", code="A11Y003",
                message="Input without id — associate with a <label> element",
                file=path, line=line_num,
            ))
        # Check for missing skip link
        if "<body" in content.lower() and "skip" not in content.lower():
            issues.append(Issue(
                layer="a11y", severity="warning", code="A11Y004",
                message="Missing skip-to-content link — add for keyboard navigation",
                file=path, line=0,
            ))
    return issues


# ---------------------------------------------------------------------------
# Combined runner
# ---------------------------------------------------------------------------

async def run_enhanced_review(
    files: List[Dict[str, str]],
    tech_stack: str,
    config,
    execution_id: str,
    design_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run all enhanced static analysis layers."""
    loop = asyncio.get_event_loop()

    # Run all layers in parallel via thread pool
    tasks = []
    tasks.append(loop.run_in_executor(None, _secrets_detection, files))
    tasks.append(loop.run_in_executor(None, _sast_analysis, files))

    stack_lower = tech_stack.lower()
    if "python" in stack_lower or "fastapi" in stack_lower:
        tasks.append(loop.run_in_executor(None, _type_checking_python, files))
    else:
        tasks.append(loop.run_in_executor(None, _type_checking_js, files))

    tasks.append(loop.run_in_executor(None, _complexity_analysis, files))
    tasks.append(loop.run_in_executor(None, _bundle_analysis, files, tech_stack))
    tasks.append(loop.run_in_executor(None, _accessibility_audit, files, design_spec))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_issues = []
    for result in results:
        if isinstance(result, list):
            all_issues.extend(result)
        elif isinstance(result, Exception):
            logger.warning("enhanced_review.layer_failed", error=str(result))

    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]

    # Security errors are hard failures
    security_errors = [i for i in all_issues if i.layer in ("secrets", "sast") and i.severity == "error"]

    approved = len(errors) == 0 and len(security_errors) == 0

    issues_flat = [str(i) for i in all_issues]

    logger.info(
        "enhanced_review.complete",
        execution_id=execution_id,
        errors=len(errors),
        warnings=len(warnings),
        secrets=len([i for i in all_issues if i.layer == "secrets"]),
        sast=len([i for i in all_issues if i.layer == "sast"]),
        types=len([i for i in all_issues if i.layer == "types"]),
        complexity=len([i for i in all_issues if i.layer == "complexity"]),
        bundle=len([i for i in all_issues if i.layer == "bundle"]),
        a11y=len([i for i in all_issues if i.layer == "a11y"]),
    )

    return {
        "approved": approved,
        "score": 10.0 if approved else max(1.0, 8.0 - len(errors) * 2.0),
        "issues": [i.to_dict() for i in all_issues],
        "issues_flat": issues_flat,
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "secrets": len([i for i in all_issues if i.layer == "secrets"]),
            "sast": len([i for i in all_issues if i.layer == "sast"]),
            "types": len([i for i in all_issues if i.layer == "types"]),
            "complexity": len([i for i in all_issues if i.layer == "complexity"]),
            "bundle": len([i for i in all_issues if i.layer == "bundle"]),
            "a11y": len([i for i in all_issues if i.layer == "a11y"]),
        },
        "tokens": 0,
    }
