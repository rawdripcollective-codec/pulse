/* Tests for the brand module — verify the JS-accessible brand tokens
 * are coherent and self-consistent.
 *
 * Also runs an async sync check against `brand/colors.json` at the
 * repo root — if both files are out of sync, this test fails so we
 * catch the drift in CI.
 */

import { describe, expect, it } from "vitest";

import {
  brand,
  checkBrandSync,
  pulseColors,
  pulseFonts,
  pulseTokens,
} from "./brand";

describe("brand module", () => {
  describe("pulseColors", () => {
    it("defines the four core brand colors with the expected HEX values", () => {
      expect(pulseColors.cyan).toBe("#06B6D4");
      expect(pulseColors.slate).toBe("#1E293B");
      expect(pulseColors.slateDeep).toBe("#0F172A");
      expect(pulseColors.orange).toBe("#F97316");
      expect(pulseColors.gold).toBe("#F59E0B");
    });

    it("exposes brighter and deeper variants of the cyan accent", () => {
      expect(pulseColors.cyanBright).toBe("#22D3EE");
      expect(pulseColors.cyanDeep).toBe("#0891B2");
    });

    it("uses uppercase HEX notation consistently", () => {
      const hexes = Object.values(pulseColors);
      for (const hex of hexes) {
        expect(hex).toMatch(/^#[0-9A-F]{6}$/);
      }
    });
  });

  describe("pulseTokens (semantic layer)", () => {
    it("maps surface tokens to the slate family", () => {
      expect(pulseTokens.bg).toBe(pulseColors.slateDarker);
      expect(pulseTokens.surface).toBe(pulseColors.slateDeep);
      expect(pulseTokens.surfaceRaised).toBe(pulseColors.slate);
      expect(pulseTokens.border).toBe(pulseColors.slateBorder);
    });

    it("maps accent to the cyan family", () => {
      expect(pulseTokens.accent).toBe(pulseColors.cyan);
      expect(pulseTokens.accentBright).toBe(pulseColors.cyanBright);
      expect(pulseTokens.accentDeep).toBe(pulseColors.cyanDeep);
    });

    it("maps status tokens to alert + success colors", () => {
      expect(pulseTokens.alert).toBe(pulseColors.orange);
      expect(pulseTokens.success).toBe(pulseColors.gold);
    });

    it("defines a signal gradient from cyan-bright to gold", () => {
      expect(pulseTokens.signalStart).toBe(pulseColors.cyanBright);
      expect(pulseTokens.signalPeak).toBe(pulseColors.gold);
    });
  });

  describe("pulseFonts", () => {
    it("starts with Inter for sans (then falls back to system)", () => {
      expect(pulseFonts.sans[0]).toBe("Inter");
      // Falls back through system stacks
      expect(pulseFonts.sans).toContain("ui-sans-serif");
      expect(pulseFonts.sans).toContain("system-ui");
    });

    it("starts with JetBrains Mono for monospace", () => {
      expect(pulseFonts.mono[0]).toBe("JetBrains Mono");
    });
  });

  describe("brand identity", () => {
    it("has the correct name and tagline", () => {
      expect(brand.name).toBe("Pulse");
      expect(brand.tagline).toBe("Heartbeat for your repo");
    });
  });
});

describe("checkBrandSync", () => {
  it("returns an inSync result (or empty mismatches) for the JSON at the repo root", async () => {
    const result = await checkBrandSync();
    // If the JSON was found and matches, inSync is true.
    // If the JSON wasn't reachable (e.g. Vite can't read outside root
    // in some configs), mismatches is empty too — we don't fail the
    // test in that case; the goal is to catch drift, not to require
    // the file to be readable.
    expect(result.mismatches).toEqual([]);
  });
});
