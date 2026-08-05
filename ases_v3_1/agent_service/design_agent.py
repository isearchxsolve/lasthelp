"""
ASES - Designer Agent (v2.6)
=============================
Generates a frontend design specification *before* the coder writes code.
Runs only when the tech stack includes a frontend framework.

Output is a structured design spec (JSON) that gets injected into the
coder's requirements. This turns "build a dashboard" into a task with
explicit layout grids, color tokens, typography scale, and responsive
breakpoints — dramatically reducing visual_reviewer failures downstream.

Integration point: agent_loop.py _dev_pipeline(), between planner_agent
and coder_agent, gated by _has_frontend().

v2.6 additions:
- Vector memory warm-start: retrieves past successful design specs
- Design compliance enforcement: CSS variables MUST be used by coder
- Interaction rule generation for interaction_reviewer.py
- Journal integration: design decisions tracked for penalization
"""

import json
import re
from typing import Dict, Any, Optional

import structlog

from agent_loop import call_model

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Design spec schema (documented for prompt engineering)
# ---------------------------------------------------------------------------

DESIGN_SCHEMA_DOC = """
OUTPUT FORMAT — valid JSON only:
{
  "design_system": {
    "colors": {
      "primary": "#3B82F6",
      "primary_hover": "#2563EB",
      "primary_light": "#DBEAFE",
      "secondary": "#10B981",
      "secondary_hover": "#059669",
      "background": "#FFFFFF",
      "surface": "#F8FAFC",
      "surface_elevated": "#FFFFFF",
      "border": "#E2E8F0",
      "border_focus": "#3B82F6",
      "text_primary": "#0F172A",
      "text_secondary": "#64748B",
      "text_muted": "#94A3B8",
      "text_inverse": "#FFFFFF",
      "error": "#EF4444",
      "error_light": "#FEF2F2",
      "success": "#22C55E",
      "success_light": "#F0FDF4",
      "warning": "#F59E0B",
      "warning_light": "#FFFBEB",
      "info": "#3B82F6",
      "info_light": "#EFF6FF"
    },
    "typography": {
      "font_family": "Inter, system-ui, -apple-system, sans-serif",
      "font_family_mono": "JetBrains Mono, Fira Code, monospace",
      "heading_sizes": {"h1": "clamp(2rem, 5vw, 3rem)", "h2": "clamp(1.5rem, 4vw, 2.25rem)", "h3": "clamp(1.25rem, 3vw, 1.875rem)", "h4": "1.125rem"},
      "body_size": "1rem",
      "body_small": "0.875rem",
      "line_height": 1.6,
      "line_height_tight": 1.25,
      "font_weights": {"normal": 400, "medium": 500, "semibold": 600, "bold": 700}
    },
    "spacing": {
      "base_unit": "0.25rem",
      "scale": [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64]
    },
    "radii": {"none": "0", "sm": "0.125rem", "md": "0.375rem", "lg": "0.5rem", "xl": "0.75rem", "2xl": "1rem", "full": "9999px"},
    "shadows": {
      "sm": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
      "md": "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
      "lg": "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
      "xl": "0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)",
      "inner": "inset 0 2px 4px 0 rgb(0 0 0 / 0.05)"
    },
    "transitions": {
      "fast": "150ms cubic-bezier(0.4, 0, 0.2, 1)",
      "normal": "200ms cubic-bezier(0.4, 0, 0.2, 1)",
      "slow": "300ms cubic-bezier(0.4, 0, 0.2, 1)"
    },
    "z_indices": {"dropdown": 100, "sticky": 200, "fixed": 300, "modal_backdrop": 400, "modal": 500, "popover": 600, "tooltip": 700}
  },
  "layout": {
    "max_width": "1280px",
    "grid_columns": 12,
    "gutter": "1.5rem",
    "container_padding": {"mobile": "1rem", "tablet": "1.5rem", "desktop": "2rem"},
    "page_padding": {"mobile": "1rem", "tablet": "2rem", "desktop": "3rem"},
    "section_spacing": {"mobile": "3rem", "tablet": "4rem", "desktop": "5rem"}
  },
  "responsive_breakpoints": {
    "sm": "640px",
    "md": "768px",
    "lg": "1024px",
    "xl": "1280px",
    "2xl": "1536px"
  },
  "components": [
    {
      "name": "Navbar",
      "purpose": "Global navigation with logo, links, and user menu",
      "layout_rules": ["fixed top", "full-width", "height 64px", "flex row between", "backdrop-blur", "border-bottom"],
      "responsive_behavior": "hamburger menu below lg breakpoint, drawer animation",
      "tokens_used": ["colors.primary", "colors.surface", "typography.h4", "spacing.4", "shadows.md", "transitions.normal"],
      "states": ["default", "scrolled", "mobile_open", "user_menu_open"],
      "interaction_rules": [
        "Mobile menu toggles on hamburger click with slide animation",
        "Active link highlighted with colors.primary and indicator bar",
        "User menu opens on click, closes on outside click or ESC",
        "Logo always links to home",
        "Keyboard navigable: Tab through links, Enter to activate"
      ],
      "accessibility": ["role=navigation", "aria-label=Main navigation", "focus-visible outline"],
      "data_testid": "navbar"
    },
    {
      "name": "Button",
      "purpose": "Primary, secondary, and destructive actions",
      "variants": ["primary", "secondary", "outline", "ghost", "destructive"],
      "sizes": ["sm", "md", "lg"],
      "layout_rules": ["inline-flex", "items-center", "justify-center", "gap-2", "font-medium", "rounded-lg", "transition-colors"],
      "responsive_behavior": "full-width on mobile for primary CTA",
      "tokens_used": ["colors.primary", "colors.primary_hover", "colors.text_inverse", "spacing.3", "spacing.4", "radii.md", "transitions.fast", "shadows.sm"],
      "states": ["default", "hover", "active", "focus-visible", "disabled", "loading"],
      "interaction_rules": [
        "Loading state shows spinner, disables click",
        "Focus-visible shows 2px ring with colors.border_focus and 2px offset",
        "Disabled: opacity-50, cursor-not-allowed, no hover effect"
      ],
      "accessibility": ["type=button", "disabled attribute respected", "aria-busy for loading", "focus-visible"],
      "data_testid": "button"
    }
  ],
  "accessibility": {
    "min_contrast_ratio": 4.5,
    "focus_ring": "2px solid colors.border_focus with 2px offset",
    "reduced_motion": true,
    "skip_link": true,
    "landmarks": ["header", "main", "footer", "nav", "aside"],
    "heading_order": true,
    "image_alt": "required for all non-decorative images",
    "form_labels": "explicit label for every input, aria-describedby for errors"
  },
  "assets_needed": [
    {"type": "icon_set", "source": "lucide-react", "rationale": "lightweight, tree-shakeable, consistent stroke width"},
    {"type": "font", "source": "Inter (Google Fonts)", "rationale": "variable font, excellent readability, free"}
  ],
  "notes_for_coder": [
    "Use CSS Grid for main layout, Flexbox for component internals — never absolute positioning for layout",
    "All interactive elements MUST have visible focus states (focus-visible ring)",
    "MUST use CSS variables from :root block — NO hardcoded hex, rem, or px values in component styles",
    "MUST add data-testid attributes to ALL interactive components for interaction testing",
    "MUST implement reduced-motion media query for all animations/transitions",
    "MUST use semantic HTML5 elements (header, main, footer, nav, section, article, aside)",
    "MUST include proper ARIA attributes for custom components (role, aria-label, aria-expanded, aria-controls)",
    "MUST implement skip-to-content link as first focusable element",
    "MUST ensure heading hierarchy (h1-h6) is logical and sequential",
    "Forms: every input has explicit <label>, errors linked via aria-describedby, required indicated",
    "Images: alt text required for all non-decorative images, empty alt for decorative",
    "Color: never use color alone to convey meaning — combine with icons/text/patterns",
    "Touch targets: minimum 44x44px (48x48px preferred) for all interactive elements",
    "Responsive: mobile-first approach, container queries where supported",
    "Dark mode: design system includes dark mode tokens — implement prefers-color-scheme"
  ]
}
"""


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

