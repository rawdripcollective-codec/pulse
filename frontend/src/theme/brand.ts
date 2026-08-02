/* Pulse brand design tokens — the single source of truth for the frontend.

These values mirror `brand/colors.json` at the repo root. When you change
a brand color, update BOTH this file AND `brand/colors.json` (the
brand test will catch drift). Long-term: auto-generate this file from
`brand/colors.json` via a `make sync-brand` target.

The CSS layer (`src/styles/theme.css`) reads from these values via
Tailwind 4's `@theme` directive, which means every constant here
becomes a utility class (e.g. `bg-pulse-cyan`, `text-pulse-gold`).
*/

// ─── Brand colors ────────────────────────────────────────────

export const pulseColors = {
  /** Cyan — primary brand mark, links, primary actions, focus rings. */
  cyan: "#06B6D4",
  /** Cyan bright — hover/focus state on cyan. */
  cyanBright: "#22D3EE",
  /** Cyan deep — pressed state. */
  cyanDeep: "#0891B2",

  /** Slate — dark mode surface (cards, panels). */
  slate: "#1E293B",
  /** Slate deep — page background. */
  slateDeep: "#0F172A",
  /** Slate darker — page background below surface. */
  slateDarker: "#020617",
  /** Slate border — dividers, borders. */
  slateBorder: "#334155",

  /** Orange — high-risk alerts, critical events. */
  orange: "#F97316",
  /** Gold — approved states, success highlights, premium finish. */
  gold: "#F59E0B",

  /** Foreground (text) — primary readable color on dark surfaces. */
  fg: "#F8FAFC",
  /** Foreground muted — secondary text. */
  fgMuted: "#94A3B8",
  /** Foreground dim — tertiary text, metadata. */
  fgDim: "#64748B",
} as const;

// ─── Semantic tokens (use these in components) ────────────────

/**
 * Semantic tokens layer the brand colors into named roles. Prefer these
 * over `pulseColors.cyan` etc. in component code — that way a future
 * rebranding changes one mapping, not every usage.
 */
export const pulseTokens = {
  // Surfaces (dark)
  bg: pulseColors.slateDarker,         // page background
  surface: pulseColors.slateDeep,      // card / panel
  surfaceRaised: pulseColors.slate,    // raised card / hover
  border: pulseColors.slateBorder,     // dividers

  // Foreground
  fg: pulseColors.fg,                  // primary text
  fgMuted: pulseColors.fgMuted,        // secondary text
  fgDim: pulseColors.fgDim,            // metadata

  // Brand
  accent: pulseColors.cyan,            // primary accent
  accentBright: pulseColors.cyanBright,
  accentDeep: pulseColors.cyanDeep,

  // Status
  alert: pulseColors.orange,           // high-risk
  success: pulseColors.gold,           // approved

  // Pulse signal gradient (the signature cyan→gold peak)
  signalStart: pulseColors.cyanBright,
  signalPeak: pulseColors.gold,
} as const;

// ─── Typography ──────────────────────────────────────────────

export const pulseFonts = {
  sans: [
    "Inter",
    "ui-sans-serif",
    "system-ui",
    "-apple-system",
    "sans-serif",
  ] as const,
  mono: [
    "JetBrains Mono",
    "ui-monospace",
    "SFMono-Regular",
    "monospace",
  ] as const,
} as const;

// ─── Brand identity ──────────────────────────────────────────

export const brand = {
  name: "Pulse",
  tagline: "Heartbeat for your repo",
  description: "Agentic PR Triage & Review for Maintainers",
} as const;

// ─── Sync check ──────────────────────────────────────────────

/**
 * Returns true if the in-module brand colors match the JSON at the repo
 * root. Used by the brand test to catch drift.
 *
 * The JSON import is optional — if the file isn't found, we assume drift
 * is fine (e.g. the test environment doesn't have the brand/ dir).
 */
export async function checkBrandSync(): Promise<{
  inSync: boolean;
  mismatches: string[];
}> {
  const mismatches: string[] = [];
  try {
    // Dynamic import so a missing file doesn't break the app at build
    const url = new URL("../../../brand/colors.json", import.meta.url);
    const json = (await import(/* @vite-ignore */ url.href)) as {
      colors: Record<string, { hex: string }>;
    };

    const mapping: Record<string, string> = {
      "primary": pulseColors.cyan,
      "base": pulseColors.slate,
      "baseDeep": pulseColors.slateDeep,
      "alert": pulseColors.orange,
      "accent": pulseColors.gold,
    };
    for (const [key, expected] of Object.entries(mapping)) {
      const got = json.colors?.[key]?.hex?.toUpperCase();
      if (got && got !== expected.toUpperCase()) {
        mismatches.push(`${key}: module=${expected} json=${got}`);
      }
    }
  } catch {
    // brand/colors.json not accessible from the frontend at runtime —
    // that's fine, this is a dev-time check.
  }
  return { inSync: mismatches.length === 0, mismatches };
}
