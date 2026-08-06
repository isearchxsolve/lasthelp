"""
OMEGA Validation Integration - Orchestrator Pipeline Integration
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from omega_agent.validation.validation_framework import (
    ValidationOrchestrator,
    ValidationLevel,
    ValidationResult,
    ProjectType,
)

logger = logging.getLogger("omega_agent.validation.integration")

class ValidationGate:
    def __init__(self, workspace_path: Path, validation_level: ValidationLevel = ValidationLevel.MEDIUM):
        self.workspace_path = workspace_path
        self.validation_level = validation_level
    
    async def validate_and_gate(self, bypass_sota: bool = False) -> Tuple[bool, ValidationResult]:
        orchestrator = ValidationOrchestrator(self.workspace_path, validation_level=self.validation_level)
        try:
            result = await orchestrator.run_validation(bypass_sota=bypass_sota)
            return result.validated, result
        except Exception as e:
            return False, ValidationResult(
                project_type=ProjectType.UNKNOWN, validated=False, validation_level=self.validation_level,
                checks_passed=0, checks_failed=1, checks_total=1, errors=[], warnings=[str(e)], execution_time_ms=0
            )

class ValidationErrorAnalyzer:
    @staticmethod
    def analyze(result: ValidationResult) -> Dict[str, Any]:
        if result.validated:
            return {"error_summary": "No errors", "root_causes": [], "suggested_fixes": [], "is_recoverable": True}
        
        root_causes = []
        for e in result.errors:
            if e.error_type == "dependency": root_causes.append(f"Dependency failure: {e.stderr[:100]}")
            if e.error_type == "syntax": root_causes.append(f"Syntax error: {e.stderr[:100]}")
            if e.error_type == "build": root_causes.append(f"Build failed: {e.stderr[:100]}")
            if e.error_type == "sota_quality": root_causes.append(f"Quality Check Failed: {e.stderr[:200]}")
            
        return {
            "error_summary": f"Validation failed with {len(result.errors)} issues.",
            "root_causes": root_causes,
            "suggested_fixes": ["Regenerate code addressing the specific build/syntax errors"],
            "is_recoverable": True,
        }

class RegenerationCoordinator:
    def __init__(self, llm_generate_files_fn=None):
        self.llm_generate_files_fn = llm_generate_files_fn
    
    async def attempt_recovery(self, goal: str, validation_result: ValidationResult, error_analysis: Dict[str, Any], max_attempts: int = 3, **llm_kwargs):
        if not self.llm_generate_files_fn or not error_analysis.get("is_recoverable"):
            return None
            
        recovery_context = f"\nVALIDATION FAILED. FIX THESE ISSUES:\n" + "\n".join(error_analysis["root_causes"])
        
        for attempt in range(max_attempts):
            try:
                regen_result = await self.llm_generate_files_fn(goal=goal + recovery_context, **llm_kwargs)
                if regen_result.get("success"):
                    return regen_result.get("files")
            except Exception as e:
                logger.warning(f"Recovery failed on attempt {attempt+1}: {e}")
        return None

class ValidationPipeline:
    def __init__(self, workspace_path: Path, validation_level: ValidationLevel = ValidationLevel.MEDIUM, llm_generate_files_fn=None, max_recovery_attempts: int = 2):
        self.workspace_path = workspace_path
        self.gate = ValidationGate(workspace_path, validation_level)
        self.analyzer = ValidationErrorAnalyzer()
        self.recovery = RegenerationCoordinator(llm_generate_files_fn)
        self.max_recovery_attempts = max_recovery_attempts
    
    async def execute(self, goal: str, allow_recovery: bool = True, **llm_kwargs) -> Dict[str, Any]:
        safe_goal = str(goal).lower() if goal else ""
        safe_web_ctx = str(llm_kwargs.get("web_context", "")).lower()
        bypass_sota = (
            llm_kwargs.get("python_only") is True or 
            "python only" in safe_goal or 
            "universal solver" in safe_goal or
            "universal solver" in safe_web_ctx
        )
        passed, result = await self.gate.validate_and_gate(bypass_sota=bypass_sota)
        if result.status == "PASS":
            return {"success": True, "validation_result": result.to_dict(), "report": "✅ RUNTIME VALIDITY PASSED"}
        elif result.status == "INCONCLUSIVE":
            return {"success": True, "validation_result": result.to_dict(), "report": "⚠️ RUNTIME VALIDITY INCONCLUSIVE (some checks bypassed)"}
            
        error_analysis = self.analyzer.analyze(result)
        recovery_successful = False
        regen_result_data = None
        
        if allow_recovery:
            # We need the full result from attempt_recovery to get the files_written, summary, etc.
            if not self.recovery.llm_generate_files_fn or not error_analysis.get("is_recoverable"):
                regen_result_data = None
            else:
                recovery_context = f"\nVALIDATION FAILED. FIX THESE ISSUES:\n" + "\n".join(error_analysis["root_causes"])
                for attempt in range(self.max_recovery_attempts):
                    try:
                        # Mark this as a recovery pass to prevent infinite validation loops
                        regen_result = await self.recovery.llm_generate_files_fn(goal=goal + recovery_context, is_recovery_pass=True, **llm_kwargs)
                        if regen_result.get("success"):
                            # CRITICAL: Even after recovery, validate the regenerated code to ensure it actually works
                            # Use LIGHT validation level for recovery to avoid excessive retries while still catching critical errors
                            recovery_passed, recovery_result = await self.gate.validate_and_gate(bypass_sota=bypass_sota)
                            if recovery_passed:
                                regen_result_data = regen_result
                                regen_result_data["validation_passed"] = True
                                regen_result_data["validation_result"] = recovery_result.to_dict()
                                break
                            else:
                                logger.warning(f"Recovery attempt {attempt+1} produced code that still failed validation")
                    except Exception as e:
                        logger.warning(f"Recovery failed on attempt {attempt+1}: {e}")

            recovery_successful = regen_result_data is not None
            
        return {
            "success": recovery_successful,
            "validation_result": result.to_dict(),
            "recovery_successful": recovery_successful,
            "recovered_result": regen_result_data,
            "report": f"{'✅ RECOVERED' if recovery_successful else '❌ FAILED'}\n{error_analysis['error_summary']}"
        }