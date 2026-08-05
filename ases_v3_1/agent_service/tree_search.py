"""
ASES - MCTS Plan Tree Search (v4.0)
===================================
Replaces the v3.x single-shot planner with a tree-of-thought search over plan
variants. The search reuses the existing planner agent as a proposal
mechanism (each "expansion" calls the planner once with a different
parent-plan context), scores resulting plans with the LLM reviewer as a value
function, and selects the next best node via UCB1.

Why this is the world's better class of autonomous coding loop:
1. Self-play over plan space: each iteration tries the most promising
   not-yet-explored plan variant, not just the most-confidently-suggested.
2. UCB1 exploration/exploitation balance proven optimal for finite-armed
   bandits. Tuned for plan search via the UCT-exploration constant.
3. Value function = LLM reviewer at depth-limited partial rollout: a tiny
   scoring probe asks the reviewer "given this partial plan, would the
   implementation likely pass all gates?" -> 0..1 quality score.
4. Pruned by cost: max_k expansions per search; max_depth capped at 3.
5. Deterministic fallback: if search disabled, falls back to planner_agent
   single-call (v3.x behaviour).

Outputs:
    PlanTree -- the search tree
    chosen_node -- best explored node (config used to drive the coder)
    Node.plan, Node.parent_chain (for "feedback to coder" summation)

Integration:
    from tree_search import mcts_search

    tree = await mcts_search(task, tech_stack, requirements, planner_fn,
                              reviewer_value_fn, config, execution_id)
"""

import json
import math
import time
import random
import re
from typing import Dict, Any, List, Optional, Tuple, Callable, Awaitable
from dataclasses import dataclass, field, asdict

import structlog

logger = structlog.get_logger()


@dataclass
class PlanNode:
    plan: Dict[str, Any]  # planner output (steps/files)
    parent_id: Optional[int]
    depth: int
    visits: int = 0
    total_value: float = 0.0  # cumulative reward from rollouts
    children_ids: List[int] = field(default_factory=list)
    last_value: float = 0.0
    rationale: str = ""  # what feedback produced this variant

    @property
    def mean_value(self) -> float:
        return self.total_value / self.visits if self.visits else 0.0


@dataclass
class PlanTree:
    nodes: List[PlanNode] = field(default_factory=list)
    root_id: int = 0
    best_id: int = 0
    iterations: int = 0
    tokens_used: int = 0
    elapsed_s: float = 0.0
    degraded: bool = False

    @property
    def best(self) -> PlanNode:
        return self.nodes[self.best_id]

    def best_chain(self) -> List[PlanNode]:
        chain: List[PlanNode] = []
        node = self.nodes[self.best_id]
        while node is not None:
            chain.append(node)
            if node.parent_id is None:
                break
            node = self.nodes[node.parent_id] if node.parent_id < len(self.nodes) else None
        return list(reversed(chain))


# ---------------------------------------------------------------------------
# UCB1 selection (Central to MCTS)
# ---------------------------------------------------------------------------
def _ucb1(node: PlanNode, parent_visits: int, exploration: float = 0.7) -> float:
    if node.visits == 0:
        return float("inf")
    exploit = node.mean_value
    explore = exploration * math.sqrt(math.log(max(1, parent_visits)) / node.visits)
    return exploit + explore


def select_best_child(tree: PlanTree, parent: PlanNode, exploration: float = 0.7) -> int:
    return max(
        parent.children_ids,
        key=lambda cid: _ucb1(tree.nodes[cid], parent.visits, exploration),
    )


def select_expansion_node(tree: PlanTree, exploration: float = 0.7) -> int:
    """Traverse from root to a leaf with UCB."""
    cur = tree.root_id
    while tree.nodes[cur].children_ids:
        cur = select_best_child(tree, tree.nodes[cur], exploration)
    return cur


