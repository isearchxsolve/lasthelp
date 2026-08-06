"""LLM-driven file generation from goal + web evidence — zero templates, zero scaffolds.

ENHANCED: Incorporates Intelligent Token Limit Fallback, Decomposition integration, 
full Auto-Recovery Validation Pipeline, and Safety & Quality Guards.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.tools.workspace import write_files, workspace_project_dir
from omega_agent.safety_guard import (
    apply_safety_and_quality_gates,
    build_rejection_message,
    classify_safety_risk,
)

# Import the newly integrated validation framework
from omega_agent.validation import ValidationPipeline, ValidationLevel

logger = logging.getLogger("omega_agent.tools.llm_codegen")

CODEGEN_DECOMPOSITION_SYSTEM = """You are OMEGA Project Architect. Your job is to decompose a code generation
goal into independent sub-tasks that can be solved iteratively.

For each sub-task, specify:
1. What files to generate
2. Success criteria (what makes these files "done")
3. Dependencies on other sub-tasks
4. The domain hint (config, backend, frontend, tests, docs)

Output ONLY valid JSON — no markdown, no fences:
{
  "sub_tasks": [
    {
      "id": "config",
      "title": "Project Configuration & Manifests",
      "description": "Generate package.json/pyproject.toml, tsconfig, vite config, etc.",
      "file_patterns": ["package.json", "tsconfig.json", "requirements.txt", "*.toml", "*.yaml"],
      "success_criteria": ["All dependency manifests complete and correct", "Build tooling configured"],
      "dependencies": [],
      "domain_hint": "config"
    },
    {
      "id": "backend",
      "title": "Backend / Core Logic",
      "description": "Main application source code, API routes, business logic",
      "file_patterns": ["src/**/*.py", "src/**/*.ts", "server/**/*.ts"],
      "success_criteria": ["Core logic implements the goal", "API endpoints defined", "Error handling present"],
      "dependencies": ["config"],
      "domain_hint": "backend"
    }
  ],
  "post_install_commands": ["npm install", "npm run build"],
  "summary": "One paragraph describing the project architecture and how sub-tasks fit together",
  "project_type": "web-app | cli | library | research | api | automation"
}

RULES:
- Break the project into 2-6 sub-tasks, each producing a coherent group of files
- Sub-tasks should be ordered by dependencies (config first, tests last)
- Each sub-task must have verifiable success criteria
- The summary must explain how all sub-tasks compose into a complete project
- file_patterns help identify which files belong to each sub-task
- Do NOT include files in multiple sub-tasks — each file belongs to exactly one sub-task
"""

CODEGEN_SUB_TASK_SYSTEM = """You are OMEGA Code Generator — generating one specific sub-task of a larger project.

For this sub-task, you will produce files and then self-evaluate them.

Output format — MUST be valid JSON:
{
  "files": [
    {"path": "relative/path/to/file.ext", "content": "complete file content"}
  ],
  "self_evaluation": {
    "criteria_met": ["criteria fully satisfied"],
    "criteria_partial": ["criteria partially met — what's missing"],
    "criteria_not_met": ["criteria not met — why"],
    "overall_assessment": "1-2 sentence quality summary"
  },
  "gaps_identified": ["specific shortcomings to fix in next iteration"],
  "passed": true,
  "summary": "What was generated and why"
}

CRITICAL RULES:
- Every file must be COMPLETE and production-quality — no placeholders, no TODOs, no stubs
- All imports must be correct and consistent with other sub-tasks
- Any file already listed in a prior sub-task must NOT be re-generated here
- self_evaluation must be brutally honest — identify every gap
- passed=true ONLY when ALL success criteria are fully met
- If this sub-task depends on another, assume its outputs exist
- For Python test files, include: import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
- For JS/TS test files, import from the correct relative path
"""

CODEGEN_SYSTEM = """You are OMEGA Code Generator. You produce complete, runnable, production-quality
projects from scratch based solely on the user's goal and the web evidence provided.

OUTPUT FORMAT — MUST be VALID JSON and nothing else (no markdown, no fences):
{
  "files": [
    {"path": "relative/path/to/file.ext", "content": "complete file content as string"}
  ],
  "post_install_commands": ["npm install", "npm run dev"],
  "summary": "one paragraph describing what was built and why each major decision was made"
}

CRITICAL: The response MUST be valid JSON. Do not wrap in markdown code fences. 
Do not include any text before or after the JSON object.

ABSOLUTE RULES — violating any of these is a failure:
- Every framework, library, config, and architectural choice MUST be directly justified by
  the web evidence snippets. If evidence recommends Vite + React for a dashboard, use those.
  If evidence recommends FastAPI + SQLModel for a REST API, use those. Never default to anything.
- The output must be SPECIFIC to the goal. A CRM app, a data pipeline, a CLI tool, a REST API,
  a mobile backend — each looks completely different. Never produce a generic or recycled structure.
- No placeholders. No "// TODO: implement this". No stub functions. Every file must be complete
  and functional enough to run after post_install_commands executes.
- All files needed to run the project must be included: dependency manifests, configs, source
  files, entry points, README. Nothing can be missing.
