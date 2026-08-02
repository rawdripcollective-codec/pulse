/* Tests for the useWebSocket hook — connection state + message routing.

We stub the global WebSocket with a minimal mock because jsdom doesn't
ship with one. This lets us drive the hook through a complete
open/message/close lifecycle without a real server.
*/

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWebSocket } from "./useWebSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  readyState = 0; // CONNECTING
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  // Test helpers
  simulateOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  simulateMessage(data: string) {
    this.onmessage?.({ data });
  }

  simulateError() {
    this.onerror?.();
  }

  simulateClose() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  // WebSocket is a read-only global; use defineProperty to override
  Object.defineProperty(globalThis, "WebSocket", {
    writable: true,
    configurable: true,
    value: FakeWebSocket,
  });
});

afterEach(() => {
  vi.useRealTimers();
  // Restore: delete our override (falls back to undefined, which is what
  // the production code expects if it ever runs without a real WS)
  // @ts-expect-error — best effort
  delete (globalThis as { WebSocket?: unknown }).WebSocket;
});

describe("useWebSocket", () => {
  it("starts disconnected", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() => useWebSocket(onMessage));
    expect(result.current.connected).toBe(false);
  });

  it("marks connected when WebSocket opens", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() => useWebSocket(onMessage));

    act(() => {
      FakeWebSocket.instances[0]!.simulateOpen();
    });

    expect(result.current.connected).toBe(true);
  });

  it("marks disconnected when WebSocket closes", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() => useWebSocket(onMessage));

    act(() => {
      FakeWebSocket.instances[0]!.simulateOpen();
    });
    expect(result.current.connected).toBe(true);

    act(() => {
      FakeWebSocket.instances[0]!.simulateClose();
    });
    expect(result.current.connected).toBe(false);
  });

  it("routes incoming JSON messages to onMessage", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() => useWebSocket(onMessage));

    act(() => {
      FakeWebSocket.instances[0]!.simulateOpen();
      FakeWebSocket.instances[0]!.simulateMessage(
        JSON.stringify({
          type: "triage_complete",
          repo: "acme/widget",
          pr_number: 1,
          classification: "human_first",
        })
      );
    });

    expect(onMessage).toHaveBeenCalledWith({
      type: "triage_complete",
      repo: "acme/widget",
      pr_number: 1,
      classification: "human_first",
    });
    // Still connected after receiving a message
    expect(result.current.connected).toBe(true);
  });

  it("ignores unparseable messages without crashing", () => {
    const onMessage = vi.fn();
    renderHook(() => useWebSocket(onMessage));

    expect(() => {
      act(() => {
        FakeWebSocket.instances[0]!.simulateOpen();
        FakeWebSocket.instances[0]!.simulateMessage("not-json{{{}");
      });
    }).not.toThrow();
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("connects to the configured WS_URL", () => {
    renderHook(() => useWebSocket(vi.fn()));
    // Default URL is built from import.meta.env; we just verify
    // *a* WebSocket was constructed and pointed at /ws/triage-updates.
    expect(FakeWebSocket.instances[0]!.url).toMatch(/\/ws\/triage-updates/);
  });

  it("disconnects on unmount", () => {
    const { unmount } = renderHook(() => useWebSocket(vi.fn()));
    const ws = FakeWebSocket.instances[0]!;
    unmount();
    expect(ws.readyState).toBe(FakeWebSocket.CLOSED);
  });
});
