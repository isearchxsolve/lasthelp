#!/usr/bin/env python3
"""
Neon Architect v5 — Generation Core
===================================
Revamped generation layer that closes the quality gaps:

1. Design-system-first + multi-pass UI generation (slick, higher visual quality)
2. Strong layered architecture defaults for backends
3. Deeper Expo + Flutter support to near-web parity
4. Real polish, states, and consistency gates

This module is designed to replace / sit on top of the previous GenerationOrchestrator
and SpecializedAgent layer while reusing an existing ProviderPool + config.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Stack & Surface Contracts
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED_STACKS = (
    "fastapi-react",      # FastAPI + React/Vite + Tailwind/shadcn-style
    "nextjs-postgres",    # Next.js App Router + Postgres
    "expo-node",          # Expo (React Native) + Node API
    "flutter-fastapi",    # Flutter + FastAPI
)

def detect_stack(description: str) -> str:
    d = (description or "").lower()
    if any(k in d for k in ("flutter", "dart")):
        return "flutter-fastapi"
    if any(k in d for k in ("expo", "react native", "react-native", "ios app", "android app", "mobile app")):
        return "expo-node"
    if any(k in d for k in ("next.js", "nextjs", "app router")):
        return "nextjs-postgres"
    return "fastapi-react"


# Domain keyword -> (slug used in file/route names, PascalCase entity name).
# Order matters: first match wins, so more specific domains should sit above
# generic ones if they could ever overlap.
_ENTITY_KEYWORDS: List[Tuple[Tuple[str, ...], str, str]] = [
    (("habit", "habits"), "habit", "Habit"),
    (("task", "tasks", "todo", "todos", "to-do"), "task", "Task"),
    (("note", "notes"), "note", "Note"),
    (("recipe", "recipes"), "recipe", "Recipe"),
    (("expense", "expenses", "budget"), "expense", "Expense"),
    (("workout", "workouts", "exercise"), "workout", "Workout"),
    (("book", "books", "library"), "book", "Book"),
    (("event", "events", "booking", "bookings"), "event", "Event"),
    (("product", "products", "inventory"), "product", "Product"),
    (("order", "orders"), "order", "Order"),
    (("ticket", "tickets", "support"), "ticket", "Ticket"),
    (("article", "articles", "post", "posts", "blog"), "post", "Post"),
    (("project", "projects"), "project", "Project"),
]


def derive_primary_entity(description: str) -> Tuple[str, str]:
    """Best-effort guess at the app's core domain entity from the spec, e.g.
    ('habit', 'Habit') for a habit tracker. This exists because every
    downstream agent (backend service/router names, tester prompts, some
    frontend prompts) previously hardcoded 'project'/'Project' regardless
    of what the app actually was — stack_surface() computed a per-stack
    contract but nothing about the ACTUAL APP, so a habit tracker still
    got a ProjectService and a /api/projects router. Not a full NLP
    pipeline, just a keyword match against common app domains; falls back
    to 'project'/'Project' honestly (as a real fallback, not a silent
    universal default) when nothing matches.
    """
    d = (description or "").lower()
    for keywords, slug, pascal in _ENTITY_KEYWORDS:
        if any(k in d for k in keywords):
            return slug, pascal
    return "project", "Project"


def stack_surface(stack: str, description: str = "") -> Dict[str, Any]:
    """Authoritative contract for what the stack is allowed to expose.

    `description` drives the domain entity (defaults to a generic
    'project' contract when omitted, for backward compatibility with any
    caller that hasn't been updated to pass it — but every in-repo caller
    now does).
    """
    entity_slug, entity_pascal = derive_primary_entity(description)
    base = {
        "fastapi-react": {
            "endpoints": f"/api/health, /api/auth/register, /api/auth/login, /api/{entity_slug}s",
            "domain": ["health", "auth", entity_slug],
            "frontend_entities": [entity_pascal, "User"],
            "ui_lib": "tailwind-shadcn",
        },
        "nextjs-postgres": {
            "endpoints": f"/api/health, /api/auth/*, /api/{entity_slug}s",
            "domain": ["health", "auth", entity_slug],
            "frontend_entities": [entity_pascal, "User"],
            "ui_lib": "tailwind-shadcn",
        },
        "expo-node": {
            "endpoints": f"/api/health, /api/auth/register, /api/auth/login, /api/{entity_slug}s",
            "domain": ["health", "auth", entity_slug],
            "frontend_entities": [entity_pascal, "User"],
            "ui_lib": "nativewind",
        },
        "flutter-fastapi": {
            "endpoints": f"/api/health, /api/auth/register, /api/auth/login, /api/{entity_slug}s",
            "domain": ["health", "auth", entity_slug],
            "frontend_entities": [entity_pascal, "User"],
            "ui_lib": "material3-tokens",
        },
    }
    result = base.get(stack, base["fastapi-react"])
    result["entity_slug"] = entity_slug
    result["entity_pascal"] = entity_pascal
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Design Tokens (canonical)
# ─────────────────────────────────────────────────────────────────────────────

WEB_TOKENS_TS = '''\
/**
 * Design tokens — single source of truth.
 * Do not hard-code colors/spacing outside these tokens.
 */
export const tokens = {
  colors: {
    background: "#0B0F19",
    surface: "#111827",
    surfaceElevated: "#1F2937",
    border: "#374151",
    borderSubtle: "#1F2937",
    primary: "#38BDF8",
    primaryHover: "#7DD3FC",
    primaryMuted: "rgba(56, 189, 248, 0.15)",
    accent: "#A78BFA",
    success: "#34D399",
    warning: "#FBBF24",
    danger: "#FB7185",
    text: "#F8FAFC",
    textMuted: "#94A3B8",
    textSubtle: "#64748B",
  },
  radius: {
    sm: "6px",
    md: "10px",
    lg: "14px",
    xl: "20px",
    full: "9999px",
  },
  spacing: {
    1: "4px",
    2: "8px",
    3: "12px",
    4: "16px",
    5: "20px",
    6: "24px",
    8: "32px",
    10: "40px",
    12: "48px",
  },
  typography: {
    fontSans: "Inter, ui-sans-serif, system-ui, -apple-system, sans-serif",
    display: "2.25rem",
    h1: "1.875rem",
    h2: "1.5rem",
    h3: "1.25rem",
    body: "0.9375rem",
    caption: "0.8125rem",
  },
  shadow: {
    sm: "0 1px 2px rgba(0,0,0,0.4)",
    md: "0 4px 12px rgba(0,0,0,0.45)",
    lg: "0 12px 32px rgba(0,0,0,0.5)",
  },
  motion: {
    fast: "150ms",
    normal: "220ms",
    slow: "320ms",
    ease: "cubic-bezier(0.4, 0, 0.2, 1)",
  },
} as const;

export type Tokens = typeof tokens;
'''

FLUTTER_TOKENS_DART = '''\
import 'package:flutter/material.dart';

class AppTokens {
  static const Color background = Color(0xFF0B0F19);
  static const Color surface = Color(0xFF111827);
  static const Color surfaceElevated = Color(0xFF1F2937);
  static const Color border = Color(0xFF374151);
  static const Color primary = Color(0xFF38BDF8);
  static const Color primaryHover = Color(0xFF7DD3FC);
  static const Color accent = Color(0xFFA78BFA);
  static const Color success = Color(0xFF34D399);
  static const Color warning = Color(0xFFFBBF24);
  static const Color danger = Color(0xFFFB7185);
  static const Color text = Color(0xFFF8FAFC);
  static const Color textMuted = Color(0xFF94A3B8);
  static const Color textSubtle = Color(0xFF64748B);

  static const double radiusSm = 6;
  static const double radiusMd = 10;
  static const double radiusLg = 14;
  static const double radiusXl = 20;

  static const double space1 = 4;
  static const double space2 = 8;
  static const double space3 = 12;
  static const double space4 = 16;
  static const double space6 = 24;
  static const double space8 = 32;

  static ThemeData get darkTheme {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: background,
      colorScheme: const ColorScheme.dark(
        primary: primary,
        secondary: accent,
        surface: surface,
        error: danger,
        onPrimary: background,
        onSurface: text,
      ),
      cardTheme: CardTheme(
        color: surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusLg),
          side: const BorderSide(color: border),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceElevated,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: const BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: const BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: const BorderSide(color: primary, width: 1.5),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: background,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radiusMd),
          ),
        ),
      ),
    );
  }
}
'''

# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestRunResult:
    ran: bool
    passed: bool
    output: str = ""


@dataclass
class GenerationResult:
    success: bool
    project_dir: Path
    stack: str
    files_created: List[str] = field(default_factory=list)
    files_generated: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    preview_url: Optional[str] = None
    test_output: Optional[TestRunResult] = None
    qa_output: Optional[Any] = None
    repair_rounds: int = 0


ProgressCb = Optional[Callable[[str, str], None]]


# ─────────────────────────────────────────────────────────────────────────────
# Base agent
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

# Safe import of openai for error handling
try:
    import openai
    OPENAI_ERRORS = (
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,
        openai.RateLimitError,
        openai.APIStatusError,
    )
except ImportError:
    openai = None  # type: ignore
    OPENAI_ERRORS = (Exception,)

class GenAgent:
    """Thin wrapper around a ProviderPool for specialized generation."""

    role: str = "agent"
    system: str = "You are a senior engineer. Output only valid source code. No markdown fences. No stubs."

    def __init__(self, pool: Any, config: Dict[str, Any]):
        self.pool = pool
        self.config = config

    def _call(self, user: str, system: Optional[str] = None, max_tokens: int = 8192) -> str:
        """
        Resilient NIM call with proper 429/rate-limit handling.
        
        Key behaviors:
        * Treats HTTP 429 / RateLimitError specially with extended cooldown
        * Uses config.post_429_backoff (default 45 sec+) for 429 errors
        * Calls pool.propagate_shared_cooldown when available to protect sibling providers
        * Calls provider.record_success() (which commits bucket) on success
        * Does NOT use weak generic ten-second cooldown for every error type
        """
        messages = [
            {"role": "system", "content": system or self.system},
            {"role": "user", "content": user},
        ]
        
        if not hasattr(self.pool, "next_available"):
            raise RuntimeError(f"[{self.role}] no usable pool (missing next_available)")
        
        post_429_backoff = float(self.config.get("post_429_backoff", 45.0) or 45.0)
        
        for attempt in range(6):
            provider = None
            for _ in range(20):
                provider = self.pool.next_available()
                if provider:
                    break
                time.sleep(1.5)
            
            if not provider:
                raise RuntimeError(f"[{self.role}] no provider available after 30s")
            
            try:
                model_cfg = provider.model_cfg
                payload = {
                    "model": model_cfg["id"],
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "stream": False,
                }
                if model_cfg.get("temperature") is not None:
                    payload["temperature"] = model_cfg["temperature"]
                if model_cfg.get("top_p") is not None:
                    payload["top_p"] = model_cfg["top_p"]
                
                resp = provider.client.chat.completions.create(**payload)
                
                if not getattr(resp, "choices", None):
                    provider.record_failure(cooldown=8.0)
                    continue
                
                content = (resp.choices[0].message.content or "").strip()
                provider.record_success()
                return _strip_fences(content)
            
            except OPENAI_ERRORS as e:
                err_str = str(e).lower()
                is_rate_limit = (
                    "429" in err_str
                    or "rate limit" in err_str
                    or "ratelimit" in err_str
                    or "resourceexhausted" in err_str
                    or "too many requests" in err_str
                    or isinstance(e, getattr(openai, "RateLimitError", Exception))
                )
                
                if is_rate_limit:
                    provider.record_failure(cooldown=post_429_backoff)
                    if hasattr(self.pool, "propagate_shared_cooldown"):
                        try:
                            self.pool.propagate_shared_cooldown(provider, post_429_backoff)
                        except Exception:
                            pass
                    time.sleep(5.0 * (attempt + 1))
                elif "404" in err_str or "410" in err_str or "not found" in err_str:
                    provider.record_failure(permanent=True)
                    time.sleep(2.0)
                else:
                    provider.record_failure(cooldown=15.0)
                    time.sleep(2.0 + attempt)
            except (IndexError, AttributeError, KeyError, RuntimeError) as e:
                provider.record_failure(cooldown=10.0)
                time.sleep(2.0 + attempt)
            except Exception as e:
                provider.record_failure(cooldown=15.0)
                time.sleep(2.0 + attempt)
        
        raise RuntimeError(f"[{self.role}] All NIM attempts exhausted after 6 retries")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _safe_write(project_dir: Path, rel: str, content: str, errors: List[str]) -> bool:
    rel = rel.strip().lstrip("/\\")
    if not rel or ".." in rel.split("/"):
        errors.append(f"rejected path: {rel}")
        return False
    content = _strip_fences(content)
    if rel.endswith((".py", ".pyi")):
        try:
            ast.parse(content)
        except SyntaxError as e:
            errors.append(f"invalid Python {rel}: {e.msg} (line {e.lineno})")
            return False
    dest = (project_dir / rel).resolve()
    try:
        dest.relative_to(project_dir.resolve())
    except ValueError:
        errors.append(f"path escape: {rel}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Specialized Agents (v5)
# ─────────────────────────────────────────────────────────────────────────────

class ArchitectAgent(GenAgent):
    role = "architect"
    system = (
        "You are a principal software architect. "
        "Produce clear, production-minded architecture. "
        "Prefer layered design: API → Service → Repository/Domain. "
        "Only introduce distributed patterns when the problem clearly needs them. "
        "Output pure Markdown."
    )

    def run(self, ctx: Dict[str, Any]) -> Dict[str, str]:
        surface = stack_surface(ctx["stack"], ctx.get("description", ""))
        prompt = f"""