- Paths must be relative. No ".." segments. Example: "src/App.js", "package.json", "public/index.html"
- The summary must explain WHY you made each major stack decision, grounded in the evidence.
- If the evidence is thin or contradictory, reason through the best approach explicitly in the
  summary and justify the choices made.
- ALWAYS include at least 5 files for a complete project. A CRM requires backend, frontend, database schema, config, and tests.
- YOU MUST INCLUDE TESTS. Generate test files (e.g., test_*.py, *.test.js, *.spec.ts) with comprehensive unit tests for the core logic. A project without tests is considered a failure.
- ALWAYS include a package.json or requirements.txt with exact dependency versions.

README REQUIREMENTS — CRITICAL:
The README.md file MUST be comprehensive and include ALL of the following sections:
1. **Project Title & Description**: Clear title and 2-3 sentence description of what the project does
2. **Features**: Bullet list of key features and capabilities
3. **Prerequisites**: Required software/tools (e.g., Node.js 18+, Python 3.9+, Docker)
4. **Installation**: Step-by-step installation instructions with exact commands:
   - For Node.js: "npm install" or "yarn install"
   - For Python: "pip install -r requirements.txt" or "python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
   - Include any environment variable setup (e.g., .env file creation)
5. **Configuration**: How to configure the project (environment variables, config files)
6. **Running the Application**: Exact commands to start the application:
   - Development: "npm run dev" or "python main.py"
   - Production: "npm run build && npm start" or "gunicorn app:app"
   - Include port numbers and URLs (e.g., "http://localhost:3000")
7. **Usage Examples**: How to use the application with specific examples
8. **Project Structure**: Brief description of the directory structure
9. **Testing**: How to run tests (e.g., "npm test" or "pytest")
10. **Troubleshooting**: Common issues and solutions

The README must be written in clear, professional language with code blocks for all commands.
"""

DECOMPOSITION_SYSTEM = """You are continuing to build a project that was started incompletely.

You've already generated some files. Now generate the ADDITIONAL files needed to complete the project.

Output ONLY valid JSON with this structure:
{
  "files": [
    {"path": "relative/path/to/file.ext", "content": "complete file content"}
  ],
  "summary": "What additional components were added and why"
}

Do NOT repeat files already generated. Focus on missing components.

README REQUIREMENTS — CRITICAL:
If generating or updating a README.md file, it MUST be comprehensive and include ALL of the following sections:
1. **Project Title & Description**: Clear title and 2-3 sentence description of what the project does
2. **Features**: Bullet list of key features and capabilities
3. **Prerequisites**: Required software/tools (e.g., Node.js 18+, Python 3.9+, Docker)
4. **Installation**: Step-by-step installation instructions with exact commands
5. **Configuration**: How to configure the project (environment variables, config files)
6. **Running the Application**: Exact commands to start the application with port numbers and URLs
7. **Usage Examples**: How to use the application with specific examples
8. **Project Structure**: Brief description of the directory structure
9. **Testing**: How to run tests
10. **Troubleshooting**: Common issues and solutions

