/* Vitest global setup: jest-dom matchers + MSW server lifecycle. */

import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./mocks/server";

// Establish API mocking before all tests.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

// Reset any request handlers added during the tests, so they don't
// affect subsequent tests.
afterEach(() => server.resetHandlers());

// Clean up after the tests are finished.
afterAll(() => server.close());

// Polyfills / shims that jsdom doesn't ship with but React Query /
// other libraries occasionally expect.

// matchMedia — not implemented in jsdom
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // deprecated
    removeListener: () => {}, // deprecated
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// IntersectionObserver — not implemented in jsdom
class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
  root = null;
  rootMargin = "";
  thresholds = [];
}
Object.defineProperty(window, "IntersectionObserver", {
  writable: true,
  value: MockIntersectionObserver,
});
