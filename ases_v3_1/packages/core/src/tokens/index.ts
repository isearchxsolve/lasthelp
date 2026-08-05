// ASES v3.1 — Design Token System
// Single source of truth consumed by canvas, Studio UI, AND emitted to generated apps.
// See DESIGN.md §2. Interface stubs only — no feature logic.

export type ColorToken = { value: string; alpha?: number };
export type TypographyToken = {
  fontFamily: string;
  fontSize: string;
  fontWeight: string | number;
  lineHeight: string;
  letterSpacing?: string;
};
export type SpacingToken = string;
export type RadiusToken = string;
export type ShadowToken = string;
export type MotionToken = { duration: string; easing: string };

export interface TokenGroup {
  id: string;
  color: Record<string, ColorToken>;
  typography: Record<string, TypographyToken>;
  spacing: Record<string, SpacingToken>;
  radius: Record<string, RadiusToken>;
  shadow: Record<string, ShadowToken>;
  motion: Record<string, MotionToken>;
}

export interface Theme {
  id: string;
  name: string;
  mode: 'light' | 'dark';
  tokens: TokenGroup;
}

export interface Breakpoint {
  id: string;
  name: string;
  minWidth: number;
}

export interface TokenResolver {
  resolve(path: string): string | undefined;
  theme(): Theme;
  breakpoint(id: string): Breakpoint | undefined;
}

export interface TokenEmitter {
  toCssVariables(theme: Theme): string;
  toJson(theme: Theme): string;
  toTailwindConfig(theme: Theme): string;
}
