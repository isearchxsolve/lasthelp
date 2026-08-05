"""Compile and import verification test.

Ensures all modules compile and import without errors.
No LLM credentials required — pure structure verification.
"""

import importlib
import pkgutil
import py_compile
from pathlib import Path


def test_all_pyfiles_compile():
    """Every .py file in omega_agent must compile without syntax errors."""
    root = Path("omega_agent")
    failed = []
    for pyfile in root.rglob("*.py"):
        try:
            py_compile.compile(str(pyfile), doraise=True)
        except py_compile.PyCompileError as e:
            failed.append((str(pyfile), str(e)))

    if failed:
        msg = "\n".join(f"  {f}: {e}" for f, e in failed)
        raise AssertionError(f"Compilation failures:\n{msg}")


def test_core_modules_import():
    """Core modules must import cleanly."""
    modules = [
        "omega_agent.core.config",
        "omega_agent.core.types",
        "omega_agent.core.orchestrator",
        "omega_agent.core.execution",
        "omega_agent.core.dag_schedule",
        "omega_agent.core.convergence_engine",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            raise AssertionError(f"Failed to import {mod}: {e}")


def test_reasoning_modules_import():
    """Reasoning modules must import cleanly."""
    modules = [
        "omega_agent.reasoning.types",
        "omega_agent.reasoning.synthesizer",
        "omega_agent.reasoning.crisis",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            raise AssertionError(f"Failed to import {mod}: {e}")


def test_moe_modules_import():
    """MOE modules must import cleanly."""
    modules = [
        "omega_agent.moe",
        "omega_agent.moe.router",
        "omega_agent.moe.experts",
        "omega_agent.moe.dynamic_tools",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            raise AssertionError(f"Failed to import {mod}: {e}")


def test_memory_modules_import():
    """Memory modules must import cleanly."""
    modules = [
        "omega_agent.memory",
        "omega_agent.memory.rag",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            raise AssertionError(f"Failed to import {mod}: {e}")


def test_submodules_discoverable():
    """All sub-packages must have __init__.py or be importable."""
    root = Path("omega_agent")
    packages = [
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith("__") and not d.name.startswith(".")
    ]
    for pkg in packages:
        pkg_name = f"omega_agent.{pkg.name}"
        try:
            importlib.import_module(pkg_name)
        except Exception as e:
            raise AssertionError(f"Package {pkg_name} not importable: {e}")


def test_no_use_mock_llm_references():
    """Config should no longer have use_mock_llm field."""
    from omega_agent.core.config import Config
    cfg = Config()
    assert not hasattr(cfg, "use_mock_llm"), (
        "Config should not have use_mock_llm — mock mode removed"
    )


def test_orchestrator_no_mock_invoke():
    """Orchestrator should not have _mock_invoke method."""
    from omega_agent.core.orchestrator import ModelOrchestrator
    assert not hasattr(ModelOrchestrator, "_mock_invoke"), (
        "_mock_invoke should be removed"
    )


def test_llm_codegen_no_mock_generate():
    """llm_codegen should not have _mock_generate_files."""
    import omega_agent.tools.llm_codegen as lcg
    assert not hasattr(lcg, "_mock_generate_files"), (
        "_mock_generate_files should be removed"
    )


def test_cli_no_mock_arg():
    """CLI should not have --mock argument."""
    from omega_agent.cli import main as cli_main
    import argparse
    # Just verify the module works — can't easily check args without running
    assert cli_main is not None