The README must be written in clear, professional language with code blocks for all commands.
"""


async def llm_generate_files(
    goal: str,
    workspace_id: str = "default",
    output_base: str = "",
    web_context: Optional[Dict[str, Any]] = None,
    project_subdir: str = "project",
    is_recovery_pass: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """Generate a complete project from goal + web evidence via LLM reasoning.
    
    ENHANCED: Detects when model returns incomplete output (fallback pattern), performs
    decomposition to generate remaining files, and executes a full Validation Pipeline
    with auto-recovery to ensure the final code is production-ready.
    """
    
    # IMPORTANT: Keep a single stable workspace project root.
    # If the model wants a top-level folder, it should include it in file paths (e.g. "crm-app/...").
    if project_subdir != "project":
        logger.info("Normalizing project_subdir '%s' -> 'project'", project_subdir)
        project_subdir = "project"

    config = Config()
    # Reuse the app-level singleton config so the active provider (e.g. github) is honoured.
    # Use global config if available to honour the active provider.
    try:
        from omega_agent.core.config import _get_global_config  # type: ignore
        _global_cfg = _get_global_config()
        if _global_cfg is not None:
            config = _global_cfg
    except (ImportError, AttributeError):
        pass  # No global config helper — use the fresh Config() above

    orchestrator = ModelOrchestrator(config)

    # =============================================================================
    # SAFETY GUARD: Block harmful requests using LLM classification
    # =============================================================================
    risk_level, confidence, refusal = await classify_safety_risk(goal, orchestrator)
    if risk_level == "block":
        logger.warning(
            "SAFETY GATE BLOCKED: goal='%s...' confidence=%.2f",
            goal[:80], confidence
        )
        return {
            "success": False,
            "error": refusal,
            "files_written": [],
            "generation_mode": "safety_blocked",
            "blocked_reason": "harmful_content",
            "risk_level": risk_level,
            "risk_confidence": confidence,
        }

    # Get the coding model from config for code generation
    coding_model = getattr(config, 'coding_model', None) or getattr(config, 'openai_model', None)
    
    # If coding_model looks like an OpenRouter model ID (contains "/"), but the main
    # provider is a custom OpenAI endpoint (local vLLM), we need a SEPARATE orchestrator
    # for coding that uses OpenRouter. The local vLLM won't have coding models.
    coding_orchestrator = None
    if (coding_model and "/" in coding_model and 
        config.llm_provider == "openai" and config.openai_base_url and 
        "openrouter" not in config.openai_base_url):
        # Create a temporary config for OpenRouter to use for coding
        from omega_agent.core.config import Config as ConfigClass
        coding_config = ConfigClass(
            llm_provider="openrouter",
            openrouter_api_key=config.openrouter_api_key,
            coding_model=coding_model,
            coding_fast_model=getattr(config, 'coding_fast_model', coding_model),
            # use_mock_llm field removed — no mock mode supported
        )
        coding_orchestrator = ModelOrchestrator(coding_config)
        logger.info("Using separate OpenRouter orchestrator for code generation (model: %s)", coding_model)


    snippets: List[str] = []
    if isinstance(web_context, dict):
        snippets = list(web_context.get("snippets", []))[:20]
    elif isinstance(web_context, str):
        snippets = [web_context[:800]]

    evidence_block = (
        "\n".join(f"[{i+1}] {s}" for i, s in enumerate(snippets))
        if snippets
        else "(no web evidence available — reason from first principles for this goal)"
    )

    if not config.has_llm_credentials():
        logger.warning("No LLM credentials — cannot generate files without reasoning engine")
        
        return {
            "success": False,
            "error": "LLM credentials required for file generation.",
            "files_written": [],
            "generation_mode": "no_credentials",
        }

    active_orchestrator = coding_orchestrator or orchestrator
    is_python_only = (
        kwargs.get("python_only") is True or
        "python only" in goal.lower() or
        "UNIVERSAL SOLVER BREAKTHROUGH" in str(web_context)
    )

    # =============================================================================
    # DECOMPOSE → ITERATE → CONVERGE Pipeline
    # =============================================================================
    files: List[Dict[str, str]] = []
    post_commands: List[str] = []
    summary = ""
    llm_cost = 0.0
    generation_mode = "decompose_iterate_converge"

    if not is_recovery_pass:
        # PHASE 1: DECOMPOSE — Plan the project structure into sub-tasks
        plan = await _decompose_code_project(
            orchestrator=active_orchestrator,
            goal=goal,
            evidence_block=evidence_block,
            is_python_only=is_python_only,
        )
        llm_cost += plan.get("cost", 0.0)

        if plan["success"] and plan["sub_tasks"]:
            # PHASE 2: ITERATE — Solve each sub-task with iterative refinement
            already_generated: List[str] = []

            for sub_task in plan["sub_tasks"]:
                sub_files = await _solve_code_sub_task(
                    orchestrator=active_orchestrator,
                    goal=goal,
                    sub_task=sub_task,
                    evidence_block=evidence_block,
                    already_generated=already_generated,
                    coding_model=coding_model,
                )
                # Deduplicate by path
                for f in sub_files:
                    fp = f.get("path", "")
                    if fp and fp not in already_generated:
                        files.append(f)
                        already_generated.append(fp)

            # PHASE 3: CONVERGE — Check completeness and fill gaps
            converge_result = await _converge_project_outputs(
                orchestrator=active_orchestrator,
                goal=goal,
                all_files=files,
                plan=plan,
                evidence_block=evidence_block,
                coding_model=coding_model,
            )
            files = converge_result["files"]
            summary = converge_result.get("summary") or plan.get("summary", "")
            post_commands = plan.get("post_install_commands", [])

            logger.info(
                "DECOMPOSE→ITERATE→CONVERGE: %d files across %d sub-tasks (converged=%s)",
                len(files), len(plan["sub_tasks"]), converge_result.get("converged", False),
            )

    # If the pipeline produced no files (recovery pass, no sub-tasks, or failure),
    # fall back to original single-shot generation
    if not files:
        generation_mode = "single_shot_fallback"
        logger.info("Falling back to single-shot code generation")
        
        system_prompt = CODEGEN_SYSTEM
        if is_python_only:
            system_prompt += "\n\nCRITICAL OVERRIDE: YOU MUST GENERATE A STRICTLY PYTHON-ONLY PROJECT. DO NOT GENERATE ANY JAVASCRIPT, TYPESCRIPT, REACT, VUE, HTML, CSS, OR PACKAGE.JSON FILES. Ignore any web evidence that suggests using a JS frontend. All UI must be CLI or Python-based (e.g., Streamlit if web is absolutely required). The entire project MUST be Python. CRITICAL: For any Python test files generated, YOU MUST include `import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))` at the very top so they can run directly without ModuleNotFoundError. CRITICAL: If you generate a requirements.txt, each package MUST be on a new line. Never space-separate packages."

        single_shot_prompt = f"""GOAL:
{goal}

WEB EVIDENCE FROM SEARCH (ground every decision in this):
{evidence_block}

Generate a complete, runnable project. Every file must be production-quality and specific
to this goal. Ground all stack and library choices in the evidence above.