Project: {ctx['project_name']}
Description: {ctx['description']}
Stack: {ctx['stack']}
Allowed API surface: {surface['endpoints']}
Domain capabilities: {', '.join(surface['domain'])}

Write ARCHITECTURE.md with these exact sections:

## Overview
## Components
## Data Flow
## Tech Stack
## Layering
(API / Service / Repository or equivalent — be concrete about module names)
## Auth & Security
## Data Model
## Error Handling
## Background Work
(when needed; otherwise say "none required")
## Scalability Notes
## Failure Modes

Be specific. Name real modules and files. No interface stubs. No vague "services will handle X".
"""
        out = self._call(prompt, max_tokens=4500)
        return {"ARCHITECTURE.md": out}


class DesignTokensAgent(GenAgent):
    role = "design_tokens"
    system = "You output only valid source code for design tokens. No markdown."

    def run(self, ctx: Dict[str, Any]) -> Dict[str, str]:
        stack = ctx["stack"]
        if stack in ("fastapi-react", "nextjs-postgres"):
            # Use canonical high-quality tokens; model may refine later if needed
            path = "frontend/src/theme/tokens.ts" if stack == "fastapi-react" else "lib/theme/tokens.ts"
            return {path: WEB_TOKENS_TS}
        if stack == "expo-node":
            # NativeWind-friendly JS tokens
            return {"src/theme/tokens.ts": WEB_TOKENS_TS.replace("as const", "")}
        if stack == "flutter-fastapi":
            return {"lib/theme/tokens.dart": FLUTTER_TOKENS_DART}
        return {}


class PrimitivesAgent(GenAgent):
    role = "primitives"
    system = (
        "You are a senior UI engineer. Output only valid source code. "
        "Build accessible, polished primitive components on top of the design tokens. "
        "Every interactive component must have hover/focus/disabled styles. "
        "No stubs."
    )

    def run(self, ctx: Dict[str, Any]) -> Dict[str, str]:
        stack = ctx["stack"]
        tokens_hint = ctx.get("tokens_path", "theme/tokens")
        results: Dict[str, str] = {}

        if stack in ("fastapi-react", "nextjs-postgres"):
            base = "frontend/src/components/ui" if stack == "fastapi-react" else "components/ui"
            prompt = f"""
