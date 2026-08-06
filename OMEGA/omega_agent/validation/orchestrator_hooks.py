"""
OMEGA Orchestrator Hook - Main Workflow Integration
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

from omega_agent.validation.validation_framework import ValidationLevel
from omega_agent.validation.validation_integration import ValidationPipeline

logger = logging.getLogger("omega_agent.orchestrator.hooks")

class ValidatedGenerationHook:
    def __init__(self, workspace_path: Path, workspace_id: str, validation_level: ValidationLevel = ValidationLevel.MEDIUM):
        self.workspace_path = workspace_path
        self.workspace_id = workspace_id
        self.validation_level = validation_level
    
    async def execute_validated_generation(self, llm_generate_files_fn, goal: str, **kwargs) -> Dict[str, Any]:
        gen_result = await llm_generate_files_fn(goal=goal, **kwargs)
        if not gen_result.get("success"):
            return {"success": False, "validation_passed": False, "validation_report": "Generation failed"}
            
        pipeline = ValidationPipeline(
            workspace_path=self.workspace_path,
            validation_level=self.validation_level,
            llm_generate_files_fn=llm_generate_files_fn
        )
        
        val_result = await pipeline.execute(goal=goal, allow_recovery=True, **kwargs)
        
        return {
            "success": val_result["success"],
            "generated_files": gen_result.get("files", []),
            "validation_passed": val_result["success"],
            "validation_report": val_result["report"],
        }

class OrchestratorIntegration:
    @staticmethod
    def patch_execute_method(orchestrator_class) -> None:
        original_execute = orchestrator_class.execute
        async def execute_with_validation(self, *args, **kwargs) -> Dict[str, Any]:
            result = await original_execute(*args, **kwargs)
            if result.get("type") == "generation" and result.get("workspace_id"):
                workspace_path = Path(f"./outputs/workspaces/{result['workspace_id']}/project")
                hook = ValidatedGenerationHook(workspace_path, result["workspace_id"])
                val_result = await hook.execute_validated_generation(self.llm_generate_files, result.get("goal", ""))
                result["validation"] = val_result
            return result
        orchestrator_class.execute = execute_with_validation

class PostGenerationValidation:
    """Validates outputs after LLM generation before returning to user."""
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.MEDIUM):
        self.validation_level = validation_level
        self.metrics = {
            "total_validations": 0,
            "passed": 0,
            "failed": 0,
            "recovered": 0
        }
    
    async def validate_output(self, output: str, goal: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Validate generated output for quality and correctness.
        
        Returns:
            Dict with validation result, issues found, and recovery suggestions
        """
        self.metrics["total_validations"] += 1
        context = context or {}
        
        issues = []
        # Check for common issues
        if not output or len(output.strip()) < 10:
            issues.append("Output is too short or empty")
        
        if "error" in output.lower() and "traceback" in output.lower():
            issues.append("Output contains error traceback")
        
        # Check if output addresses the goal
        if goal.lower() not in output.lower() and len(goal.split()) > 2:
            # For multi-word goals, check if key terms are present
            goal_words = set(goal.lower().split())
            output_words = set(output.lower().split())
            overlap = len(goal_words & output_words) / len(goal_words)
            if overlap < 0.3:
                issues.append("Output may not address the goal")
        
        passed = len(issues) == 0
        if passed:
            self.metrics["passed"] += 1
        else:
            self.metrics["failed"] += 1
        
        return {
            "passed": passed,
            "issues": issues,
            "recovery_suggested": self._suggest_recovery(issues, goal),
            "metrics": self.metrics.copy()
        }
    
    def _suggest_recovery(self, issues: List[str], goal: str) -> str:
        """Suggest recovery strategies based on issues found."""
        if not issues:
            return ""
        
        suggestions = []
        for issue in issues:
            if "too short" in issue.lower():
                suggestions.append("Regenerate with request for more detailed output")
            elif "traceback" in issue.lower():
                suggestions.append("Fix the error and regenerate")
            elif "address the goal" in issue.lower():
                suggestions.append("Ensure output directly addresses the user's goal")
        
        return "; ".join(suggestions)