REMINDER: Output MUST be valid JSON with "files" array containing objects with "path" and "content" keys.
Do not wrap in markdown. Do not add explanatory text before or after the JSON."""

        try:
            data, llm_cost = await active_orchestrator.invoke_json(
                prompt=single_shot_prompt,
                system=system_prompt,
                temperature=0.2,
                model=coding_model,
            )
        except Exception as e:
            logger.exception("LLM invocation failed during single-shot codegen")
            return {"success": False, "error": f"LLM call failed: {e}", "files_written": []}

        # SAFE EXTRACTION
        raw_files = data.get("files", [])
        if isinstance(raw_files, list):
            for item in raw_files:
                if isinstance(item, dict) and "path" in item:
                    files.append(item)
        elif isinstance(raw_files, dict):
            for k, v in raw_files.items():
                if isinstance(v, str):
                    files.append({"path": k, "content": v})

        post_commands = data.get("post_install_commands", []) if isinstance(data.get("post_install_commands"), list) else []
        summary = data.get("summary", "") if isinstance(data.get("summary"), str) else ""

        # Bridge for flat dict
        if not files and isinstance(data, dict):
            for key, value in data.items():
                if key not in ["summary", "post_install_commands", "raw", "success", "error"] and isinstance(value, str):
                    files.append({"path": key, "content": value})

        if not files and "raw" in data:
            files = _extract_files_from_raw(data["raw"])

        if not files:
            # Final fallback: generate from first principles
            fallback_prompt = f"""GOAL:
{goal}

Generate a complete, runnable project from FIRST PRINCIPLES.

Format your output based on the goal:
- If building an app/service: use a modern stack (React, FastAPI, Click, etc) and include all manifests, source code, and tests.
- If solving a mathematical, algorithmic, or research problem: output comprehensive research reports, LaTeX documents, markdown proofs, and Python algorithmic simulations. Do NOT build a web frontend or backend unless requested.

Generate ALL necessary files including:
1. Package manifests (if code) or bibliography (if research)
2. Source code or research papers (complete, no placeholders)
3. README.md with comprehensive setup, installation, and running instructions
4. Test files or simulation scripts