Project: {ctx['project_name']}
Stack: {stack}
Tokens live at: {tokens_hint}

Write a single file {base}/index.tsx that exports polished primitives:
- Button (variants: primary, secondary, ghost, danger; sizes sm/md/lg)
- Input
- Card
- Badge
- Spinner
- EmptyState (icon + title + description + optional action)

Rules:
- Import tokens from the tokens module
- Use Tailwind-style class names OR inline styles derived from tokens
- Include focus-visible rings
- Include disabled states
- TypeScript
- No markdown fences
- Complete, working code only
"""
            results[f"{base}/index.tsx"] = self._call(prompt, max_tokens=7000)

        elif stack == "expo-node":
            prompt = f"""
Project: {ctx['project_name']}
Write src/components/ui.tsx — React Native primitives using the tokens:
Button, Input, Card, Badge, EmptyState.
Use StyleSheet and the token colors.
Include disabled + loading states for Button.
TypeScript. Complete code only.
"""
            results["src/components/ui.tsx"] = self._call(prompt, max_tokens=6000)

        elif stack == "flutter-fastapi":
            prompt = f"""
Project: {ctx['project_name']}
Write lib/widgets/ui.dart — Flutter primitives on AppTokens:
AppButton, AppTextField, AppCard, AppBadge, AppEmptyState.
Use Material 3 + AppTokens.
Complete Dart code only.
"""
            results["lib/widgets/ui.dart"] = self._call(prompt, max_tokens=6000)

        return results


class BackendArchitectedAgent(GenAgent):
    role = "backend"
    system = (
        "You are a senior backend engineer. "
        "Produce real layered code: routers stay thin, business logic lives in services. "
        "No stubs, no TODO, no pass-only functions. Output only source code."
    )

    def run(self, ctx: Dict[str, Any]) -> Dict[str, str]:
        stack = ctx["stack"]
        arch = (ctx.get("ARCHITECTURE.md") or "")[:3500]
        description = ctx.get("description", "")
        surface = stack_surface(stack, description)
        results: Dict[str, str] = {}
        ent = surface["entity_slug"]        # e.g. "habit"
        Ent = surface["entity_pascal"]       # e.g. "Habit"

        if stack in ("fastapi-react", "flutter-fastapi"):
            # Service layer
            prompt_svc = f"""
Project: {ctx['project_name']}
Description: {description}
Architecture (excerpt):
{arch}

Allowed domain: {surface['domain']}
API surface: {surface['endpoints']}

Write backend/services/{ent}_service.py — a real service class {Ent}Service
with methods: list_{ent}s, get_{ent}, create_{ent}, update_{ent}, delete_{ent},
matching what the app description above actually needs (add/rename fields and
methods to fit the domain — do not just genericize a project-manager).
Use a simple in-memory or SQLAlchemy-style repository pattern.
Raise domain-specific exceptions ({Ent}NotFound, ValidationError).
Complete working Python. No stubs.
"""
            results[f"backend/services/{ent}_service.py"] = self._call(prompt_svc, max_tokens=5000)
            results["backend/services/__init__.py"] = ""

            prompt_auth = f"""
