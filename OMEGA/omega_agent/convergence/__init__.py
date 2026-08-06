"""OMEGA Convergence Engine — Full AGI-level General Convergence Framework.

Transforms the theoretical framework from AGENTS.md into executable code.
Implements Phase F → 0 → A → B → C → D loop with all validation hardening.
"""

from omega_agent.convergence.types import (
    # Phase identifiers
    ConvergencePhase,
    SolveMode,
    DefectClassification,
    DefectSeverity,
    ObjectiveTag,

    # Core data structures
    DefectRecord,
    BoundaryCase,
    PathTrace,
    ApproachAnalysis,
    ConvergenceMetrics,
    ConvergenceResult,
    ObjectiveFunction,

    # Adversarial & validation
    AdversarialAttack,
    AdversarialResult,
    OracleResult,
    ValidityGateResult,

    # Formalization
    FormalizationResult,
    IntentLabel,
)

from omega_agent.convergence.formalizer import Formalizer
from omega_agent.convergence.scanner import Scanner
from omega_agent.convergence.fixer import Fixer
from omega_agent.convergence.checker import ConvergenceChecker
from omega_agent.convergence.validity_gate import RuntimeValidityGate
from omega_agent.convergence.adversarial import AdversarialRedTeam
from omega_agent.convergence.engine import ConvergenceOrchestrator

__all__ = [
    # Types
    "ConvergencePhase",
    "SolveMode",
    "DefectClassification",
    "DefectSeverity",
    "ObjectiveTag",
    "DefectRecord",
    "BoundaryCase",
    "PathTrace",
    "ApproachAnalysis",
    "ConvergenceMetrics",
    "ConvergenceResult",
    "ObjectiveFunction",
    "AdversarialAttack",
    "AdversarialResult",
    "OracleResult",
    "ValidityGateResult",
    "FormalizationResult",
    "IntentLabel",

    # Modules
    "Formalizer",
    "Scanner",
    "Fixer",
    "ConvergenceChecker",
    "RuntimeValidityGate",
    "AdversarialRedTeam",
    "ConvergenceOrchestrator",
]