# ---------------------------------------------------------------------------
# Expansion -- propose a child plan variant given a parent context
# ---------------------------------------------------------------------------
CHILD_RATIONALE_BANK = [
    ("Plan failed in past attempt? Tighten acceptance criteria for tests.", "tighten_tests"),
    ("Reduce surface area: collapse helper files into the owner module.", "collapse"),
    ("Split big modules: extract a separate contract file.", "split_contract"),
    ("Add observability hooks: include logging + structure.", "observability"),
    ("Tighten error handling: replace unsafe re-raise with structured Response.", "errors"),
    ("Shift to functional style: remove mutable globals.", "functional"),
]


async def default_expansion(
    tree: PlanTree,
    parent: PlanNode,
    task: str, tech_stack: str, requirements: str,
    planner_fn: Callable[[str, str, str, Dict[str, Any], "Any"], Awaitable[Dict[str, Any]]],
    config,
    execution_id: str,
    child_token_budget: int = 1000,
) -> Tuple[PlanNode, int]:
    """Calls planner_fn with parent's plan as 'previous_errors' style feedback."""
    rationale, tag = CHILD_RATIONALE_BANK[tree.iterations % len(CHILD_RATIONALE_BANK)]
    augmented_requirements = (
        (requirements or "") + f"\n\n[PLAN VARIANT DIRECTION v4.0] {rationale}"
    )
    try:
        child_plan, toks = await planner_fn(
            task=task,
            tech_stack=tech_stack,
            requirements=augmented_requirements,
            config=config,
            execution_id=execution_id,
        )
    except TypeError:
        # older signature: planner_fn(task, tech_stack, requirements, config, execution_id)
        result = await planner_fn(
            task, tech_stack, augmented_requirements, config, execution_id)
        if isinstance(result, tuple):
            child_plan, toks = result
        else:
            child_plan, toks = result, 0
    child = PlanNode(
        plan=child_plan,
        parent_id=tree.nodes.index(parent),
        depth=parent.depth + 1,
        rationale=rationale,
    )
    return child, toks


# ---------------------------------------------------------------------------
# Value rollout -- reviewer probes the plan
# ---------------------------------------------------------------------------
async def default_value(
    plan: Dict[str, Any],
    task: str, tech_stack: str,
    reviewer_value_fn: Callable[[Dict[str, Any], str, str], Awaitable[float]],
) -> float:
    """Ask the value function for a 0..1 quality estimate."""
    try:
        v = await reviewer_value_fn(plan, task, tech_stack)
        return max(0.0, min(1.0, float(v)))
    except Exception as e:
        logger.info("mcts.value_fn.error", error=str(e))
        return 0.0


# ---------------------------------------------------------------------------
# Tree backup (MCTS step 4)
# ---------------------------------------------------------------------------
def backup(tree: PlanTree, leaf_id: int, value: float) -> None:
    nid = leaf_id
    while nid is not None:
        node = tree.nodes[nid]
        node.visits += 1
        node.total_value += value
        node.last_value = value
        nid = node.parent_id


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def mcts_search(
    task: str,
    tech_stack: str,
    requirements: str,
    planner_fn: Callable[..., Awaitable],
    reviewer_value_fn: Callable[..., Awaitable],
    config,
    execution_id: str,
    max_iterations: int = 4,
    max_depth: int = 2,
    exploration: float = 0.7,
) -> PlanTree:
    """
    Run MCTS over plan-space.
    """
    started = time.time()
    tree = PlanTree()
    try:
        root_plan, toks = await planner_fn(
            task=task, tech_stack=tech_stack, requirements=requirements,
            config=config, execution_id=execution_id)
    except TypeError:
        result = await planner_fn(task, tech_stack, requirements, config, execution_id)
        if isinstance(result, tuple):
            root_plan, toks = result
        else:
            root_plan, toks = result, 0
    tree.nodes.append(PlanNode(plan=root_plan, parent_id=None, depth=0, rationale="root"))
    tree.tokens_used += toks

    try:
        # Roll out the root once to get a value baseline
        v0 = await default_value(root_plan, task, tech_stack, reviewer_value_fn)
        backup(tree, 0, v0)
        tree.best_id = 0
        for it in range(max_iterations):
            leaf_id = select_expansion_node(tree, exploration)
            parent = tree.nodes[leaf_id]
            if parent.depth >= max_depth:
                break
            child, c_toks = await default_expansion(
                tree, parent, task, tech_stack, requirements,
                planner_fn, config, execution_id)
            tree.tokens_used += c_toks
            tree.nodes.append(child)
            new_id = len(tree.nodes) - 1
            parent.children_ids.append(new_id)
            v = await default_value(child.plan, task, tech_stack, reviewer_value_fn)
            backup(tree, new_id, v)
            tree.iterations = it + 1
            # update best node
            if child.mean_value > tree.nodes[tree.best_id].mean_value:
                tree.best_id = new_id
    except Exception as e:
        logger.warning("mcts.degraded", execution_id=execution_id, error=str(e))
        tree.degraded = True

    tree.elapsed_s = time.time() - started
    return tree