Output as valid JSON with "files" array containing objects with "path" and "content" keys.
Do not wrap in markdown. Do not add explanatory text before or after the JSON."""

            try:
                fallback_data, fallback_cost = await active_orchestrator.invoke_json(
                    prompt=fallback_prompt,
                    system=CODEGEN_SYSTEM,
                    temperature=0.3,
                    model=coding_model,
                )
                llm_cost += fallback_cost
                raw_files = fallback_data.get("files", [])
                if isinstance(raw_files, list):
                    for item in raw_files:
                        if isinstance(item, dict) and "path" in item:
                            files.append(item)
                elif isinstance(raw_files, dict):
                    for k, v in raw_files.items():
                        if isinstance(v, str):
                            files.append({"path": k, "content": v})
                if files:
                    summary = fallback_data.get("summary", "") if isinstance(fallback_data.get("summary"), str) else summary
                    logger.info(f"Fallback generation succeeded: {len(files)} files")
                else:
                    return {
                        "success": False,
                        "error": "LLM did not produce any files.",
                        "generation_mode": "llm_failed",
                        "llm_cost": llm_cost,
                    }
            except Exception as e:
                logger.exception("Fallback generation failed: %s", e)
                return {
                    "success": False,
                    "error": f"LLM calls failed: {e}",
                    "files_written": [],
                    "generation_mode": "llm_failed",
                }
    # ==============================================================================
    # THE FINAL PYTHON PURGE: Hard Filter for JS/HTML Assets before writing
    # ==============================================================================
    # Convert goal and web_context to safe strings to prevent crash
    safe_goal = str(goal).lower() if goal else ""
    safe_web_ctx = str(web_context).lower() if web_context else ""
    
    is_python_only = (
        kwargs.get("python_only") is True or 
        "python only" in safe_goal or 
        "universal solver" in safe_goal or
        "universal solver" in safe_web_ctx
    )
    
    if is_python_only:
        orig_count = len(files)
        files = [
            f for f in files 
            if isinstance(f, dict) and not str(f.get("path", "")).strip().lower().endswith(
                (".js", ".jsx", ".ts", ".tsx", ".html", ".css", "package.json", "package-lock.json", ".cjs", ".mjs", "jest.config.js")
            )
        ]
        if len(files) < orig_count:
            logger.info(f"Python Purge safely stripped {orig_count - len(files)} Javascript/HTML files before writing.")

    logger.info(f"Successfully extracted {len(files)} files from LLM response")

    # =============================================================================
    # QUALITY GATE: Reject comment-only or non-executable code
    # =============================================================================
    gate_result = await apply_safety_and_quality_gates(goal, files, orchestrator)
    if not gate_result["safe"]:
        rejection_msg = build_rejection_message(gate_result)
        logger.error(
            "QUALITY GATE BLOCKED: %d quality issues, %d package issues for goal='%s...'",
            len(gate_result["quality_issues"]),
            len(gate_result["package_issues"]),
            goal[:80],
        )
        return {
            "success": False,
            "error": rejection_msg,
            "files_written": [],
            "generation_mode": "quality_blocked",
            "quality_issues": gate_result["quality_issues"],
            "package_issues": gate_result["package_issues"],
            "accepted_files": gate_result["accepted_files"],
            "rejected_files": gate_result["rejected_files"],
        }
    
    # Step 1: Write all initial files to disk
    # IMPORTANT: never raise from this tool; return structured failure instead.
    unsafe_paths: List[str] = []
    safe_files: List[Dict[str, str]] = []
    try:
        # Pre-filter unsafe paths before write_files (prevents ValueError from aborting run)
        from omega_agent.tools.workspace import safe_relative_path

        for f in files:
            try:
                p = f.get("path", "")
                safe_relative_path(p)
                safe_files.append(f)
            except Exception:
                unsafe_paths.append(str(f.get("path", ""))[:200])

        if not safe_files:
            return {
                "success": False,
                "error": "LLM produced only unsafe / invalid file paths. Refusing to write files.",
                "unsafe_paths": unsafe_paths[:25],
                "generation_mode": "invalid_paths",
            }

        write_result = await write_files(
            files=safe_files,
            workspace_id=workspace_id,
            output_base=output_base,
            project_subdir=project_subdir,
            goal=goal,
            **{k: v for k, v in kwargs.items() if k == "tenant_id"},
        )
    except Exception as e:
        logger.exception("write_files failed")
        return {
            "success": False,
            "error": f"Failed writing generated files: {e}",
            "unsafe_paths": unsafe_paths[:25],
            "generation_mode": "write_failed",
        }

    # ==============================================================================
    # THE VALIDATION INTEGRATION FIX: Post-Generation Validation & Auto-Recovery
    # ==============================================================================
    logger.info("Starting post-generation validation and auto-recovery sequence")
    validation_passed = None
    validation_report = None

    if files and not is_recovery_pass:
        try:
            workspace_dir = workspace_project_dir(workspace_id, output_base, project_subdir)
            
            # Using MEDIUM level to ensure npm dry-run and builds are validated
            pipeline = ValidationPipeline(
                workspace_path=Path(workspace_dir),
                validation_level=ValidationLevel.MEDIUM,
                llm_generate_files_fn=llm_generate_files,  # Enables AI Auto-Recovery!
                max_recovery_attempts=2
            )
            
            val_result = await pipeline.execute(
                goal=goal, 
                allow_recovery=True,
                workspace_id=workspace_id,
                output_base=output_base,
                web_context=web_context,
                project_subdir=project_subdir,
                is_recovery_pass=True,  # Prevent infinite recursive validation loops!
                **kwargs
            )
            
            validation_passed = val_result["success"]
            validation_report = val_result["report"]
            
            if val_result.get("recovery_successful") and val_result.get("recovered_result"):
                recovered = val_result["recovered_result"]
                write_result["files_written"] = recovered.get("files_written", write_result.get("files_written", []))
                write_result["action_taken"] = recovered.get("action_taken", write_result.get("action_taken", ""))
                llm_cost += recovered.get("llm_cost", 0.0)
                summary += "\n\n[Validation Recovery Applied] The validation framework automatically caught errors and repaired the codebase."
                logger.info("Validation recovery triggered successful regeneration of files.")
        except Exception as e:
            logger.warning(f"Validation framework error: {e}")
            validation_passed = False
            validation_report = f"Validation framework encountered an internal error: {e}"
    elif is_recovery_pass:
        logger.info("Skipping validation gate (currently inside an auto-recovery pass)")
        validation_passed = None
        validation_report = "Validation skipped (recovery pass)."
    else:
        validation_passed = False
        validation_report = "Validation skipped (insufficient files generated)."

    return {
        "success": True,
        **write_result,
        "llm_summary": summary,
        "post_install_commands": post_commands,
        "generation_mode": generation_mode,
        "llm_cost": llm_cost,
        "evidence_snippets_used": len(snippets),
        "action_taken": (
            write_result.get("action_taken", "")
            + f"; generated {len(files)} files via LLM reasoning over {len(snippets)} evidence snippets"
        ),
        "validation_passed": validation_passed,
        "validation_report": validation_report,
    }


async def _decompose_and_generate(
    orchestrator: ModelOrchestrator,
    goal: str,
    initial_files: List[Dict[str, str]],
    evidence_snippets: List[str],
) -> Dict[str, Any]:
    """Decompose incomplete generation and generate remaining files."""
    generated_paths = [f.get("path", "") for f in initial_files]
    logger.info(f"Decomposition: already have {generated_paths}")
    
    project_type = await _infer_project_type(goal, orchestrator)

    decomp_prompt = f"""You've started building: {goal}

Already generated:
{chr(10).join(f'  - {p}' for p in generated_paths)}

Now generate the REMAINING ESSENTIAL files to complete this project.

For a {project_type}, prioritize:
1. Any missing core application files
2. Backend/API infrastructure
3. Frontend structure and entry points
4. Database schema or initialization
5. Configuration files
6. Package manifests and dependency declarations
7. Comprehensive test files to verify the application logic
8. README.md with comprehensive setup, installation, and running instructions (if not already present)

Include complete, production-ready code for each file.

