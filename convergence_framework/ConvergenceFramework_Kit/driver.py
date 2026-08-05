#!/usr/bin/env python3
"""
Convergence Driver - reference harness for the Feasibility-First Convergence Framework.

WHY THIS EXISTS
---------------
A single LLM call is stateless and token-bounded, so "iterate until convergence"
is IMPOSSIBLE inside one call. This driver externalizes the loop and the memory:
each call does ONE bounded convergence step; the driver persists state and
re-invokes until an EXTERNAL, deterministic check says the objective is met.

This is the "driver" that a free coding agent (Antigravity, OpenHands, Cline,
Aider, ...) embodies. Use it as the skeleton: wire `call_llm`, `scan`, and
`verify` to your model/agent and your project.

DISCIPLINE (do not violate)
---------------------------
- Reason to convergence FIRST; use runtime only to CONFIRM, never to DISCOVER.
- The LLM's self-reported "done" is NEVER the oracle. `scan`/`verify` are.
- Monotonic progress or escalate: never loop forever.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

STATE_PATH = os.environ.get("DRIVER_STATE", "/data/driver_state.json")
MAX_ITERS = int(os.environ.get("DRIVER_MAX_ITERS", "200"))


@dataclass
class Part:
    """One node of the Phase S build manifest."""
    id: str
    depends_on: list[str] = field(default_factory=list)
    contract: str = ""          # frozen interface / acceptance contract
    acceptance: str = ""        # human-readable acceptance predicate
    status: str = "OPEN"        # OPEN | DONE


@dataclass
class State:
    objective: str                       # the scalar objective f, in words
    predicate: str                       # verification predicate V, in words
    manifest: list[Part] = field(default_factory=list)
    defect_ledger: list[str] = field(default_factory=list)
    code: str = ""
    iteration: int = 0
    last_defect_count: Optional[int] = None

    def save(self, path: str = STATE_PATH) -> None:
        with open(path, "w") as fh:
            json.dump({**asdict(self)}, fh, indent=2)

    @classmethod
    def load(cls, path: str = STATE_PATH) -> "State":
        with open(path) as fh:
            raw = json.load(fh)
        raw["manifest"] = [Part(**p) for p in raw.get("manifest", [])]
        return cls(**raw)


# --- Wire these three to your model / agent / project ------------------------

def call_llm(system_prompt: str, state: State, part: Optional[Part]) -> str:
    """ONE bounded convergence step. Return updated code for `part`.
    Replace with your model/agent call. Keep the step bounded: converge ONE
    part per call, depth-first, and emit a fresh OPEN-DEFECTS ledger."""
    raise NotImplementedError("Wire call_llm to your LLM / coding agent.")


def scan(state: State, part: Optional[Part]) -> list[str]:
    """DETERMINISTIC defect scan. Reason/lint/type-check against the contract.
    Return the list of OPEN defects. THIS - not the LLM - is the oracle."""
    raise NotImplementedError("Wire scan to your static checks / analyzers.")


def verify(state: State) -> bool:
    """The ONE confirmatory pass. Run the single end-to-end integration test
    (or compile / render-vs-Figma check) AFTER analytic convergence.
    Runtime CONFIRMS here; it must never be the debugging loop."""
    raise NotImplementedError("Wire verify to your single integration test.")


# --- Phase S: scaffold-first ordering ---------------------------------------

def topological_order(manifest: list[Part]) -> list[Part]:
    """types/contracts -> leaf modules -> integrators."""
    done: set[str] = set()
    ordered: list[Part] = []
    remaining = list(manifest)
    while remaining:
        progressed = False
        for p in list(remaining):
            if all(dep in done for dep in p.depends_on):
                ordered.append(p)
                done.add(p.id)
                remaining.remove(p)
                progressed = True
        if not progressed:
            raise RuntimeError(f"Cyclic/unresolvable dependencies: {[p.id for p in remaining]}")
    return ordered


def next_open_part(state: State) -> Optional[Part]:
    for p in topological_order(state.manifest):
        if p.status != "DONE":
            return p
    return None


# --- The convergence loop ----------------------------------------------------

def run(system_prompt: str, state: State) -> bool:
    """Drive the framework to convergence. Returns True on success."""
    # S0: converge the scaffold FIRST (a wrong scaffold mass-produces defects).
    topological_order(state.manifest)  # raises if the skeleton is inconsistent

    while state.iteration < MAX_ITERS:
        state.iteration += 1
        part = next_open_part(state)  # None => integrate-and-verify phase

        state.code = call_llm(system_prompt, state, part)  # one bounded step
        state.defect_ledger = scan(state, part)            # controller decides
        state.save()

        open_count = len(state.defect_ledger)

        # Monotonic-progress guard: never loop forever.
        if state.last_defect_count is not None and open_count >= state.last_defect_count:
            print(f"[iter {state.iteration}] no progress ({open_count} defects) -> escalate / change strategy")
            return False
        state.last_defect_count = open_count

        if open_count == 0:
            if part is not None:
                part.status = "DONE"          # this part converged; move on
                state.last_defect_count = None
                state.save()
                continue
            # No open parts and no defects -> run the ONE confirmatory pass.
            if verify(state):
                print(f"[iter {state.iteration}] CONVERGED and verified.")
                return True
            print(f"[iter {state.iteration}] integration test failed -> reopening.")
            state.last_defect_count = None

    print(f"Hit MAX_ITERS={MAX_ITERS} without convergence -> escalate.")
    return False


if __name__ == "__main__":
    # Example skeleton. Fill the manifest from Phase S (S1) and wire the three
    # functions above, then: python3 /data/driver.py
    demo = State(
        objective="Build the app to spec",
        predicate="All acceptance predicates pass; single integration test green",
        manifest=[
            Part(id="types", contract="shared types", acceptance="0 type errors"),
            Part(id="db-schema", depends_on=["types"], contract="schema.sql", acceptance="migrations apply"),
            Part(id="auth-service", depends_on=["types", "db-schema"],
                 contract="POST /login -> {token}; verify(token) -> userId",
                 acceptance="all contract endpoints pass; 0 type errors"),
        ],
    )
    demo.save()
    print("Wrote demo manifest to", STATE_PATH,
          "- wire call_llm/scan/verify, then run().")