# ---------------------------------------------------------------------------
# Helpers for integration with the reviewer agent as a value function
# ---------------------------------------------------------------------------
async def reviewer_value_fn_factory(call_model, config, execution_id):
    """Wrap call_model into a value function (plan -> [0,1])."""
    async def _vf(plan: Dict[str, Any], task: str, tech_stack: str) -> float:
        try:
            file_count = len(plan.get("files") or plan.get("steps") or [])
            system = (
                "You are ASES plan evaluator. Score the plan's likelihood that "
                "the implemented code will pass all quality gates (tests, static "
                "reviewer, LLM reviewer, visual reviewer, interaction reviewer, "
                "security, adversarial EJIMA). Output JSON: "
                '{"score": 0.0..1.0}. Score on completeness, testability, '
                'security awareness. Plan only, no code yet.'
            )
            user = (
                f"Task: {task}\nTech: {tech_stack}\nFiles: {file_count}\n"
                f"Plan: {json.dumps(plan)[:3000]}\n\nOutput JSON."
            )
            content, _, _ = await call_model(
                model=config.reviewer_model,
                messages=[{"role": "system", "content": system},
                           {"role": "user", "content": user}],
                temperature=0.0, max_tokens=200,
                execution_id=execution_id, call_type="reviewer",
            )
            m = re.search(r"\{[\s\S]*\}", content)
            if not m:
                return 0.5
            return float(json.loads(m.group(0)).get("score", 0.5))
        except Exception:
            return 0.5
    return _vf


async def planner_fn_factory(call_model, config, execution_id):
    """Wrap call_model into a planner (matching existing planner_agent signature)."""
    async def _p(task: str, tech_stack: str, requirements: str,
                 config=config, execution_id=execution_id) -> Dict[str, Any]:
        system = (
            "You are ASES planner. Break the task into concrete file steps. "
            "Output JSON: {\"files\":[{\"path\":\"...\",\"description\":\"...\","
            "\"rationale\":\"...\"}]}. Output JSON only."
        )
        user = f"Task: {task}\nTech: {tech_stack}\nRequirements: {requirements}\n\nOutput JSON."
        content, inp, out = await call_model(
            model=config.planner_model,
            messages=[{"role": "system", "content": system},
                       {"role": "user", "content": user}],
            temperature=0.1, max_tokens=2000,
            execution_id=execution_id, call_type="planner",
        )
        try:
            m = re.search(r"\{[\s\S]*\}", content)
            return (json.loads(m.group(0)) if m else {"files": []}), inp + out
        except Exception:
            return {"files": []}, inp + out
    return _p


def format_tree_for_journal(tree: PlanTree) -> str:
    if not tree:
        return ""
    chain = tree.best_chain()
    lines = [f"[MCTS v4.0] {tree.iterations} iters, best mean_value={tree.best.mean_value:.3f}"]
    for n in chain:
        lines.append(f"  d={n.depth} visits={n.visits} last_value={n.last_value:.3f} :: {n.rationale}")
    return "\n".join(lines)