README REQUIREMENTS — CRITICAL:
If generating or updating a README.md file, it MUST be comprehensive and include ALL of the following sections:
1. **Project Title & Description**: Clear title and 2-3 sentence description of what the project does
2. **Features**: Bullet list of key features and capabilities
3. **Prerequisites**: Required software/tools (e.g., Node.js 18+, Python 3.9+, Docker)
4. **Installation**: Step-by-step installation instructions with exact commands
5. **Configuration**: How to configure the project (environment variables, config files)
6. **Running the Application**: Exact commands to start the application with port numbers and URLs
7. **Usage Examples**: How to use the application with specific examples
8. **Project Structure**: Brief description of the directory structure
9. **Testing**: How to run tests
10. **Troubleshooting**: Common issues and solutions

The README must be written in clear, professional language with code blocks for all commands.

Output as JSON with "files" array ONLY:
{{
  "files": [
    {{"path": "filename.ext", "content": "...complete content..."}}
  ]
}}

Do NOT regenerate the files already listed above. Only add new, required files."""

    import asyncio as _asyncio
    max_decomp_retries = 4
    decomp_data, decomp_cost = None, 0.0
    for _attempt in range(1, max_decomp_retries + 1):
        try:
            decomp_data, decomp_cost = await (coding_orchestrator or orchestrator).invoke_json(
                prompt=decomp_prompt,
                system=DECOMPOSITION_SYSTEM,
                temperature=0.2,
                model=coding_model,
            )
            break  # Success
        except Exception as _exc:
            _msg = str(_exc)
            if "429" in _msg and _attempt < max_decomp_retries:
                import re as _re
                _wait = 10
                _m = _re.search(r"wait (\d+) second", _msg)
                if _m:
                    _wait = max(int(_m.group(1)), 5)
                logger.warning("Decomposition 429 (attempt %d/%d), waiting %ds…", _attempt, max_decomp_retries, _wait)
                await _asyncio.sleep(_wait)
            else:
                raise
    if decomp_data is None:
        raise RuntimeError("Decomposition exhausted all retries")

    # SAFE EXTRACTION: Protect against LLM outputting lists of strings
    raw_files = decomp_data.get("files", [])
    additional_files = []

    if isinstance(raw_files, list):
        for item in raw_files:
            if isinstance(item, dict) and "path" in item:
                additional_files.append(item)
    elif isinstance(raw_files, dict):
        for k, v in raw_files.items():
            if isinstance(v, str):
                additional_files.append({"path": k, "content": v})

    # BRIDGE: Extract from flat orchestrator dict if files array is empty
    if not additional_files and isinstance(decomp_data, dict):
        for k, v in decomp_data.items():
            if k not in ["files", "summary", "post_install_commands", "raw", "success", "error"] and isinstance(v, str):
                additional_files.append({"path": k, "content": v})

    decomp_summary = decomp_data.get("summary", "") if isinstance(decomp_data.get("summary"), str) else ""

    unique_additional = [
        f for f in additional_files 
        if isinstance(f, dict) and f.get("path") not in generated_paths
    ]

    if unique_additional:
        logger.info(f"Decomposition generated {len(unique_additional)} new files")
        return {
            "success": True,
            "additional_files": unique_additional,
            "summary": decomp_summary,
            "llm_cost": decomp_cost,
            "post_install_commands": decomp_data.get("post_install_commands", []) if isinstance(decomp_data.get("post_install_commands"), list) else [],
        }
    else:
        logger.warning("Decomposition produced no new files (all were repeats)")
        return {
            "success": True,
            "error": "Decomposition produced only repeated files",
            "additional_files": [],
            "llm_cost": decomp_cost,
        }


# =============================================================================
# DECOMPOSE → ITERATE → CONVERGE: New pipeline for code generation
# =============================================================================

async def _decompose_code_project(
    orchestrator: ModelOrchestrator,
    goal: str,
    evidence_block: str,
    is_python_only: bool = False,
) -> Dict[str, Any]:
    """Decompose a code generation goal into sub-tasks via LLM planning."""
    evidence_part = f"\n\nWEB EVIDENCE:\n{evidence_block[:3000]}" if evidence_block else ""
    python_override = (
        "\n\nCRITICAL: This project MUST be strictly Python-only. No JavaScript, TypeScript, "
        "React, HTML, or CSS files. All UI must be CLI or Python-based (Streamlit if web required)."
        if is_python_only else ""
    )

    prompt = f"""Decompose this code generation goal into sub-tasks:

GOAL: {goal}{evidence_part}{python_override}

Each sub-task should produce a coherent group of related files.
Order by dependencies: config first, tests last.
Every file must belong to exactly one sub-task.