class ConditionalValidationStrategy:
    """Applies validation selectively based on context and risk assessment."""
    
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
    
    def should_validate(self, goal: str, context: Dict[str, Any] = None) -> ValidationLevel:
        """
        Determine if and how strictly to validate based on goal content.
        
        Uses LLM-based risk assessment when orchestrator is available.
        Falls back to medium validation by default.
        
        Returns:
            ValidationLevel (LIGHT, MEDIUM, HEAVY, PARANOID)
        """
        goal_lower = goal.lower()
        context = context or {}
        
        # When orchestrator is available, use LLM for risk assessment
        if self.orchestrator and self.orchestrator.config.has_llm_credentials():
            try:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    # We're in an async context but this is a sync method
                    # Schedule the async call on the loop
                    import asyncio as _asyncio
                    future = asyncio.run_coroutine_threadsafe(
                        self._async_risk_assessment(goal),
                        loop
                    )
                    risk = future.result(timeout=5)
                    return risk
            except Exception:
                pass
        
        # Default to medium validation
        return ValidationLevel.MEDIUM
    
    async def _async_risk_assessment(self, goal: str) -> ValidationLevel:
        """Async LLM-based risk assessment for validation level."""
        try:
            resp, _ = await self.orchestrator.invoke(
                prompt=f"Classify the risk level of this goal for validation purposes.\n\n"
                       f"Goal: {goal}\n\n"
                       f"Respond with ONE of: 'paranoid', 'heavy', 'medium', 'light'.\n\n"
                       f"- 'paranoid': Operations that modify/destroy data (delete, format, wipe, deploy to production)\n"
                       f"- 'heavy': Financial/money operations, publishing, releasing\n"
                       f"- 'medium': Standard code generation, file creation, research\n"
                       f"- 'light': Informational queries (explain, describe, summarize, list, demo)",
                system="You classify validation risk levels. Reply with ONE word.",
                temperature=0.1,
                max_tokens=10
            )
            level = resp.strip().lower()
            mapping = {
                "paranoid": ValidationLevel.PARANOID,
                "heavy": ValidationLevel.HEAVY,
                "medium": ValidationLevel.MEDIUM,
                "light": ValidationLevel.LIGHT,
            }
            return mapping.get(level, ValidationLevel.MEDIUM)
        except Exception:
            return ValidationLevel.MEDIUM
    
    def get_validation_rules(self, level: ValidationLevel) -> Dict[str, Any]:
        """Get validation rules for a given validation level."""
        rules = {
            ValidationLevel.LIGHT: {
                "check_syntax": True,
                "check_length": True,
                "check_goal_relevance": False,
                "check_security": False,
                "max_retries": 1
            },
            ValidationLevel.MEDIUM: {
                "check_syntax": True,
                "check_length": True,
                "check_goal_relevance": True,
                "check_security": True,
                "max_retries": 2
            },
            ValidationLevel.HEAVY: {
                "check_syntax": True,
                "check_length": True,
                "check_goal_relevance": True,
                "check_security": True,
                "check_execution": True,
                "max_retries": 3
            },
            ValidationLevel.PARANOID: {
                "check_syntax": True,
                "check_length": True,
                "check_goal_relevance": True,
                "check_security": True,
                "check_execution": True,
                "check_data_integrity": True,
                "max_retries": 5
            }
        }
        return rules.get(level, rules[ValidationLevel.MEDIUM])


class ValidationMetrics:
    """Tracks and reports validation metrics across the system."""
    
    def __init__(self):
        self.metrics = {
            "total_validations": 0,
            "total_passed": 0,
            "total_failed": 0,
            "total_recovered": 0,
            "by_level": {
                "LIGHT": {"total": 0, "passed": 0, "failed": 0},
                "MEDIUM": {"total": 0, "passed": 0, "failed": 0},
                "HEAVY": {"total": 0, "passed": 0, "failed": 0},
                "PARANOID": {"total": 0, "passed": 0, "failed": 0}
            },
            "common_failures": {},
            "avg_validation_time_ms": 0.0,
            "validation_times": []
        }
    
    def record_validation(self, level: ValidationLevel, passed: bool, recovery_successful: bool = False, duration_ms: float = 0.0, failure_reason: str = ""):
        """Record a validation result."""
        level_name = level.name
        self.metrics["total_validations"] += 1
        self.metrics["by_level"][level_name]["total"] += 1
        
        if passed:
            self.metrics["total_passed"] += 1
            self.metrics["by_level"][level_name]["passed"] += 1
        else:
            self.metrics["total_failed"] += 1
            self.metrics["by_level"][level_name]["failed"] += 1
            
            if failure_reason:
                self.metrics["common_failures"][failure_reason] = \
                    self.metrics["common_failures"].get(failure_reason, 0) + 1
        
        if recovery_successful:
            self.metrics["total_recovered"] += 1
        
        if duration_ms > 0:
            self.metrics["validation_times"].append(duration_ms)
            self.metrics["avg_validation_time_ms"] = sum(self.metrics["validation_times"]) / len(self.metrics["validation_times"])
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of validation metrics."""
        total = self.metrics["total_validations"]
        if total == 0:
            return self.metrics.copy()
        
        return {
            "total_validations": total,
            "pass_rate": self.metrics["total_passed"] / total,
            "failure_rate": self.metrics["total_failed"] / total,
            "recovery_rate": self.metrics["total_recovered"] / max(1, self.metrics["total_failed"]),
            "by_level": {
                level: {
                    "total": data["total"],
                    "pass_rate": data["passed"] / max(1, data["total"])
                }
                for level, data in self.metrics["by_level"].items()
            },
            "common_failures": sorted(
                self.metrics["common_failures"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            "avg_validation_time_ms": self.metrics["avg_validation_time_ms"]
        }
    
    def reset(self):
        """Reset all metrics."""
        self.metrics = {
            "total_validations": 0,
            "total_passed": 0,
            "total_failed": 0,
            "total_recovered": 0,
            "by_level": {
                "LIGHT": {"total": 0, "passed": 0, "failed": 0},
                "MEDIUM": {"total": 0, "passed": 0, "failed": 0},
                "HEAVY": {"total": 0, "passed": 0, "failed": 0},
                "PARANOID": {"total": 0, "passed": 0, "failed": 0}
            },
            "common_failures": {},
            "avg_validation_time_ms": 0.0,
            "validation_times": []
        }