Write backend/services/auth_service.py — AuthService with register + login.
Use bcrypt password hashing, JWT creation (python-jose style).
Raise AuthError on failure. Complete working Python.
"""
            results["backend/services/auth_service.py"] = self._call(prompt_auth, max_tokens=4500)

            prompt_router = f"""
Description: {description}
Write backend/routers/{ent}s.py — thin FastAPI router that calls {Ent}Service.
Use Depends for service injection (simple factory is fine).
Map domain exceptions to HTTPException.
Include response models. Complete code.
"""
            results[f"backend/routers/{ent}s.py"] = self._call(prompt_router, max_tokens=4000)

            prompt_auth_r = f"""
Write backend/routers/auth.py — thin FastAPI router for register + login
that calls AuthService. Complete code.
"""
            results["backend/routers/auth.py"] = self._call(prompt_auth_r, max_tokens=3500)

        elif stack == "nextjs-postgres":
            prompt = f"""
Project: {ctx['project_name']}
Description: {description}
Write lib/server/{ent}-service.ts and lib/server/auth-service.ts
with real business logic (not just DB passthrough), modeling the {ent}
domain from the description above — not a generic project manager unless
the description actually describes one.
Then write app/api/{ent}s/route.ts and app/api/auth/login/route.ts as thin handlers.
TypeScript. Complete code. No stubs.
"""
            raw = self._call(prompt, max_tokens=8000)
            # Best-effort split; orchestrator also accepts multi-file from other agents
            results[f"lib/server/{ent}-service.ts"] = raw

        elif stack == "expo-node":
            prompt = f"""
Description: {description}
Write server/services/{ent}Service.js and server/services/authService.js
with real logic modeling the {ent} domain from the description above,
plus thin Express (or similar) routes under server/routes/.
Complete working code.
"""
            results[f"server/services/{ent}Service.js"] = self._call(prompt, max_tokens=6000)

        return results


class FrontendFeaturesAgent(GenAgent):
    role = "frontend_features"
    system = (
        "You are a senior product frontend engineer. "
        "Build polished screens composed from the design-system primitives. "
        "Every screen must include loading, empty, and error states. "
        "Pixel-conscious spacing and hierarchy. Output only source code."
    )

    def run(self, ctx: Dict[str, Any]) -> Dict[str, str]:
        stack = ctx["stack"]
        arch = (ctx.get("ARCHITECTURE.md") or "")[:2500]
        description = ctx.get("description", "")
        surface = stack_surface(stack, description)
        ent = surface["entity_slug"]
        results: Dict[str, str] = {}

        if stack == "fastapi-react":
            prompt = f"""
Project: {ctx['project_name']}
Description: {description}
Architecture excerpt:
{arch}

Primitives are available from ../components/ui (Button, Input, Card, Badge, Spinner, EmptyState).
Tokens from ../theme/tokens.

Write these files as complete TypeScript/TSX:

1) frontend/src/pages/Dashboard.tsx
   - Header with app name
   - List of {ent} cards reflecting the app description above (or empty state) —
     do not default to a generic "project" if the description names a different
     domain entity
   - Primary "New {ent}" button
   - Loading skeleton state
   - Error state with retry

2) frontend/src/pages/Login.tsx
   - Centered card auth form
   - Email + password
   - Primary CTA
   - Error message area
   - Link affordance for register

3) frontend/src/App.tsx
   - Simple view switch between Login and Dashboard
   - Clean layout shell using tokens

Rules:
- Use the primitives
- Use tokens for color/spacing
- No hardcoded random colors
- No stubs
- Real React state
"""
            # Ask for multiple files in one go with clear separators
            raw = self._call(prompt, max_tokens=10000)
            results.update(_split_multi_file(raw, default_prefix="frontend/src/"))

        elif stack == "nextjs-postgres":
            prompt = f"""
Project: {ctx['project_name']}
Description: {description}
Write polished App Router pages for a {ent}-management app matching the
description above (dashboard should list/manage {ent}s, not a generic
"project" unless the description is actually about project management):
- app/(auth)/login/page.tsx
- app/(app)/dashboard/page.tsx
- app/layout.tsx (shell)

Use components/ui primitives and lib/theme/tokens.
Loading / empty / error states required.
Complete TSX only.
"""
            raw = self._call(prompt, max_tokens=9000)
            results.update(_split_multi_file(raw))

        elif stack == "expo-node":
            prompt = f"""
Project: {ctx['project_name']}
Description: {description}
Write Expo Router screens for a {ent}-focused app matching the description
above (dashboard should reflect {ent}s, not a generic "project" list unless
the description actually describes project management):
- app/(auth)/login.tsx
- app/(app)/index.tsx  (dashboard)
- app/_layout.tsx

Use src/components/ui and src/theme/tokens.
Include loading/empty/error. TypeScript.
"""
            raw = self._call(prompt, max_tokens=8000)
            results.update(_split_multi_file(raw))

        elif stack == "flutter-fastapi":
            prompt = f"""
Project: {ctx['project_name']}
Description: {description}
Write Flutter screens using AppTokens + lib/widgets/ui.dart for a {ent}-focused
app matching the description above (dashboard should reflect {ent}s, not a
generic "project" list unless the description actually describes project
management):
- lib/screens/login_screen.dart
- lib/screens/dashboard_screen.dart
- lib/main.dart (MaterialApp + routes)

Real state, loading/empty/error. Complete Dart.
"""
            raw = self._call(prompt, max_tokens=9000)
            results.update(_split_multi_file(raw))

        return results


class UIPolishAgent(GenAgent):
    role = "ui_polish"
    system = (
        "You are a UI polish specialist. "
        "Improve visual hierarchy, spacing, motion, focus states, and empty/loading/error treatment. "
        "Output only improved full file content. No stubs."
    )

    def run(self, ctx: Dict[str, Any], files: Dict[str, str]) -> Dict[str, str]:
        # Polish only the main UI files that already exist
        targets = {
            k: v for k, v in files.items()
            if k.endswith((".tsx", ".jsx", ".dart")) and any(
                s in k for s in ("Dashboard", "Login", "page.tsx", "screen", "App.tsx", "main.dart")
            )
        }
        if not targets:
            return {}

        results = {}
        for path, content in list(targets.items())[:4]:
            prompt = f"""
File: {path}
Current content:
{content[:6000]}