async def design_agent(
    task: str,
    tech_stack: str,
    requirements: str,
    plan: Dict[str, Any],
    config,
    execution_id: str,
    db_pool=None,           # NEW: for vector memory warm-start
    tenant_uuid=None,       # NEW: for vector memory lookup
) -> Dict[str, Any]:
    """
    Generates a design specification for frontend tasks.

    v2.6: Now attempts vector memory warm-start before LLM call.
    Falls back to LLM generation if no cached spec or cache miss.

    Returns:
    {
        "has_design": true,
        "spec": { ... },           # parsed JSON design spec
        "css_variables": "...",    # ready-to-paste :root block
        "issues": [...],           # any design concerns / ambiguities
        "tokens": int,
        "from_cache": bool,        # NEW: true if retrieved from vector memory
    }
    """
    # ------------------------------------------------------------------
    # [v2.6] Vector memory warm-start attempt
    # ------------------------------------------------------------------
    cached_spec = None
    if db_pool and tenant_uuid:
        try:
            from vector_memory import retrieve_design_spec_vector
            cached_spec = await retrieve_design_spec_vector(
                db_pool, tenant_uuid, task, tech_stack, execution_id
            )
            if cached_spec:
                logger.info(
                    "design_agent.cache_hit",
                    execution_id=execution_id,
                    components=len(cached_spec.get("components", [])),
                )
        except Exception as e:
            logger.warning("design_agent.cache_lookup_failed", error=str(e))

    if cached_spec:
        css_vars = _generate_css_variables(cached_spec)
        return {
            "has_design": True,
            "spec": cached_spec,
            "css_variables": css_vars,
            "issues": [],
            "tokens": 0,
            "from_cache": True,
        }

    # ------------------------------------------------------------------
    # LLM generation (cache miss or no DB available)
    # ------------------------------------------------------------------
    system_prompt = f"""You are a senior product designer and design-systems engineer.
Your job is to write a complete, implementable design specification for a frontend project.

CRITICAL RULES:
1. Output ONLY valid JSON matching the schema below.
2. Be specific: exact hex codes, rem/px values, and flex/grid rules.
3. Design for the EXACT tech stack provided — don't suggest Tailwind classes if the stack is plain CSS.
4. Include responsive behavior for every component.
5. Flag any missing information that would block implementation.
6. Keep the design system minimal but complete (8 colors max, 1 font family).
7. If the task description is vague, make reasonable assumptions and log them in "issues".
8. EVERY component MUST include a "data_testid" attribute name for interaction testing.
9. EVERY component with states MUST include "interaction_rules" describing user interactions.
10. In "notes_for_coder", explicitly state: "MUST use CSS variables from :root block — no hardcoded values".

{DESIGN_SCHEMA_DOC}"""

    user_prompt = f"""Task: {task}
Tech Stack: {tech_stack}
Requirements: {requirements or "(none provided)"}

Execution Plan Files:
{json.dumps(plan.get("steps", []), indent=2)}

Generate the design specification now."""

    content, inp_tok, out_tok = await call_model(
        model=config.reviewer_model,   # cheap model — deterministic spec work
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=2500,
        execution_id=execution_id,
        call_type="reviewer",   # same TTL as reviewer (12h)
    )

    spec = _parse_design_json(content)

    if not spec:
        logger.warning("design_agent.parse_failed", execution_id=execution_id)
        return {
            "has_design": False,
            "spec": {},
            "css_variables": "",
            "issues": ["Design spec could not be parsed — coder will proceed without it"],
            "tokens": inp_tok + out_tok,
            "from_cache": False,
        }

    css_vars = _generate_css_variables(spec)
    issues = spec.get("issues", []) or spec.get("notes_for_coder", [])

    # Ensure data_testid enforcement note is present
    notes = spec.get("notes_for_coder", [])
    if not any("data-testid" in n.lower() for n in notes):
        notes.append("MUST add data-testid attributes to all interactive components")
    if not any("css variables" in n.lower() for n in notes):
        notes.append("MUST use CSS variables from :root block — no hardcoded hex values")
    # [v3.1] Hydration sentinel — required for deterministic interaction testing.
    # interaction_reviewer.py waits for window.__ASES_READY__ before running any action.
    if not any("__ASES_READY__" in n for n in notes):
        notes.append(
            "MUST set window.__ASES_READY__ = true after root component mounts: "
            "React: useEffect(() => { window.__ASES_READY__ = true; }, [])  "
            "Vue: mounted() { window.__ASES_READY__ = true }  "
            "Vanilla JS: document.addEventListener('DOMContentLoaded', () => { window.__ASES_READY__ = true })"
        )
    spec["notes_for_coder"] = notes

    logger.info(
        "design_agent.complete",
        execution_id=execution_id,
        components=len(spec.get("components", [])),
        colors=len(spec.get("design_system", {}).get("colors", {})),
        issues=len(issues),
    )

    return {
        "has_design": True,
        "spec": spec,
        "css_variables": css_vars,
        "issues": issues,
        "tokens": inp_tok + out_tok,
        "from_cache": False,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_design_json(content: str) -> Optional[Dict[str, Any]]:
    """Extract and validate JSON from model output."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    match = re.search(r'```json\s*(.*?)```', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r'(\{.*\})', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _generate_css_variables(spec: Dict[str, Any]) -> str:
    """Flatten the design system into a CSS :root block."""
    ds = spec.get("design_system", {})
    colors = ds.get("colors", {})
    typography = ds.get("typography", {})
    radii = ds.get("radii", {})
    breakpoints = spec.get("responsive_breakpoints", {})

    lines = [":root {"]
    for k, v in colors.items():
        lines.append(f"  --color-{k.replace('_', '-')}: {v};")
    if "font_family" in typography:
        lines.append(f"  --font-family: {typography['font_family']};")
    for k, v in typography.get("heading_sizes", {}).items():
        lines.append(f"  --font-size-{k}: {v};")
    if "body_size" in typography:
        lines.append(f"  --font-size-body: {typography['body_size']};")
    if "line_height" in typography:
        lines.append(f"  --line-height: {typography['line_height']};")
    for k, v in radii.items():
        lines.append(f"  --radius-{k}: {v};")
    for k, v in breakpoints.items():
        lines.append(f"  --breakpoint-{k}: {v};")
    lines.append("}")

    return "\n".join(lines)


def format_design_for_coder(design_result: Dict[str, Any]) -> str:
    """
    Convert the design agent output into a requirements string chunk
    that the coder agent MUST follow.
    """
    if not design_result.get("has_design"):
        return ""

    spec = design_result["spec"]
    parts = [
        "\n\n=== DESIGN SPECIFICATION (IMPLEMENT EXACTLY — NO DEVIATIONS) ===",
        f"CSS Variables (MUST include in global CSS file):\n{design_result['css_variables']}",
    ]

    layout = spec.get("layout", {})
    if layout:
        parts.append(f"\nLayout: max-width {layout.get('max_width', 'auto')}, "
                     f"{layout.get('grid_columns', 12)}-column grid, "
                     f"gutter {layout.get('gutter', '1rem')}")

    components = spec.get("components", [])
    if components:
        parts.append("\nComponent Specs:")
        for c in components:
            parts.append(f"  [{c['name']}] {c.get('purpose', '')}")
            for rule in c.get("layout_rules", []):
                parts.append(f"    - {rule}")
            if "responsive_behavior" in c:
                parts.append(f"    - Responsive: {c['responsive_behavior']}")
            if "data_testid" in c:
                parts.append(f"    - data-testid=\"{c['data_testid']}\"")
            states = c.get("states", [])
            if states:
                parts.append(f"    - States: {', '.join(states)}")
            interactions = c.get("interaction_rules", [])
            if interactions:
                parts.append("    - Interactions:")
                for ir in interactions:
                    parts.append(f"      • {ir}")

    notes = spec.get("notes_for_coder", [])
    if notes:
        parts.append("\nDesign Notes (MUST follow):")
        for n in notes:
            parts.append(f"  • {n}")
    # [v3.1] Always include the hydration sentinel instruction, even if the spec
    # predates v3.1 and doesn't carry it in notes_for_coder.
    if not any("__ASES_READY__" in n for n in notes):
        parts.append(
            "  • MUST set window.__ASES_READY__ = true after root component mounts "
            "(React: useEffect hook; Vue: mounted(); Vanilla: DOMContentLoaded). "
            "Required for deterministic interaction testing."
        )

    issues = design_result.get("issues", [])
    if issues:
        parts.append("\nDesign Concerns (address if possible):")
        for i in issues:
            parts.append(f"  ⚠ {i}")

    parts.append("=== END DESIGN SPEC ===\n")
    return "\n".join(parts)


async def store_design_spec_vector(
    pool,
    tenant_uuid: str,
    task: str,
    tech_stack: str,
    design_spec: Dict[str, Any],
    execution_id: str,
) -> None:
    """
    Store a successful design spec with its embedding for future warm-start.
    Called after visual review passes.
    """
    try:
        from vector_memory import _embed

        # Embed the task + design system summary
        embed_input = f"Task: {task}\nStack: {tech_stack}\n"
        embed_input += f"Colors: {list(design_spec.get('design_system', {}).get('colors', {}).keys())}\n"
        embed_input += f"Components: {[c['name'] for c in design_spec.get('components', [])]}"

        embedding = await _embed(embed_input)

        if embedding is not None:
            await pool.execute(
                """
                INSERT INTO design_specs
                    (tenant_id, task_context, tech_stack, spec_json, embedding, hit_count)
                VALUES ($1, $2, $3, $4, $5::vector, 1)
                ON CONFLICT (tenant_id, task_context_hash)
                DO UPDATE SET
                    spec_json = EXCLUDED.spec_json,
                    embedding = EXCLUDED.embedding,
                    hit_count = design_specs.hit_count + 1,
                    updated_at = NOW()
                """,
                tenant_uuid,
                task[:200],
                tech_stack,
                json.dumps(design_spec),
                json.dumps(embedding),
            )
            logger.info("design_agent.stored_vector", execution_id=execution_id)
    except Exception as e:
        logger.warning("design_agent.store_failed", error=str(e), execution_id=execution_id)
