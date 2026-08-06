"""Convergence engine type definitions - all framework data structures."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


# ============================================================================
# PHASE & MODE ENUMS
# ============================================================================

class ConvergencePhase(Enum):
    """Phases of the General Convergence Framework."""
    F = "formalize"             # NL goal -> validated objective function
    ZERO = "define_objective"
    A = "scan"
    B = "fix_construct"
    C = "rescan"
    D = "convergence_check"


class SolveMode(Enum):
    """Operating mode - system vs problem focus."""
    VERIFY = "verify"           # Existing system: scan + fix + converge
    SOLVE = "solve"             # Problem space: enumerate + eliminate + construct
    HYBRID = "hybrid"           # Both: verify existing + solve novel sub-problems


class DefectClassification(Enum):
    """How the defect was classified during scanning."""
    DEFECT = "defect"
    DEAD_CODE = "dead_code"
    CONTRADICTION = "contradiction"
    UNREACHABLE = "unreachable"
    FRAGILE = "fragile"
    DEFECTIVE_APPROACH = "defective_approach"
    UNDEFINED_REGION = "undefined_region"
    MISSING_APPROACH = "missing_approach"
    OBJECTIVE_DEFECT = "objective_defect"


class DefectSeverity(Enum):
    """Severity levels for defects."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ObjectiveTag(Enum):
    """Tagging for objective decision variables."""
    STRUCTURAL = "structural"
    PERFORMANCE = "performance"
    CORRECTNESS = "correctness"
    SAFETY = "safety"
    ROBUSTNESS = "robustness"


class IntentLabel(Enum):
    """Formalizability labels applied by Phase F4."""
    FORMALIZABLE = "formalizable"
    UNDERSPECIFIED = "underspecified"
    NOT_FORMALIZABLE = "not_formalizable"


# ============================================================================
# CORE DATA STRUCTURES
# ============================================================================

@dataclass
class ObjectiveFunction:
    """A formalized objective - the output of Phase F."""
    statement: str
    decision_variables: List[str] = field(default_factory=list)
    direction: str = "maximize"           # "maximize" | "minimize"
    success_criterion: str = ""
    hard_constraints: List[str] = field(default_factory=list)
    soft_constraints: List[str] = field(default_factory=list)
    time_horizon: str = "immediate"
    labeled_inputs: Dict[str, ObjectiveTag] = field(default_factory=dict)
    formalizable: IntentLabel = IntentLabel.UNDERSPECIFIED
    formalization_rationale: str = ""
    walls_touched: List[str] = field(default_factory=list)


@dataclass
class FormalizationResult:
    """Output of Phase F formalize()."""
    success: bool
    goal_text: str = ""
    error: Optional[str] = None
    intent_description: str = ""
    objective: Optional[ObjectiveFunction] = None
    candidates: List[ObjectiveFunction] = field(default_factory=list)
    ambiguities_found: List[str] = field(default_factory=list)
    missing_inputs: List[str] = field(default_factory=list)
    confirmation_required: bool = False


@dataclass
class DefectRecord:
    """A single defect surfaced by the scanner."""
    defect_id: str
    mode: SolveMode
    severity: DefectSeverity
    classification: DefectClassification
    location: str
    current_value: str = ""
    correct_value: str = ""
    boundary_proof: str = ""
    objective_served: str = ""


@dataclass
class BoundaryCase:
    """A boundary case used in convergence testing."""
    case_id: str
    description: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected: Any = None
    actual: Any = None
    passed: bool = False


@dataclass
class PathTrace:
    """A trace of the convergence path through phases."""
    trace_id: str
    phases: List[ConvergencePhase] = field(default_factory=list)
    defects_at_each_phase: Dict[str, List[str]] = field(default_factory=dict)
    timestamp: Optional[datetime] = None


@dataclass
class ApproachAnalysis:
    """Analysis of candidate approaches for a sub-problem."""
    approach_id: str
    description: str
    score: float = 0.0
    rationale: str = ""
    risks: List[str] = field(default_factory=list)


@dataclass
class ConvergenceMetrics:
    """Running metrics for a convergence cycle."""
    total_llm_calls: int = 0
    total_defects_found: int = 0
    total_defects_fixed: int = 0
    boundary_failures: int = 0
    total_boundary_cases: int = 0
    severity_breakdown: Dict[str, int] = field(default_factory=dict)
    convergence_score: float = 0.0
    outer_loops: int = 0
    total_time_seconds: float = 0.0
    adversarial_attacks: int = 0
    adversarial_survived: int = 0


@dataclass
class ConvergenceResult:
    """Output of a full convergence cycle."""
    converged: bool
    remaining_defects: List[DefectRecord] = field(default_factory=list)
    metrics: Optional[ConvergenceMetrics] = None
    rationale: str = ""


# ============================================================================
# ADVERSARIAL & VALIDATION
# ============================================================================

@dataclass
class AdversarialAttack:
    """A single adversarial attack launched at a target."""
    attack_id: str
    name: str
    description: str
    target: str
    attack_vector: Dict[str, Any] = field(default_factory=dict)
    expected_failure: str = ""
    survived: bool = False
    proof: str = ""


@dataclass
class AdversarialResult:
    """Aggregate result of an adversarial red-team run."""
    attacks_launched: int = 0
    attacks_survived: int = 0
    attacks_breached: int = 0
    critical_breaches: int = 0
    new_defects_found: List[DefectRecord] = field(default_factory=list)
    attacks: List[AdversarialAttack] = field(default_factory=list)
    summary: str = ""

    def passed(self) -> bool:
        """A red-team run passes if there were zero critical breaches."""
        return self.critical_breaches == 0


@dataclass
class OracleResult:
    """Result of running an oracle (ground-truth check)."""
    oracle_id: str
    passed: bool = False
    expected: Any = None
    actual: Any = None
    evidence: str = ""


@dataclass
class ValidityGateResult:
    """Aggregate result of the H7-H14 validity gate suite."""
    timestamp: Optional[datetime] = None
    adversarial: Optional[AdversarialResult] = None
    executability_check: Dict[str, Any] = field(default_factory=dict)
    sample_validity: Dict[str, Any] = field(default_factory=dict)
    fail_loud: Dict[str, Any] = field(default_factory=dict)
    non_stationarity: Dict[str, Any] = field(default_factory=dict)
    irreversibility: Dict[str, Any] = field(default_factory=dict)
    passed: bool = False


__all__ = [
    # Enums
    "ConvergencePhase",
    "SolveMode",
    "DefectClassification",
    "DefectSeverity",
    "ObjectiveTag",
    "IntentLabel",
    # Core data structures
    "ObjectiveFunction",
    "FormalizationResult",
    "DefectRecord",
    "BoundaryCase",
    "PathTrace",
    "ApproachAnalysis",
    "ConvergenceMetrics",
    "ConvergenceResult",
    # Adversarial & validation
    "AdversarialAttack",
    "AdversarialResult",
    "OracleResult",
    "ValidityGateResult",
]