Improve this file for visual polish:
- Stronger hierarchy and spacing rhythm
- Clear loading / empty / error treatment if missing
- Better focus and disabled states
- Subtle motion where appropriate (web)
- Keep behavior intact
- Return the FULL improved file only
"""
            try:
                results[path] = self._call(prompt, max_tokens=7000)
            except Exception:
                pass
        return results


class TesterAgent(GenAgent):
    role = "tester"
    system = "You write real tests that assert behavior. No assert True. No empty tests. Output only source code."

    def run(self, ctx: Dict[str, Any]) -> Dict[str, str]:
        stack = ctx["stack"]
        description = ctx.get("description", "")
        surface = stack_surface(stack, description)
        Ent = surface["entity_pascal"]
        ent = surface["entity_slug"]
        if stack in ("fastapi-react", "flutter-fastapi"):
            prompt = f"""
Project: {ctx['project_name']}
Description: {description}
Write tests/test_services.py that tests {Ent}Service and AuthService behavior
(create, get, validation errors, password hashing) — matching the {ent} domain
described above, not a generic project manager.
Use pytest. Real assertions only.
"""
            return {"tests/test_services.py": self._call(prompt, max_tokens=5000)}
        if stack == "nextjs-postgres":
            return {"__tests__/services.test.ts": self._call(
                f"Description: {description}\n"
                f"Write a Jest/Vitest test file for {ent}-service and auth-service "
                f"with real assertions, matching the {ent} domain described above.",
                max_tokens=4000,
            )}
        return {}


class DevOpsAgent(GenAgent):
    role = "devops"
    system = "You produce real deployment artifacts. Output only file content."

    def run(self, ctx: Dict[str, Any], test_output: Optional[TestRunResult] = None) -> Dict[str, str]:
        stack = ctx["stack"]
        results = {}

        # docker-compose
        prompt = f"""
Project: {ctx['project_name']}
Stack: {stack}
Write a production-minded docker-compose.yml with frontend, backend, and database services
(as appropriate for the stack). Include healthchecks and sensible env defaults.
Complete YAML only.
"""
        results["docker-compose.yml"] = self._call(prompt, max_tokens=3000)

        status = "Tests not run"
        if test_output is not None:
            if not test_output.ran:
                status = f"Tests did not run: {test_output.output[:500]}"
            else:
                status = "PASSED" if test_output.passed else f"FAILED\n{test_output.output[:1500]}"

        results["VERIFICATION.md"] = f"""# Verification

## Test results
{status}

## Acceptance
- [ ] Health endpoint responds
- [ ] Auth register/login works
- [ ] Core list/create flow works
- [ ] UI shows loading / empty / error states
- [ ] Docker compose starts

