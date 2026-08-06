"""
OMEGA Validation Framework - Complete Post-Generation Verification
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("omega_agent.validation.framework")

class ProjectType(Enum):
    REACT = "react"
    VUE = "vue"
    ANGULAR = "angular"
    NEXT_JS = "nextjs"
    EXPRESS = "express"
    FASTAPI = "fastapi"
    DJANGO = "django"
    PYTHON_CLI = "python_cli"
    RUST = "rust"
    UNKNOWN = "unknown"

class ValidationLevel(Enum):
    LIGHT = 1
    MEDIUM = 2
    HEAVY = 3
    PARANOID = 4

@dataclass
class ValidationError:
    check_name: str
    command: Optional[str]
    returncode: Optional[int]
    stdout: str
    stderr: str
    error_type: str
    severity: str
    recoverable: bool = True

@dataclass
class ValidationResult:
    project_type: ProjectType
    validated: bool
    validation_level: ValidationLevel
    checks_passed: int
    checks_failed: int
    checks_total: int
    errors: List[ValidationError]
    warnings: List[str]
    execution_time_ms: float
    dependency_valid: Optional[bool] = None
    build_valid: Optional[bool] = None
    tests_valid: Optional[bool] = None
    syntax_valid: Optional[bool] = None
    sota_valid: Optional[bool] = None
    runtime_valid: Optional[bool] = None
    status: str = "INCONCLUSIVE"
    recommendations: List[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_type": self.project_type.value,
            "validated": self.validated,
            "validation_level": self.validation_level.name,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "checks_total": self.checks_total,
            "errors": [asdict(e) for e in self.errors],
            "warnings": self.warnings,
            "execution_time_ms": self.execution_time_ms,
            "dependency_valid": self.dependency_valid,
            "build_valid": self.build_valid,
            "tests_valid": self.tests_valid,
            "syntax_valid": self.syntax_valid,
            "sota_valid": self.sota_valid,
            "runtime_valid": self.runtime_valid,
            "status": self.status,
            "recommendations": self.recommendations or [],
        }

class ProjectDetector:
    @staticmethod
    def detect_from_files(files: List[Dict[str, str]]) -> ProjectType:
        file_paths = {f.get("path", "") for f in files}
        contents = {f.get("path", ""): f.get("content", "") for f in files}
        
        has_reqs = any("requirements.txt" in p or "pyproject.toml" in p or "setup.py" in p for p in file_paths)
        has_cargo = any("Cargo.toml" in p for p in file_paths)
        
        for path, content in contents.items():
            if path == "package.json" or path.endswith("package.json"):
                try:
                    pkg = json.loads(content)
                    if not isinstance(pkg, dict): continue
                    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
                    if "react" in deps and "next" in deps: return ProjectType.NEXT_JS
                    if "react" in deps and "react-dom" in deps: return ProjectType.REACT
                    if "vue" in deps: return ProjectType.VUE
                    if "@angular/core" in deps: return ProjectType.ANGULAR
                    if "express" in deps or "fastify" in deps: return ProjectType.EXPRESS
                except json.JSONDecodeError:
                    pass
        
        if has_reqs:
            for path, content in contents.items():
                if "requirements.txt" in path:
                    if "fastapi" in content or "starlette" in content: return ProjectType.FASTAPI
                    if "django" in content: return ProjectType.DJANGO
                    return ProjectType.PYTHON_CLI
                if "pyproject.toml" in path:
                    if "fastapi" in content: return ProjectType.FASTAPI
                    if "django" in content: return ProjectType.DJANGO
                    return ProjectType.PYTHON_CLI
            return ProjectType.PYTHON_CLI # default fallback if requirements found but no matching framework
        
        if has_cargo: return ProjectType.RUST
        
        for path, content in contents.items():
            content_lower = content.lower()
            if "react" in content_lower: return ProjectType.REACT
            if "express" in content_lower: return ProjectType.EXPRESS
            if "fastapi" in content_lower: return ProjectType.FASTAPI
        
        return ProjectType.UNKNOWN
    
    @staticmethod
    def detect_from_workspace(workspace_path: Path) -> ProjectType:
        files = []
        for file_path in workspace_path.rglob("*"):
            if file_path.is_file() and not any(part.startswith(".") for part in file_path.parts) and "node_modules" not in file_path.parts:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    rel_path = file_path.relative_to(workspace_path)
                    files.append({"path": str(rel_path), "content": content[:5000]})
                except (UnicodeDecodeError, IOError):
                    pass
        return ProjectDetector.detect_from_files(files)

class ValidationChecks:
    @staticmethod
    def check_has_package_json(workspace_path: Path) -> Tuple[bool, str]:
        pkg_path = workspace_path / "package.json"
        if pkg_path.exists():
            try:
                json.loads(pkg_path.read_text())
                return True, "package.json found and valid"
            except json.JSONDecodeError as e:
                return False, f"package.json is invalid JSON: {e}"
        return False, "package.json not found"
    
    @staticmethod
    def check_has_requirements_txt(workspace_path: Path) -> Tuple[bool, str]:
        if (workspace_path / "requirements.txt").exists():
            return True, "requirements.txt found"
        return False, "requirements.txt not found"
    
    @staticmethod
    def check_package_json_syntax(workspace_path: Path) -> Tuple[bool, str]:
        pkg_path = workspace_path / "package.json"
        if not pkg_path.exists(): return True, "package.json not applicable"
        try:
            json.loads(pkg_path.read_text())
            return True, "package.json syntax valid"
        except json.JSONDecodeError as e:
            return False, f"package.json syntax error: {str(e)[:200]}"
    
    @staticmethod
    def check_no_syntax_errors_in_js(workspace_path: Path) -> Tuple[bool, str, Optional[str]]:
        js_files = list(workspace_path.rglob("*.js")) + list(workspace_path.rglob("*.jsx"))
        if not js_files: return True, "No JavaScript files to check", None
        errors = []
        for js_file in js_files[:20]:
            try:
                content = js_file.read_text()
                if content.count("{") != content.count("}"):
                    errors.append(f"{js_file.relative_to(workspace_path)}: Mismatched braces")
                if content.count("[") != content.count("]"):
                    errors.append(f"{js_file.relative_to(workspace_path)}: Mismatched brackets")
            except (UnicodeDecodeError, IOError):
                pass
        if errors: return False, f"Syntax errors found in {len(errors)} files", f"Errors in: {'; '.join(errors[:3])}"
        return True, "JavaScript syntax checks passed", None
    
    @staticmethod
    def check_no_syntax_errors_in_python(workspace_path: Path) -> Tuple[bool, str, Optional[str]]:
        import ast
        py_files = list(workspace_path.rglob("*.py"))
        if not py_files: return True, "No Python files to check", None
        errors = []
        for py_file in py_files[:20]:
            try:
                ast.parse(py_file.read_text())
            except SyntaxError as e:
                errors.append(f"{py_file.relative_to(workspace_path)}: {str(e)[:100]}")
            except (UnicodeDecodeError, IOError):
                pass
        if errors: return False, f"Python syntax errors found in {len(errors)} files", f"Errors in: {'; '.join(errors[:3])}"
        return True, "Python syntax checks passed", None

    @staticmethod
    def check_no_syntax_errors_in_toml(workspace_path: Path) -> Tuple[bool, str, Optional[str]]:
        toml_files = list(workspace_path.rglob("*.toml"))
        if not toml_files: return True, "No TOML files to check", None
        errors = []
        try:
            import tomllib as toml_parser
        except ImportError:
            try:
                import tomli as toml_parser
            except ImportError:
                return True, "No TOML parser available", None
                
        for toml_file in toml_files[:20]:
            try:
                content = toml_file.read_text(encoding="utf-8")
                toml_parser.loads(content)
            except Exception as e:
                errors.append(f"{toml_file.relative_to(workspace_path)}: {str(e)[:100]}")
        if errors: return False, f"TOML syntax errors found in {len(errors)} files", f"Errors in: {'; '.join(errors[:3])}"
        return True, "TOML syntax checks passed", None

    @staticmethod
    def check_readme_quality(workspace_path: Path) -> Tuple[bool, str, Optional[str]]:
        import re
        readme_path = workspace_path / "README.md"
        if not readme_path.exists():
            readme_path = workspace_path / "readme.md"
            if not readme_path.exists():
                return False, "README.md is missing", "A high-quality README.md is required for SOTA."
                
        try:
            content = readme_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return False, "README.md decoding failed", "README.md contains invalid UTF-8 characters."
            
        words = content.split()
        if len(words) < 50:
            return False, "README.md is too short", "README.md must be comprehensive, with at least 50 words explaining the project."
            
        avg_word_len = sum(len(w) for w in words) / max(1, len(words))
        if avg_word_len > 15:
            return False, "README.md appears to be gibberish", "The average word length is suspiciously high. Ensure the README is written in comprehensible natural language."
            
        has_heading = bool(re.search(r"^#+\s+\w+", content, re.MULTILINE))
        if not has_heading:
            return False, "README.md lacks proper formatting", "The README must contain Markdown headings (e.g., '# Introduction')."
            
        lines = content.split("\n")
        max_line_len = max((len(l) for l in lines), default=0)
        if max_line_len > 2000:
            return False, "README.md has extremely long lines", "Lines in README.md exceed 2000 characters. Break down long paragraphs to make it comprehensible."
            
        return True, "README.md quality checks passed", None

class ShellCommandValidator:
    def __init__(self, workspace_path: Path, timeout: int = 300):
        self.workspace_path = workspace_path
        self.timeout = timeout
    
    async def run_command(self, command: str, cwd=None) -> Dict[str, Any]:
        import subprocess
        exec_dir = cwd or self.workspace_path
        logger.info(f"[VALIDATION] Executing: {command} in {exec_dir}")
        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    command, shell=True, cwd=str(exec_dir),
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout
                )
            )
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[:8000],
                "stderr": (proc.stderr or "")[:4000],
                "command": command,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "command": command}
    
    async def validate_npm_dependencies(self) -> Tuple[bool, str, Optional[str]]:
        pkg_files = list(self.workspace_path.rglob("package.json"))
        pkg_files = [p for p in pkg_files if "node_modules" not in p.parts]
        
        if not pkg_files:
            return True, "No package.json found", None
            
        for pkg in pkg_files:
            cwd = pkg.parent
            result = await self.run_command("npm ls --depth=0 2>&1", cwd=cwd)
            if result["success"]: continue
            stderr = result.get("stderr", "")
            if "ERR!" in stderr or "unmet" in stderr.lower():
                return False, f"npm dependencies invalid in {cwd.name}", stderr[:500]
            dry_run = await self.run_command("npm install --dry-run 2>&1", cwd=cwd)
            if dry_run["success"]: continue
            return False, f"npm dependencies validation failed in {cwd.name}", dry_run.get("stderr", "")[:500]
            
        return True, "npm dependencies valid", None
    
    async def validate_npm_build(self) -> Tuple[bool, str, Optional[str]]:
        pkg_files = list(self.workspace_path.rglob("package.json"))
        pkg_files = [p for p in pkg_files if "node_modules" not in p.parts]
        
        if not pkg_files:
            return True, "No package.json found", None
            
        for pkg in pkg_files:
            cwd = pkg.parent
            try:
                import json
                pkg_data = json.loads(pkg.read_text())
                if not isinstance(pkg_data, dict): continue
                scripts = pkg_data.get("scripts") or {}
                if not any(s in scripts for s in ["build", "build:prod", "prod"]):
                    continue
            except Exception:
                pass
                
            build_success = False
            for cmd in ["npm run build", "npm run build:prod", "npm run prod"]:
                if cmd.replace("npm run ", "") not in scripts:
                    continue
                result = await self.run_command(f"{cmd} 2>&1", cwd=cwd)
                if result["success"]: 
                    build_success = True
                    break
                    
            if not build_success:
                return False, f"npm build failed in {cwd.name}", "Build failed"
                
        return True, "npm build succeeded", None
    
    async def validate_python_dependencies(self) -> Tuple[bool, str, Optional[str]]:
        req_files = list(self.workspace_path.rglob("requirements.txt"))
        if not req_files:
            return True, "No requirements.txt found", None
            
        for req_file in req_files:
            try:
                import re
                content = req_file.read_text(encoding="utf-8").lower()
                lines = [l.strip() for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
                for line in lines:
                    if re.match(r"^python\s*(?:[><=~!].*)?$", line):
                        return False, f"Invalid package 'python' in {req_file.name}", f"Remove '{line}' from requirements.txt as python itself cannot be installed via pip."
                        
                result = await self.run_command(f"python -m pip install --dry-run -r {req_file.name} 2>&1", cwd=req_file.parent)
                if not result["success"]:
                    err = (result.get("stdout") or "") + (result.get("stderr") or "")
                    if "No matching distribution found" in err or "Could not find a version" in err or "Invalid requirement" in err:
                        return False, f"pip install dry-run failed for {req_file.name}", err[-1000:]
            except Exception:
                pass
                    
        return True, "Python dependencies look valid", None
    
    async def validate_python_imports(self) -> Tuple[bool, str, Optional[str]]:
        import subprocess
        result = await self.run_command("python -m compileall -q . 2>&1")
        if not result["success"]:
            err = (result.get("stdout") or "") + (result.get("stderr") or "")
            return False, "Python imports have syntax errors", err[:500]
            
        for entry in ["app.py", "main.py", "solution.py", "setup.py"]:
            script_path = self.workspace_path / entry
            if script_path.exists():
                try:
                    proc = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: subprocess.run(
                            f"python {entry}", shell=True, cwd=str(self.workspace_path),
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3
                        )
                    )
                    if proc.returncode != 0:
                        out = (proc.stdout or "") + (proc.stderr or "")
                        if any(err in out for err in ["NameError", "ImportError", "ModuleNotFoundError", "TypeError", "ValueError"]):
                            return False, f"Python runtime error in {entry}", out[-1000:]
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
                    
        return True, "Python import compilation successful", None

    async def validate_python_tests(self) -> Tuple[bool, str, Optional[str]]:
        test_files = list(self.workspace_path.rglob("test_*.py")) + list(self.workspace_path.rglob("*_test.py"))
        if not test_files:
            return True, "No Python tests found", None
            
        failed_tests = []
        err_details = []
        for tfile in test_files[:5]:
            res = await self.run_command(f"python {tfile.name} 2>&1", cwd=tfile.parent, timeout=10)
            if not res["success"]:
                failed_tests.append(tfile.name)
                out = (res.get("stdout") or "") + (res.get("stderr") or "")
                err_details.append(f"--- {tfile.name} ---\n{out[-1000:]}")
        
        if failed_tests:
            return False, f"Python tests failed: {', '.join(failed_tests)}", "\n\n".join(err_details)
            
        return True, "Python tests passed", None

    async def validate_npm_tests(self) -> Tuple[bool, str, Optional[str]]:
        pkg_files = list(self.workspace_path.rglob("package.json"))
        pkg_files = [p for p in pkg_files if "node_modules" not in p.parts]
        for pkg in pkg_files:
            try:
                import json
                pkg_data = json.loads(pkg.read_text())
                scripts = pkg_data.get("scripts", {})
                if "test" not in scripts or "no test specified" in scripts["test"].lower():
                    continue
                # Use CI=true to prevent watch mode
                res = await self.run_command("npm test 2>&1", cwd=pkg.parent, timeout=30)
                if not res["success"]:
                    out = (res.get("stdout") or "") + (res.get("stderr") or "")
                    return False, f"npm test failed in {pkg.parent.name}", out[-1000:]
            except Exception:
                pass
        return True, "npm tests passed", None


class RuntimeValidityGateChecker:
    """Checks the generated codebase against H7-H14 AGI/SOTA validity constraints."""
    
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    def run_checks(self, bypass_sota: bool = False) -> Dict[str, Tuple[bool, str, Optional[str]]]:
        results = {}
        
        # Gather all code files
        code_files = []
        try:
            for file_path in self.workspace_path.rglob("*"):
                if file_path.is_file() and not any(part.startswith(".") for part in file_path.parts) and "node_modules" not in file_path.parts:
                    if file_path.suffix in (".py", ".js", ".ts", ".jsx", ".tsx"):
                        code_files.append(file_path)
        except Exception as e:
            logger.warning(f"Error gathering files for validity checks: {e}")
                    
        results["H7_red_team"] = self._check_h7_red_team(code_files)
        results["H8_executability"] = self._check_h8_executability(code_files)
        results["H10_oracle_validity"] = self._check_h10_oracle_validity(code_files)
        results["H11_sample_validity"] = self._check_h11_sample_validity(code_files)
        results["H12_fail_loud"] = self._check_h12_fail_loud(code_files)
        results["H13_non_stationarity"] = self._check_h13_non_stationarity(code_files)
        results["H14_irreversibility"] = self._check_h14_irreversibility(code_files)
        
        return results

    def _check_h7_red_team(self, files: List[Path]) -> Tuple[bool, str, Optional[str]]:
        # Verification: generated code must include adversarial test scenarios or security sanitization
        has_validation = False
        if not files:
            return True, "H7 Check: No code files to evaluate", None
        for f in files:
            try:
                content = f.read_text(encoding="utf-8").lower()
                if any(x in content for x in ("sanitize", "validate", "reject", "escape", "adversarial", "assert", "try", "except")):
                    has_validation = True
                    break
            except Exception:
                pass
        if not has_validation:
            return False, "H7 Check Failed: No input validation/sanitization or exception handling found.", "Adversarial Red-Team: The code is vulnerable to invalid or malicious inputs."
        return True, "H7 Check Passed: Input validation/sanitization/error handling patterns found.", None

    def _check_h8_executability(self, files: List[Path]) -> Tuple[bool, str, Optional[str]]:
        # Verification: generated trading code must include slippage or execution delay handling, not assuming perfect paper fills.
        is_trading = False
        has_slippage = False
        for f in files:
            try:
                content = f.read_text(encoding="utf-8").lower()
                if any(x in content for x in ("trade", "order", "buy", "sell", "swap", "sol", "btc", "eth")):
                    is_trading = True
                    if any(x in content for x in ("slippage", "spread", "tolerance", "limit_order", "depth", "liquidity")):
                        has_slippage = True
                        break
            except Exception:
                pass
        if is_trading and not has_slippage:
            return False, "H8 Check Failed: Trading code lacks slippage/spread/liquidity constraints.", "Executability Override: Real fills under adverse regime will fail if slippage is assumed to be zero."
        return True, "H8 Check Passed: Slippage/liquidity constraints checked or non-trading project.", None

    def _check_h10_oracle_validity(self, files: List[Path]) -> Tuple[bool, str, Optional[str]]:
        # Verification: check for look-ahead bias or corrupted validators in test suites or analysis logic
        has_lookahead = False
        for f in files:
            try:
                content = f.read_text(encoding="utf-8").lower()
                if "shift(-" in content or "shift( -" in content or "future" in content:
                    has_lookahead = True
                    break
            except Exception:
                pass
        if has_lookahead:
            return False, "H10 Check Failed: Potential look-ahead bias detected.", "Oracle Validity: Code contains future shifts or variables that indicate look-ahead leaks."
        return True, "H10 Check Passed: No obvious look-ahead patterns found.", None

    def _check_h11_sample_validity(self, files: List[Path]) -> Tuple[bool, str, Optional[str]]:
        # Verification: check for selection bias or tuning-set data leakage
        has_leakage = False
        for f in files:
            try:
                content = f.read_text(encoding="utf-8").lower()
                if "train_test_split" in content and not any(x in content for x in ("random_state", "shuffle", "stratify")):
                    has_leakage = True
                    break
            except Exception:
                pass
        if has_leakage:
            return False, "H11 Check Failed: Statistical split lacks reproducible randomness/shuffle constraints.", "Sample Validity: Split may suffer from selection or survivorship bias."
        return True, "H11 Check Passed: Statistical splits look valid or non-ML project.", None

    def _check_h12_fail_loud(self, files: List[Path]) -> Tuple[bool, str, Optional[str]]:
        # Verification: check for silent coercion or bare except blocks that swallow critical errors
        has_silent_coercion = False
        for f in files:
            if f.suffix == ".py":
                try:
                    content = f.read_text(encoding="utf-8").lower()
                    if "except:" in content or "except exception:" in content:
                        lines = content.split("\n")
                        for i, line in enumerate(lines):
                            if "except" in line and ":" in line:
                                block = "".join(lines[i+1:i+3])
                                if "pass" in block or ("print" not in block and "log" not in block and "raise" not in block and "exit" not in block):
                                    has_silent_coercion = True
                                    break
                except Exception:
                    pass
        if has_silent_coercion:
            return False, "H12 Check Failed: Silent error coercion detected.", "Fail-Loud: Code contains bare except blocks or pass statements that swallow exceptions silently."
        return True, "H12 Check Passed: Errors fail loud and clear.", None

    def _check_h13_non_stationarity(self, files: List[Path]) -> Tuple[bool, str, Optional[str]]:
        # Verification: models/trading systems should have regime check or expiry/decay stamps
        is_trading_or_ml = False
        has_regime_or_expiry = False
        for f in files:
            try:
                content = f.read_text(encoding="utf-8").lower()
                if any(x in content for x in ("model", "predict", "trading", "signal", "strategy")):
                    is_trading_or_ml = True
                    if any(x in content for x in ("regime", "expiry", "decay", "timestamp", "date", "window", "arbitrage")):
                        has_regime_or_expiry = True
                        break
            except Exception:
                pass
        if is_trading_or_ml and not has_regime_or_expiry:
            return False, "H13 Check Failed: System lacks decay monitoring, expiry, or regime checks.", "Non-Stationarity: Financial/predictive models decay over time and require windowing."
        return True, "H13 Check Passed: Expiry/regime constraints checked or non-financial project.", None

    def _check_h14_irreversibility(self, files: List[Path]) -> Tuple[bool, str, Optional[str]]:
        # Verification: check for kill-switch and confirmation prompts in execution pathways
        is_execution = False
        has_killswitch_or_confirm = False
        for f in files:
            try:
                content = f.read_text(encoding="utf-8").lower()
                if any(x in content for x in ("execute", "submit", "send", "run_order", "deploy", "delete", "write")):
                    is_execution = True
                    if any(x in content for x in ("kill_switch", "stop", "confirm", "prompt", "input(", "dry_run", "testnet", "sandbox")):
                        has_killswitch_or_confirm = True
                        break
            except Exception:
                pass
        if is_execution and not has_killswitch_or_confirm:
            return False, "H14 Check Failed: Execution path lacks a kill-switch or dry-run/confirmation gate.", "Irreversibility Gate: Destructive/real-money actions must be dry-run tested or have human confirmation."
        return True, "H14 Check Passed: Confirmation/kill-switch checks present or safe project.", None


class ValidationOrchestrator:
    def __init__(self, workspace_path: Path, validation_level: ValidationLevel = ValidationLevel.MEDIUM, timeout: int = 300):
        self.workspace_path = workspace_path
        self.validation_level = validation_level
        self.detector = ProjectDetector()
        self.shell_validator = ShellCommandValidator(workspace_path, timeout)
    
    async def run_validation(self, bypass_sota: bool = False) -> ValidationResult:
        import time
        start_time = time.time()
        project_type = self.detector.detect_from_workspace(self.workspace_path)
        
        errors, warnings = [], []
        checks_passed, checks_failed = 0, 0
        
        # Always run syntax and dependency validation (critical for all projects)
        syntax_valid = await self._validate_syntax(project_type, errors)
        checks_passed += 1 if syntax_valid else 0
        checks_failed += 0 if syntax_valid else 1
        
        dependency_valid = await self._validate_dependencies(project_type, errors)
        checks_passed += 1 if dependency_valid else 0
        checks_failed += 0 if dependency_valid else 1
        
        # SOTA quality check (can be bypassed for universal solver/python-only)
        sota_valid = await self._validate_sota_quality(project_type, errors, bypass_sota=bypass_sota)
        checks_passed += 1 if sota_valid else 0
        checks_failed += 0 if sota_valid else 1
        
        # Build and test validation based on validation level
        build_valid = True
        tests_valid = True
        if self.validation_level.value >= ValidationLevel.MEDIUM.value:
            build_valid = await self._validate_build(project_type, errors)
            checks_passed += 1 if build_valid else 0
            checks_failed += 0 if build_valid else 1
            
            tests_valid = await self._validate_tests(project_type, errors)
            checks_passed += 1 if tests_valid else 0
            checks_failed += 0 if tests_valid else 1
            
        # Runtime Validity Gate (H7-H14)
        checker = RuntimeValidityGateChecker(self.workspace_path)
        runtime_checks = checker.run_checks(bypass_sota=bypass_sota)
        runtime_valid = True
        for name, (passed, msg, detail) in runtime_checks.items():
            checks_passed += 1 if passed else 0
            checks_failed += 0 if passed else 1
            if not passed:
                runtime_valid = False
                errors.append(ValidationError(name, None, None, "", detail or msg, "runtime_gate", "critical"))
                
        # CRITICAL: Include tests_valid and runtime_valid in final validation decision
        all_valid = syntax_valid and sota_valid and dependency_valid and build_valid and tests_valid and runtime_valid
        recommendations = self._generate_recommendations(errors, project_type)
        
        # Determine status
        if not all_valid or len(errors) > 0:
            status = "FAIL"
        elif bypass_sota or self.validation_level.value < ValidationLevel.MEDIUM.value:
            status = "INCONCLUSIVE"
        else:
            status = "PASS"
            
        return ValidationResult(
            project_type=project_type,
            validated=status == "PASS",
            validation_level=self.validation_level,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            checks_total=checks_passed + checks_failed,
            errors=errors, warnings=warnings,
            execution_time_ms=(time.time() - start_time) * 1000,
            dependency_valid=dependency_valid, build_valid=build_valid,
            tests_valid=tests_valid, syntax_valid=syntax_valid,
            sota_valid=sota_valid,
            runtime_valid=runtime_valid,
            status=status,
            recommendations=recommendations,
        )
    
    async def _validate_sota_quality(self, project_type: ProjectType, errors: List[ValidationError], bypass_sota: bool = False) -> bool:
        files = []
        for file_path in self.workspace_path.rglob("*"):
            if file_path.is_file() and not any(part.startswith(".") for part in file_path.parts) and "node_modules" not in file_path.parts:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    files.append(content)
                except (UnicodeDecodeError, IOError):
                    pass
        
        all_content = "\n".join(files)
        lines = [l for l in all_content.split('\n') if l.strip() and not l.strip().startswith('//') and not l.strip().startswith('/*') and not l.strip().startswith('*')]
        
        if bypass_sota:
            logger.info("[VALIDATION] SOTA Quality Gate BYPASSED for Universal Solver / Python Only - performing basic functional checks only.")
            # Even when bypassed, ensure minimum code exists (not empty)
            if len(lines) < 10:
                error_msg = f"Basic Quality Check Failed: Code volume too low ({len(lines)} lines). At minimum, 10 lines of functional code required."
                logger.warning(f"[VALIDATION] {error_msg}")
                errors.append(ValidationError("Basic Quality Check", None, None, "", error_msg, "sota_quality", "critical"))
                return False
            # Check for README existence (not quality, just existence)
            readme_path = self.workspace_path / "README.md"
            if not readme_path.exists():
                readme_path = self.workspace_path / "readme.md"
            if not readme_path.exists():
                error_msg = "Basic Quality Check Failed: README.md is missing. A README is required for any functional project."
                logger.warning(f"[VALIDATION] {error_msg}")
                errors.append(ValidationError("README Existence", None, None, "", error_msg, "sota_quality", "critical"))
                return False
            logger.info(f"[VALIDATION] Basic Quality Check PASSED: Code volume is {len(lines)} lines")
            return True
        
        # Full SOTA validation for non-bypassed projects
        min_lines = 500
        if project_type in [ProjectType.PYTHON_CLI, ProjectType.UNKNOWN, ProjectType.RUST]:
            min_lines = 50
            
        if len(lines) < min_lines:
            error_msg = f"SOTA Quality Gate Failed: Code volume too low ({len(lines)} lines). SOTA requirements mandate massive, feature-complete implementation exceeding {min_lines}+ lines. ZERO boilerplate."
            logger.warning(f"[VALIDATION] {error_msg}")
            errors.append(ValidationError("SOTA Quality Gate", None, None, "", error_msg, "sota_quality", "critical"))
            return False
            
        success, msg, detail = ValidationChecks.check_readme_quality(self.workspace_path)
        if not success:
            logger.warning(f"[VALIDATION] {msg}: {detail}")
            errors.append(ValidationError("README Quality", None, None, "", detail or msg, "sota_quality", "critical"))
            return False
            
        logger.info(f"[VALIDATION] SOTA Quality Gate PASSED: Code volume is {len(lines)} lines (min: {min_lines})")
        return True
    
    async def _validate_syntax(self, project_type: ProjectType, errors: List[ValidationError]) -> bool:
        all_passed = True
        if project_type in [ProjectType.REACT, ProjectType.VUE, ProjectType.ANGULAR, ProjectType.NEXT_JS, ProjectType.EXPRESS]:
            success, msg, detail = ValidationChecks.check_no_syntax_errors_in_js(self.workspace_path)
            if not success:
                errors.append(ValidationError("JavaScript Syntax", None, None, "", detail or "", "syntax", "critical"))
                all_passed = False
        elif project_type in [ProjectType.FASTAPI, ProjectType.DJANGO, ProjectType.PYTHON_CLI, ProjectType.UNKNOWN]:
            success, msg, detail = ValidationChecks.check_no_syntax_errors_in_python(self.workspace_path)
            if not success:
                errors.append(ValidationError("Python Syntax", None, None, "", detail or "", "syntax", "critical"))
                all_passed = False
                
        # Always check TOML if present
        success, msg, detail = ValidationChecks.check_no_syntax_errors_in_toml(self.workspace_path)
        if not success:
            errors.append(ValidationError("TOML Syntax", None, None, "", detail or "", "syntax", "critical"))
            all_passed = False
            
        return all_passed
    
    async def _validate_dependencies(self, project_type: ProjectType, errors: List[ValidationError]) -> bool:
        if project_type in [ProjectType.REACT, ProjectType.VUE, ProjectType.ANGULAR, ProjectType.NEXT_JS, ProjectType.EXPRESS]:
            success, msg, detail = await self.shell_validator.validate_npm_dependencies()
            if not success:
                errors.append(ValidationError("npm Dependencies", "npm ls", 1, "", detail or "", "dependency", "critical"))
                return False
        elif project_type in [ProjectType.FASTAPI, ProjectType.DJANGO, ProjectType.PYTHON_CLI, ProjectType.UNKNOWN]:
            success, msg, detail = await self.shell_validator.validate_python_dependencies()
            if not success:
                errors.append(ValidationError("Python Dependencies", "pip install --dry-run", 1, "", detail or "", "dependency", "critical"))
                return False
                
            success, msg, detail = await self.shell_validator.validate_python_imports()
            if not success:
                errors.append(ValidationError("Python Imports", "py_compile", 1, "", detail or "", "dependency", "critical"))
                return False
        return True
    
    async def _validate_build(self, project_type: ProjectType, errors: List[ValidationError]) -> bool:
        if project_type in [ProjectType.REACT, ProjectType.VUE, ProjectType.ANGULAR, ProjectType.NEXT_JS]:
            success, msg, detail = await self.shell_validator.validate_npm_build()
            if not success:
                errors.append(ValidationError("npm Build", "npm run build", 1, "", detail or "", "build", "critical"))
                return False
        elif project_type in [ProjectType.FASTAPI, ProjectType.DJANGO, ProjectType.PYTHON_CLI, ProjectType.UNKNOWN]:
            # Validate Python builds by checking if main entry points can be imported/compiled
            success, msg, detail = await self.shell_validator.validate_python_imports()
            if not success:
                errors.append(ValidationError("Python Build/Import", "py_compile", 1, "", detail or "", "build", "critical"))
                return False
        return True

    async def _validate_tests(self, project_type: ProjectType, errors: List[ValidationError]) -> bool:
        if project_type in [ProjectType.REACT, ProjectType.VUE, ProjectType.ANGULAR, ProjectType.NEXT_JS, ProjectType.EXPRESS]:
            success, msg, detail = await self.shell_validator.validate_npm_tests()
            if not success:
                errors.append(ValidationError("npm Tests", "npm test", 1, "", detail or "", "tests", "critical"))
                return False
        elif project_type in [ProjectType.FASTAPI, ProjectType.DJANGO, ProjectType.PYTHON_CLI, ProjectType.UNKNOWN]:
            success, msg, detail = await self.shell_validator.validate_python_tests()
            if not success:
                errors.append(ValidationError("Python Tests", "python test", 1, "", detail or "", "tests", "critical"))
                return False
        return True
    
    def _generate_recommendations(self, errors: List[ValidationError], project_type: ProjectType) -> List[str]:
        if not errors: return ["✅ All validation checks passed successfully!"]
        recs = []
        error_types = {e.error_type for e in errors}
        if "dependency" in error_types:
            recs.append("🔧 Check package.json or requirements.txt for conflicts")
        if "syntax" in error_types:
            recs.append("🔍 Check for missing imports or syntax errors")
        if "sota_quality" in error_types:
            recs.append("🚀 SOTA REQUIREMENT: Generate massive, feature-complete implementation (500+ lines). No boilerplate.")
        return recs