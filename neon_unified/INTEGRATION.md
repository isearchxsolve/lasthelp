# Neon Architect v5 — Integration & Gap Closure

## What was delivered

`generation_core.py` is a **full revamp of the generation layer** that implements the blueprint:

| Blueprint point | Implementation |
|-----------------|----------------|
| 1. Upgrade Design + Frontend agents | `DesignTokensAgent`, `PrimitivesAgent`, `FrontendFeaturesAgent`, `UIPolishAgent` |
| 2. Real design system + multi-pass UI | Canonical tokens → primitives → feature screens → polish pass |
| 3. Stronger backend architecture | `ArchitectAgent` + `BackendArchitectedAgent` (API → Service → logic) |
| 4. Deeper mobile | First-class paths for `expo-node` and `flutter-fastapi` with matching token language |

## Orchestrator flow (v5)

```
Scaffold
  → Architect          (ARCHITECTURE.md with real layering)
  → Design Tokens      (canonical high-quality tokens)
  → Primitives         (Button/Input/Card/Badge/EmptyState/…)
  → Backend            (services + thin routers)
  → Frontend Features  (Login + Dashboard + shell, with states)
  → UI Polish          (hierarchy, spacing, focus, motion)
  → Tester
  → Import consistency check
  → Real test run
  → DevOps + VERIFICATION.md
```

## How to plug into existing Neon Architect

In the main agent where `GenerateAppTool` / `GenerationOrchestrator` is constructed:

```python
from generation_core import GenerationOrchestratorV5, detect_stack

# Instead of the old GenerationOrchestrator:
orch = GenerationOrchestratorV5(pool=self.pool, config=self.config)
result = orch.generate(
    description=spec,
    project_dir=project_dir,
    stack=None,  # auto-detect, or force "fastapi-react" | "expo-node" | "flutter-fastapi" | "nextjs-postgres"
    on_progress=on_progress,
)
```

The v5 orchestrator expects the same `ProviderPool` interface already used by Neon Architect (`next_available()`, `record_success()`, `record_failure()`, `model_cfg`, `client`).

## Quality gates already in v5

- AST syntax gate on every Python write
- Path containment (no `..` escapes)
- Cross-file import consistency check for generated Python
- Real pytest execution when tests exist
- Anti-stub philosophy preserved (prompts + validation)
- Loading / empty / error states required in frontend prompts
- Design tokens are the single source of color/spacing

## What this closes vs previous gaps

- **Pixel / slick UI**: Multi-pass + real tokens + primitives + polish pass (major upgrade over single theme file + generic cards)
- **Backend strength**: Explicit service layer, thin routers, domain errors
- **Mobile**: Dedicated Expo and Flutter generation paths with shared visual language
- **Real functionality**: Tests actually run; consistency checked; no success claimed on empty scaffolds

## Still recommended follow-ups (not blockers)

1. Wire visual regression (screenshot → critic) once preview is stable
2. Add more few-shot examples of excellent UIs into the agent prompts
3. Expand `validate_project` static rules for “hard-coded color outside tokens”
4. Phase-specific model overrides (strongest model for design + architecture)

## Files

- `generation_core.py` — complete v5 generation core
- `DESIGN_SYSTEM.md` — blueprint reference
- `INTEGRATION.md` — this file