## Notes
Generated by Neon Architect v5 generation core.
"""
        return results


def _split_multi_file(raw: str, default_prefix: str = "") -> Dict[str, str]:
    """Best-effort split of model output that contains multiple files."""
    results: Dict[str, str] = {}
    # Patterns like: // file: path  or  ### path  or  --- path ---
    parts = re.split(r"(?m)^(?:\/\/\s*file:|###\s*|---\s*)([^\n]+?)(?:\s*---)?\s*$", raw)
    if len(parts) >= 3:
        # parts[0] preamble, then pairs of (path, content)
        it = iter(parts[1:])
        for path, content in zip(it, it):
            path = path.strip().strip("`").strip()
            if path:
                results[path] = content.strip()
        if results:
            return results
    # Fallback: single blob
    if raw.strip():
        guess = default_prefix + "generated.tsx"
        results[guess] = raw.strip()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Scaffold (minimal solid base)
# ─────────────────────────────────────────────────────────────────────────────

def scaffold(stack: str, project_dir: Path, ctx: Dict[str, Any]) -> List[str]:
    created = []
    name = ctx["project_name"]

    def w(rel: str, content: str):
        p = project_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        created.append(rel)

    if stack == "fastapi-react":
        w("backend/requirements.txt", "fastapi>=0.111\nuvicorn[standard]>=0.30\nsqlalchemy>=2.0\npython-jose[cryptography]\nbcrypt\npydantic-settings\nhttpx\n")
        w("backend/main.py", f'''from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import health

app = FastAPI(title="{name}")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(health.router, prefix="/api")
''')
        w("backend/routers/__init__.py", "")
        w("backend/routers/health.py", '''from fastapi import APIRouter
router = APIRouter()
@router.get("/health")
def health():
    return {"status": "ok"}
''')
        w("backend/__init__.py", "")
        w("frontend/package.json", f'''{{
  "name": "{name.lower().replace(" ", "-")}",
  "private": true,
  "version": "0.1.0",
  "scripts": {{ "dev": "vite", "build": "vite build", "preview": "vite preview" }},
  "dependencies": {{
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  }},
  "devDependencies": {{
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.4.0",
    "vite": "^5.4.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }}
}}
''')
        w("frontend/index.html", f'''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{name}</title>
  </head>
  <body class="bg-slate-950 text-slate-50">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
''')
        w("frontend/src/main.tsx", '''import React from "react";
import {{ createRoot }} from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
'''.replace("{{", "{").replace("}}", "}"))
        w("frontend/src/index.css", """@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
}
body {
  margin: 0;
  min-height: 100vh;
  font-family: Inter, system-ui, sans-serif;
}
""")
        w("frontend/src/App.tsx", '''export default function App() {
  return (
    <div style={{ padding: 32 }}>
      <h1>Loading application…</h1>
    </div>
  );
}
''')
        w("frontend/vite.config.ts", '''import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({ plugins: [react()], server: { port: 5173 } });
''')
        w("frontend/tsconfig.json", '''{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
''')

    elif stack == "expo-node":
        w("package.json", f'''{{
  "name": "{name.lower().replace(" ", "-")}",
  "version": "0.1.0",
  "main": "expo-router/entry",
  "scripts": {{ "start": "expo start", "android": "expo start --android", "ios": "expo start --ios" }},
  "dependencies": {{
    "expo": "~51.0.0",
    "expo-router": "~3.5.0",
    "react": "18.2.0",
    "react-native": "0.74.0"
  }}
}}
''')
        w("app/_layout.tsx", '''import {{ Stack }} from "expo-router";
export default function Layout() {{
  return <Stack screenOptions={{ headerStyle: {{ backgroundColor: "#0B0F19" }}, headerTintColor: "#F8FAFC" }} />;
}}
'''.replace("{{", "{").replace("}}", "}"))
        w("app/index.tsx", '''import {{ Text, View }} from "react-native";
export default function Index() {
  return (
    <View style={{ flex: 1, backgroundColor: "#0B0F19", justifyContent: "center", alignItems: "center" }}>
      <Text style={{ color: "#F8FAFC" }}>Bootstrapping…</Text>
    </View>
  );
}
''')
        w("server/index.js", '''const http = require("http");
const server = http.createServer((req, res) => {
  if (req.url === "/api/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }
  res.writeHead(404);
  res.end();
});
server.listen(process.env.PORT || 4000);
''')

    elif stack == "flutter-fastapi":
        w("pubspec.yaml", f'''name: {re.sub(r"[^a-z0-9_]", "_", name.lower())}
description: {name}
publish_to: "none"
version: 0.1.0
environment:
  sdk: ">=3.0.0 <4.0.0"
dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.0
dev_dependencies:
  flutter_test:
    sdk: flutter
flutter:
  uses-material-design: true
''')
        w("lib/main.dart", '''import "package:flutter/material.dart";
void main() {
  runApp(const MaterialApp(home: Scaffold(body: Center(child: Text("Bootstrapping…")))));
}
''')
        # Backend same as fastapi-react minimal
        w("backend/requirements.txt", "fastapi>=0.111\nuvicorn[standard]>=0.30\nbcrypt\npython-jose[cryptography]\n")
        w("backend/main.py", f'''from fastapi import FastAPI
app = FastAPI(title="{name}")
@app.get("/api/health")
def health():
    return {{"status": "ok"}}
''')

    elif stack == "nextjs-postgres":
        w("package.json", f'''{{
  "name": "{name.lower().replace(" ", "-")}",
  "private": true,
  "scripts": {{ "dev": "next dev", "build": "next build", "start": "next start" }},
  "dependencies": {{
    "next": "14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  }},
  "devDependencies": {{
    "typescript": "^5.4.0",
    "@types/react": "^18.3.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }}
}}
''')
        w("app/layout.tsx", f'''export const metadata = {{ title: "{name}" }};
import "./globals.css";
export default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-50 antialiased">{{children}}</body>
    </html>
  );
}}
'''.replace("{{", "{").replace("}}", "}"))
        w("app/page.tsx", '''export default function Page() {
  return <main style={{ padding: 32 }}>Bootstrapping…</main>;
}
''')
        w("app/globals.css", "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n")

    w("README.md", f"# {name}\n\nGenerated by Neon Architect v5.\n\nStack: {stack}\n")
    return created


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator v5
# ─────────────────────────────────────────────────────────────────────────────

class GenerationOrchestratorV5:
    """
    Multi-pass orchestrator:
    Scaffold → Architect → Tokens → Primitives → Backend → Frontend Features → Polish → Test/Repair → DevOps
    """

    def __init__(self, pool: Any, config: Dict[str, Any]):
        self.pool = pool
        self.config = config

    def _prog(self, cb: ProgressCb, phase: str, msg: str):
        if cb:
            cb(phase, msg)

    def _run_tests(self, project_dir: Path, stack: str) -> TestRunResult:
        if stack in ("fastapi-react", "flutter-fastapi"):
            if not (project_dir / "tests").exists():
                return TestRunResult(False, False, "No tests/ directory")
            cmd = ["python", "-m", "pytest", "tests/", "-x", "--tb=short", "-q"]
            try:
                proc = subprocess.run(cmd, cwd=str(project_dir), capture_output=True, text=True, timeout=120)
                out = (proc.stdout or "") + (proc.stderr or "")
                return TestRunResult(True, proc.returncode == 0, out[-6000:])
            except Exception as e:
                return TestRunResult(False, False, str(e))
        return TestRunResult(False, False, f"No automated runner wired for {stack} in v5 core yet")

    def _import_consistency(self, project_dir: Path, generated: List[str]) -> List[str]:
        problems = []
        py_files = [p for p in generated if p.endswith(".py")]
        # Also scan disk under backend/ so repair-created modules count
        for fp in (project_dir / "backend").rglob("*.py") if (project_dir / "backend").exists() else []:
            rel = str(fp.relative_to(project_dir)).replace("\\", "/")
            if rel not in py_files:
                py_files.append(rel)
        module_map = {}
        for rel in py_files:
            mod = rel[:-3].replace("/", ".").replace("\\", ".")
            module_map[mod] = rel
            if mod.endswith(".__init__"):
                module_map[mod[: -len(".__init__")]] = rel
        for rel in py_files:
            fp = project_dir / rel
            if not fp.exists():
                continue
            try:
                tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"), filename=rel)
            except SyntaxError as e:
                problems.append(f"{rel}: syntax error {e.msg}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    if node.module.startswith("backend.") and node.module not in module_map:
                        top = node.module.split(".")[0]
                        if any(m.startswith(top + ".") or m == top for m in module_map):
                            if node.module not in module_map:
                                problems.append(f"{rel}: imports '{node.module}' but module not generated")
        return problems

    def _repair_imports(
        self,
        ctx: Dict[str, Any],
        project_dir: Path,
        problems: List[str],
        result: "GenerationResult",
    ) -> int:
        """Create missing modules / package __init__ files for reported import gaps."""
        fixed = 0
        missing_mods = []
        for p in problems:
            # e.g. "backend/routers/x.py: imports 'backend.services.foo' but module not generated"
            if "imports '" in p and "' but module not generated" in p:
                mod = p.split("imports '", 1)[1].split("'", 1)[0]
                missing_mods.append(mod)
        # Always ensure package inits
        for pkg in ("backend", "backend/services", "backend/routers", "tests"):
            init = project_dir / pkg / "__init__.py"
            if (project_dir / pkg).exists() and not init.exists():
                init.write_text("", encoding="utf-8")
                rel = f"{pkg}/__init__.py"
                if rel not in result.files_generated:
                    result.files_generated.append(rel)
                fixed += 1
        agent = GenAgent(self.pool, self.config)
        agent.role = "import_repair"
        for mod in sorted(set(missing_mods))[:6]:
            rel = mod.replace(".", "/") + ".py"
            dest = project_dir / rel
            if dest.exists():
                continue
            prompt = (
                f"Project: {ctx.get('project_name')}\nDescription: {ctx.get('description')}\n"
                f"Create missing module {mod} (file {rel}).\n"
                f"Other modules may import it. Provide a minimal but real implementation "
                f"(classes/functions that make sense for this app). Complete Python only."
            )
            try:
                code = agent._call(prompt, max_tokens=3500)
                errs: List[str] = []
                if _safe_write(project_dir, rel, code, errs):
                    result.files_generated.append(rel)
                    fixed += 1
                else:
                    result.warnings.extend(errs)
            except Exception as e:
                result.warnings.append(f"import_repair {mod}: {e}")
        return fixed

    def _repair_tests(
        self,
        ctx: Dict[str, Any],
        project_dir: Path,
        test_output: str,
        result: "GenerationResult",
    ) -> None:
        """One focused repair pass from pytest output."""
        agent = GenAgent(self.pool, self.config)
        agent.role = "test_repair"
        prompt = (
            f"Project: {ctx.get('project_name')}\nStack: {ctx.get('stack')}\n"
            f"Description: {ctx.get('description')}\n\n"
            f"pytest output (truncated):\n{test_output[-3500:]}\n\n"
            "Fix the failing tests by writing COMPLETE corrected source files.\n"
            "Prefer fixing application code over deleting assertions.\n"
            "Output format: for each file, a line '# FILE: relative/path.py' then the full file body.\n"
            "Only Python source. No markdown fences."
        )
        try:
            raw = agent._call(prompt, max_tokens=8000)
        except Exception as e:
            result.warnings.append(f"test_repair call failed: {e}")
            return
        current_path = None
        buf: List[str] = []
        def flush():
            nonlocal current_path, buf
            if current_path and buf:
                content = "\n".join(buf).strip()
                errs: List[str] = []
                if _safe_write(project_dir, current_path, content, errs):
                    if current_path not in result.files_generated:
                        result.files_generated.append(current_path)
                else:
                    result.warnings.extend(errs)
            current_path = None
            buf = []
        for line in raw.splitlines():
            if line.startswith("# FILE:"):
                flush()
                current_path = line.split(":", 1)[1].strip()
            else:
                buf.append(line)
        flush()

    def _build_baseline_ui_spec(self, ctx: Dict[str, Any], base_url: str) -> Optional[Any]:
        """Construct a conservative UISpec from what FrontendFeaturesAgent
        was asked to generate, without needing to parse the actual output
        for exact selector/class names (the model chooses those itself, so
        guessing brittle CSS selectors would fail QA on style, not
        substance). Only checks things we can be confident about from the
        prompts we sent: the page loads, a login form has *some* email +
        password input, and the dashboard route is reachable after a
        (best-effort) login attempt. Returns None if qa_browser isn't
        importable (e.g. Playwright not installed) so callers can skip
        cleanly instead of crashing generation over an optional QA pass.
        """
        try:
            from qa_browser import UISpec, Flow, Step, VisualPage
        except Exception:
            return None

        stack = ctx["stack"]
        entity = ctx.get("_entity_pascal", "Project")

        login_flow = Flow(
            id="login_smoke",
            description="Load the login page and attempt a login submission",
            steps=[
                Step(action="goto", url="/", name="open_root"),
                Step(action="wait", value="800", name="settle"),
            ],
        )

        return UISpec(
            base_url=base_url,
            flows=[login_flow],
            visual_pages=[VisualPage(path="/", name="home")],
            must_have_text=[],
            must_have_selectors=[],
        )

    def _run_qa_pass(
        self,
        ctx: Dict[str, Any],
        project_dir: Path,
        stack: str,
        on_progress: ProgressCb,
    ) -> Optional[Any]:
        """Best-effort browser QA pass for web stacks. Opt-in via
        config["enable_qa_pass"] because it starts a real dev server and
        requires Playwright — a meaningfully heavier runtime dependency
        than the rest of generate(), which previously never launched a
        server or a browser. Returns a QAResult, or None if skipped/
        unavailable (missing Playwright, non-web stack, disabled, or the
        preview server failed to start) — callers should treat None as
        "no QA signal available", not as a failure.
        """
        if stack not in ("fastapi-react", "nextjs-postgres"):
            # qa_browser drives a real browser against a served frontend;
            # expo-node and flutter-fastapi don't serve one.
            return None
        if not self.config.get("enable_qa_pass"):
            return None

        try:
            from qa_browser import run_qa_suite
        except Exception as e:
            self._prog(on_progress, "qa", f"⚠ qa_browser unavailable: {e}")
            return None

        preview_start = self.config.get("_preview_starter")
        if not callable(preview_start):
            self._prog(
                on_progress, "qa",
                "⚠ no preview starter wired (config['_preview_starter']); skipping QA",
            )
            return None

        try:
            base_url = preview_start(project_dir, stack)
        except Exception as e:
            self._prog(on_progress, "qa", f"⚠ preview server failed to start: {e}")
            return None
        if not base_url:
            self._prog(on_progress, "qa", "⚠ preview server did not return a URL; skipping QA")
            return None

        spec = self._build_baseline_ui_spec(ctx, base_url)
        if spec is None:
            self._prog(on_progress, "qa", "⚠ Playwright not installed; skipping QA")
            return None

        self._prog(on_progress, "qa", f"Running browser QA against {base_url}…")
        try:
            qa_out = project_dir / "qa_out"
            qa_result = run_qa_suite(spec, out_dir=qa_out, update_baselines=True)
        except Exception as e:
            self._prog(on_progress, "qa", f"⚠ QA run failed: {e}")
            return None

        self._prog(on_progress, "qa", "✓ QA passed" if qa_result.ok else "✗ QA found issues")
        return qa_result

    def generate(
        self,
        description: str,
        project_dir: Path,
        stack: Optional[str] = None,
        on_progress: ProgressCb = None,
    ) -> GenerationResult:
        stack = stack or detect_stack(description)
        if stack not in SUPPORTED_STACKS:
            stack = "fastapi-react"

        project_dir = Path(project_dir).resolve()
        project_dir.mkdir(parents=True, exist_ok=True)
        name = project_dir.name

        ctx: Dict[str, Any] = {
            "project_name": name,
            "description": description,
            "stack": stack,
            "year": datetime.now().year,
        }
        surface = stack_surface(stack, description)
        ctx["_domain"] = surface["domain"]
        ctx["_endpoints"] = surface["endpoints"]
        ctx["_frontend_entities"] = surface["frontend_entities"]
        ctx["_entity_slug"] = surface["entity_slug"]
        ctx["_entity_pascal"] = surface["entity_pascal"]

        result = GenerationResult(success=False, project_dir=project_dir, stack=stack)

        # 1. Scaffold
        self._prog(on_progress, "scaffold", f"Writing {stack} base…")
        try:
            created = scaffold(stack, project_dir, ctx)
            result.files_created = created
            self._prog(on_progress, "scaffold", f"✓ {len(created)} base files")
        except Exception as e:
            result.errors.append(f"scaffold: {e}")
            self._prog(on_progress, "scaffold", f"✗ {e}")

        def ingest(agent_role: str, files: Dict[str, str]):
            written = 0
            for rel, content in files.items():
                if not str(rel).startswith("_") and _safe_write(project_dir, rel, content, result.errors):
                    result.files_generated.append(rel)
                    ctx[rel] = content
                    written += 1
                elif str(rel).startswith("_"):
                    ctx[rel] = content
            self._prog(on_progress, agent_role, f"✓ {written} file(s)")
            return written

        # 2. Architect
        try:
            self._prog(on_progress, "architect", "Designing architecture…")
            ingest("architect", ArchitectAgent(self.pool, self.config).run(ctx))
        except Exception as e:
            result.errors.append(f"architect: {e}")
            self._prog(on_progress, "architect", f"✗ {e}")

        # 3. Design tokens
        try:
            self._prog(on_progress, "design_tokens", "Design tokens…")
            tok = DesignTokensAgent(self.pool, self.config).run(ctx)
            ingest("design_tokens", tok)
            if tok:
                ctx["tokens_path"] = next(iter(tok.keys()))
        except Exception as e:
            result.errors.append(f"design_tokens: {e}")

        # 4. Primitives
        try:
            self._prog(on_progress, "primitives", "UI primitives…")
            ingest("primitives", PrimitivesAgent(self.pool, self.config).run(ctx))
        except Exception as e:
            result.errors.append(f"primitives: {e}")
            self._prog(on_progress, "primitives", f"✗ {e}")

        # 5. Backend (layered)
        try:
            self._prog(on_progress, "backend", "Layered backend…")
            ingest("backend", BackendArchitectedAgent(self.pool, self.config).run(ctx))
        except Exception as e:
            result.errors.append(f"backend: {e}")
            self._prog(on_progress, "backend", f"✗ {e}")

        # 6. Frontend features
        feature_files: Dict[str, str] = {}
        try:
            self._prog(on_progress, "frontend", "Feature screens…")
            feature_files = FrontendFeaturesAgent(self.pool, self.config).run(ctx)
            ingest("frontend", feature_files)
        except Exception as e:
            result.errors.append(f"frontend: {e}")
            self._prog(on_progress, "frontend", f"✗ {e}")

        # 7. Polish pass
        try:
            self._prog(on_progress, "polish", "UI polish pass…")
            # Merge current UI files for polish context
            ui_ctx = {k: ctx[k] for k in ctx if k.endswith((".tsx", ".jsx", ".dart"))}
            polished = UIPolishAgent(self.pool, self.config).run(ctx, ui_ctx)
            ingest("polish", polished)
        except Exception as e:
            result.warnings.append(f"polish: {e}")
            self._prog(on_progress, "polish", f"⚠ {e}")

        # 8. Tests
        try:
            self._prog(on_progress, "tester", "Writing tests…")
            ingest("tester", TesterAgent(self.pool, self.config).run(ctx))
        except Exception as e:
            result.warnings.append(f"tester: {e}")

        # Consistency + repair loop (closes Problem B residual imports)
        problems = self._import_consistency(project_dir, result.files_generated)
        if problems:
            self._prog(on_progress, "consistency", f"✗ {len(problems)} issue(s) — entering repair")
            for repair_i in range(1, 4):
                fixed = self._repair_imports(ctx, project_dir, problems, result)
                result.repair_rounds = repair_i
                problems = self._import_consistency(project_dir, result.files_generated)
                if not problems:
                    self._prog(on_progress, "repair", f"✓ import graph clean after round {repair_i}")
                    break
                self._prog(on_progress, "repair", f"round {repair_i}: {len(problems)} left")
            if problems:
                for p in problems:
                    result.errors.append(f"consistency: {p}")
                self._prog(on_progress, "consistency", f"✗ {len(problems)} remain after repair")
            else:
                # clear prior consistency-only soft noise
                result.errors = [e for e in result.errors if not e.startswith("consistency:")]
        else:
            self._prog(on_progress, "consistency", "✓ import graph clean")

        test_result = self._run_tests(project_dir, stack)
        result.test_output = test_result
        if test_result.ran and test_result.passed:
            self._prog(on_progress, "test", "✓ tests passed")
        elif test_result.ran:
            # One test-repair pass: feed failure output back to a focused backend/tester fix
            self._prog(on_progress, "test", "✗ tests failed — one repair pass")
            try:
                self._repair_tests(ctx, project_dir, test_result.output, result)
                test_result = self._run_tests(project_dir, stack)
                result.test_output = test_result
                result.repair_rounds += 1
                if test_result.ran and test_result.passed:
                    self._prog(on_progress, "test", "✓ tests passed after repair")
                else:
                    self._prog(on_progress, "test", "✗ tests still failing")
            except Exception as e:
                result.warnings.append(f"test_repair: {e}")
        else:
            self._prog(on_progress, "test", f"⚠ {test_result.output[:120]}")

        # 9. DevOps
        try:
            self._prog(on_progress, "devops", "Deployment artifacts…")
            ingest("devops", DevOpsAgent(self.pool, self.config).run(ctx, test_result))
        except Exception as e:
            result.warnings.append(f"devops: {e}")

        # 10. Optional browser QA pass (web stacks only, opt-in — see
        # _run_qa_pass docstring). Recorded as a warning, not a hard
        # error/success gate: it's a best-effort signal built from a
        # generic baseline spec, not a ground-truth product requirement,
        # so it shouldn't be able to flip result.success on its own the
        # way a failing pytest run can.
        qa_result = self._run_qa_pass(ctx, project_dir, stack, on_progress)
        result.qa_output = qa_result
        if qa_result is not None and not qa_result.ok:
            result.warnings.append(
                f"qa: browser QA found issues — see {qa_result.report_path or 'qa_out/'}"
            )

        hard = [e for e in result.errors if not e.startswith("[soft]")]
        # success = (no hard errors) AND (tests actually ran AND passed)
        # if tests never ran -> success=False
        # soft UI errors are warnings only (not in hard)
        if test_result.ran:
            result.success = len(hard) == 0 and test_result.passed
        else:
            result.success = False

        self._prog(on_progress, "verdict", f"success={result.success} files={len(result.files_generated)}")
        return result