Return ONLY valid JSON with the sub_tasks array."""

    try:
        data, cost = await orchestrator.invoke_json(
            prompt=prompt,
            system=CODEGEN_DECOMPOSITION_SYSTEM,
            temperature=0.3,
            max_tokens=4096,
        )
        if not isinstance(data, dict) or not data.get("sub_tasks"):
            logger.warning("Decomposition returned no sub-tasks, falling back to single-shot")
            return {"success": False, "sub_tasks": [], "cost": cost}

        return {
            "success": True,
            "sub_tasks": data["sub_tasks"],
            "post_install_commands": data.get("post_install_commands", []),
            "summary": data.get("summary", ""),
            "project_type": data.get("project_type", "web-app"),
            "cost": cost,
        }
    except Exception as e:
        logger.warning(f"Code decomposition failed: {e}")
        return {"success": False, "sub_tasks": [], "cost": 0.0}


async def _solve_code_sub_task(
    orchestrator: ModelOrchestrator,
    goal: str,
    sub_task: Dict[str, Any],
    evidence_block: str,
    already_generated: List[str],
    coding_model: Optional[str] = None,
    max_iterations: int = 3,
) -> List[Dict[str, str]]:
    """Solve one code generation sub-task with iterative refinement.

    Each sub-task goes through generate → self-evaluate → refine cycles
    until all success criteria are met or max iterations reached.
    """
    task_id = sub_task.get("id", "unknown")
    task_title = sub_task.get("title", "Untitled")
    task_desc = sub_task.get("description", "")
    criteria = sub_task.get("success_criteria", [])
    deps = sub_task.get("dependencies", [])
    domain_hint = sub_task.get("domain_hint", "general")

    already_str = "\n".join(f"  - {p}" for p in already_generated) if already_generated else "  (none)"
    criteria_str = "\n".join(f"  - {c}" for c in criteria)
    deps_str = ", ".join(deps) if deps else "none"

    system_prompt = CODEGEN_SUB_TASK_SYSTEM + f"""

DOMAIN HINT: {domain_hint}
SUB-TASK ID: {task_id}
SUB-TASK TITLE: {task_title}

SUCCESS CRITERIA:
{criteria_str}

DEPENDENCIES (these sub-tasks must already be complete):
{deps_str}

FILES ALREADY GENERATED BY OTHER SUB-TASKS (do NOT repeat):
{already_str}"""

    all_files: List[Dict[str, str]] = []
    best_files: List[Dict[str, str]] = []
    best_gaps: int = 999
    evidence_part = f"\n\nWEB EVIDENCE:\n{evidence_block}" if evidence_block else ""

    for iteration in range(1, max_iterations + 1):
        prior_context = ""
        if iteration > 1 and best_files:
            prior_context = (
                f"\n\nPREVIOUS ATTEMPT ({iteration-1}): Generated {len(best_files)} files.\n"
                f"Gaps remaining: {best_gaps}.\n"
                f"Address ALL gaps in this iteration."
            )

        prompt = f"""GOAL:
{goal}

SUB-TASK: {task_id} — {task_title}
{task_desc}
{evidence_part}
{prior_context}

Generate the files for this sub-task. Remember:
{criteria_str}

