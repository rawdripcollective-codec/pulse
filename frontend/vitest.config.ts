/* Vitest configuration — extends vite.config.ts with test-specific options. */

/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "json"],
      exclude: [
        "node_modules/",
        "src/main.tsx",
        "src/api/**", // covered indirectly via integration tests
        "src/components/BlastRadiusGraph.tsx", // d3/React Flow — too visual
        "**/*.test.{ts,tsx}",
      ],
    },
  },
});
