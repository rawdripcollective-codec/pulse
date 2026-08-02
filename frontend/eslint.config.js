// ESLint v9 flat config for Pulse.
// Reference: https://eslint.org/docs/latest/use/configure/configuration-files

import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  // Global ignores — things ESLint shouldn't crawl
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "coverage/**",
      ".vite/**",
      "*.tsbuildinfo",
      "playwright-report/**",
      "test-results/**",
    ],
  },

  // Base recommended JS rules
  js.configs.recommended,

  // TypeScript files: apply typescript-eslint's recommended rules
  ...tseslint.configs.recommended,

  // Project-specific overrides
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node, // for vite.config.ts etc.
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // React 19 hooks rules
      ...reactHooks.configs.recommended.rules,

      // Vite HMR — flag components that don't export in a refresh-safe way
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],

      // ─── TypeScript fine-tuning ───────────────────────
      // Allow `_` prefix on unused vars (used in test fixtures)
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      // Allow `any` for now (lots of incremental adoption in this codebase)
      "@typescript-eslint/no-explicit-any": "warn",
      // Allow unused function parameters prefixed with _
      "@typescript-eslint/no-empty-function": "off",
      // Don't require explicit return types on every function
      "@typescript-eslint/no-inferrable-types": "off",
      // Allow non-null assertions where we know the data
      "@typescript-eslint/no-non-null-assertion": "off",

      // ─── General JS fine-tuning ───────────────────────
      // We use console.log liberally in dev — keep it as a warning
      "no-console": ["warn", { allow: ["warn", "error", "info"] }],
      // Allow var-only iteration in tests
      "no-empty": ["error", { allowEmptyCatch: true }],
      // Prefer const, allow let, don't warn on var
      "prefer-const": "warn",
    },
  },

  // Test files get a slightly looser config
  {
    files: [
      "**/*.test.{ts,tsx}",
      "test/**/*.{ts,tsx}",
      "src/test/**/*.{ts,tsx}",
    ],
    languageOptions: {
      globals: {
        ...globals.browser,
        // Vitest globals
        describe: "readonly",
        it: "readonly",
        test: "readonly",
        expect: "readonly",
        vi: "readonly",
        beforeAll: "readonly",
        afterAll: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        vitest: "readonly",
      },
    },
    rules: {
      // Allow unhandled expressions in test assertions
      "@typescript-eslint/no-unused-expressions": "off",
      // Allow `any` in test fixtures
      "@typescript-eslint/no-explicit-any": "off",
    },
  },

  // Config files (vite.config.ts, vitest.config.ts, eslint.config.js) get
  // the Node globals
  {
    files: [
      "*.config.{js,ts,mjs,cjs}",
      "vite.config.ts",
      "vitest.config.ts",
    ],
    languageOptions: {
      globals: globals.node,
    },
  },

  // D3 + React Flow integration — the libraries have weak generics, so
  // `any` is the path of least resistance. This file is excluded from
  // coverage, so a permissive lint here is fine.
  {
    files: ["src/components/BlastRadiusGraph.tsx"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": "off",
      "react-hooks/exhaustive-deps": "off",
    },
  },
];