{'This is your FINAL attempt — resolve ALL remaining gaps.' if iteration == max_iterations else f'Iteration {iteration}/{max_iterations} — improve on previous.'}"""

        try:
            data, cost = await orchestrator.invoke_json(
                prompt=prompt,
                system=system_prompt,
                temperature=min(0.7, 0.2 + 0.1 * iteration),
                model=coding_model,
            )
        except Exception as e:
            logger.warning(f"Sub-task {task_id} iteration {iteration} LLM error: {e}")
            continue

        # Extract files
        raw_files = data.get("files", [])
        iteration_files: List[Dict[str, str]] = []
        if isinstance(raw_files, list):
            for item in raw_files:
                if isinstance(item, dict) and "path" in item:
                    iteration_files.append(item)

        # Self-evaluation
        self_eval = data.get("self_evaluation", {})
        gaps = data.get("gaps_identified", [])
        passed = data.get("passed", False)

        logger.info(
            "Sub-task %s iter %d: %d files, %d gaps, passed=%s",
            task_id, iteration, len(iteration_files), len(gaps), passed,
        )

        if iteration_files:
            all_files.extend(iteration_files)
            if len(gaps) < best_gaps:
                best_files = iteration_files
                best_gaps = len(gaps)

        if passed:
            logger.info("Sub-task %s converged after %d iterations", task_id, iteration)
            return iteration_files

    # Return best effort if no passing iteration
    logger.info("Sub-task %s returning best effort (%d files, %d gaps)", task_id, len(best_files), best_gaps)
    return best_files


async def _converge_project_outputs(
    orchestrator: ModelOrchestrator,
    goal: str,
    all_files: List[Dict[str, str]],
    plan: Dict[str, Any],
    evidence_block: str,
    coding_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Convergence step: verify completeness and fill gaps.

    Checks if the combined output from all sub-tasks is complete.
    If not, generates remaining files in one final pass.
    """
    generated_paths = [f.get("path", "") for f in all_files]
    if not generated_paths:
        return {"files": all_files, "summary": plan.get("summary", ""), "needs_convergence": False}

    # Check for critical missing files by project type
    project_type = plan.get("project_type", "web-app")
    missing_indicators = []

    has_readme = any("readme" in p.lower() for p in generated_paths)
    has_tests = any("test" in p.lower() for p in generated_paths)
    has_pkg = any(
        p.endswith(("package.json", "requirements.txt", "pyproject.toml", "setup.py", "Cargo.toml"))
        for p in generated_paths
    )

    if not has_readme:
        missing_indicators.append("README.md (required for every project)")
    if not has_tests:
        missing_indicators.append("Test files (required for quality)")
    if not has_pkg:
        missing_indicators.append("Package manifest (required for reproducibility)")

    if not missing_indicators:
        return {"files": all_files, "summary": plan.get("summary", ""), "needs_convergence": False, "converged": True}

    logger.info("Convergence: missing %d file groups, generating...", len(missing_indicators))

    convergence_prompt = f"""GOAL: {goal}

PROJECT TYPE: {project_type}

ALREADY GENERATED FILES:
{chr(10).join(f'  - {p}' for p in generated_paths[:30])}

MISSING:
{chr(10).join(f'  - {m}' for m in missing_indicators)}

Generate ONLY the missing files listed above.
Each file must be complete and consistent with the already-generated files.
Do NOT regenerate any file already in the list above.

Output valid JSON with a "files" array."""

    convergence_system = """You are OMEGA Convergence Engine. Generate only the MISSING files to complete a project.

Output JSON:
{
  "files": [{"path": "relative/path", "content": "complete content"}],
  "summary": "What was added"
}

Rules:
- Only generate files explicitly listed as missing
- Files must be consistent with existing project structure
- README.md must be comprehensive (title, features, install, config, run, usage, structure, tests, troubleshooting)
- Test files must be runnable with the project's test framework"""

    try:
        data, cost = await orchestrator.invoke_json(
            prompt=convergence_prompt,
            system=convergence_system,
            temperature=0.2,
            model=coding_model,
        )

        raw = data.get("files", [])
        convergence_files: List[Dict[str, str]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "path" in item:
                    path = item["path"]
                    if path not in generated_paths:
                        convergence_files.append(item)

        all_files.extend(convergence_files)
        logger.info("Convergence added %d missing files", len(convergence_files))
        return {
            "files": all_files,
            "summary": data.get("summary", plan.get("summary", "")),
            "needs_convergence": True,
            "converged": True,
            "convergence_files_added": len(convergence_files),
        }
    except Exception as e:
        logger.warning(f"Convergence pass failed: {e}")
        return {"files": all_files, "summary": plan.get("summary", ""), "needs_convergence": False, "converged": False}


async def _infer_project_type(goal: str, orchestrator=None) -> str:
    """Infer project type from goal string using LLM."""
    if not orchestrator or not orchestrator.config.has_llm_credentials():
        # No LLM — extract first significant noun or return generic
        return "software application"
    try:
        response, _ = await orchestrator.invoke(
            prompt=f"Classify the project type for this goal. "
                   f"Reply with ONLY the category name (2-3 words max).\n\nGoal: {goal}",
            system="You classify project types. Reply with ONE short category like "
                   "'REST API', 'web application', 'CLI tool', 'mobile app', "
                   "'data pipeline', 'game', 'library', 'bot', 'dashboard', etc.",
            temperature=0.1,
            max_tokens=15
        )
        result = response.strip().strip('"').strip("'").strip('.')
        return result if len(result) < 50 else "software application"
    except Exception:
        return "software application"


def _extract_files_from_raw(text: str) -> List[Dict[str, str]]:
    """Legacy Robust extraction for raw LLM JSON strings."""
    if not isinstance(text, str): return []
    cleaned = text.strip()
    
    # Safe backtick handling to prevent chat UI parser truncation
    tick3 = chr(96) * 3
    cleaned = re.sub(r"^" + tick3 + r"(?:json)?\s*\n?", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n?" + tick3 + r"\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "files" in data:
            raw_files = data.get("files", [])
            if isinstance(raw_files, list):
                return [f for f in raw_files if isinstance(f, dict) and "path" in f]
            elif isinstance(raw_files, dict):
                return [{"path": k, "content": v} for k, v in raw_files.items() if isinstance(v, str)]
                
        if isinstance(data, list) and all(isinstance(f, dict) and "path" in f for f in data):
            return data
    except json.JSONDecodeError:
        pass

    matches = re.finditer(r'\{[^{}]*"files"[^{}]*\}', cleaned, re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match.group())
            if isinstance(data, dict) and "files" in data and data["files"]:
                raw_files = data["files"]
                if isinstance(raw_files, list):
                    return [f for f in raw_files if isinstance(f, dict) and "path" in f]
        except json.JSONDecodeError: continue

    return []


def register_llm_codegen_tools(registry) -> None:
    registry.register(
        "llm_generate_files",
        (
            "ACT: Generate a complete, runnable project from scratch using LLM reasoning "
            "over web evidence. Zero templates — every file is goal-specific. "
            "Automatically handles token limits via Intelligent Decomposition. "
            "Runs a post-generation validation pipeline to repair broken code."
        ),
        llm_generate_files,
        args={
            "goal": "string — full user goal description",
            "workspace_id": "string — workspace folder name",
            "output_base": "string — optional workspace root path",
            "web_context": "object — {snippets: [...]} from prior web_search tasks",
            "project_subdir": "string — subdirectory within workspace (default: project)",
        }
    )