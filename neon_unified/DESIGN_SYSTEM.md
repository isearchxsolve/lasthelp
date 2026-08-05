# Neon Architect v5 — Design System & Generation Blueprint

## Goals
- Pixel-conscious, modern UIs (not generic dark cards)
- Equally strong, layered backends
- First-class Web + iOS/Android (Expo + Flutter)
- Real functionality over theater

## Design System (Web)
- Tailwind CSS + shadcn/ui primitives (Radix) + Framer Motion
- Design tokens first (colors, type, spacing, radius, elevation, motion)
- Multi-pass generation:
  1. Tokens
  2. Primitives
  3. Feature components + layouts
  4. Polish (states, motion, responsive, a11y)

## Design System (Expo)
- NativeWind + consistent tokens
- Expo Router
- Shared token language with web

## Design System (Flutter)
- Material 3 + custom token layer
- go_router + Riverpod (or Bloc)
- Matching visual language

## Architecture Defaults (Backend)
- API → Service → Repository / Domain
- Explicit error model
- Real auth, validation, tests
- Distributed patterns only when justified

## Orchestrator Flow
Scaffold → Architect → Design Tokens → Primitives → Backend/DB → Frontend Features → Polish → Test+Repair → DevOps/Verify
