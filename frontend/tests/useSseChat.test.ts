import { describe, expect, it, vi } from "vitest";
import { consumeSseStream } from "../src/hooks/useSseChat";
import type { ChatEvent } from "../src/types/chat";

function stream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const queue = [...chunks];
  return new ReadableStream({
    pull(controller) {
      const next = queue.shift();
      if (next === undefined) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(next));
    },
  });
}

describe("consumeSseStream", () => {
  it("parses a single event", async () => {
    const events: ChatEvent[] = [];
    await consumeSseStream(
      stream([
        'event: token\ndata: {"text":"Hello","index":0}\n\n',
      ]),
      (e) => events.push(e),
    );
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({
      event: "token",
      data: { text: "Hello", index: 0 },
    });
  });

  it("handles events split across reads", async () => {
    const events: ChatEvent[] = [];
    await consumeSseStream(
      stream([
        "event: token\ndata: ",
        '{"text":"Hi","index":0}\n\n',
        'event: done\ndata: {"trace_id":"abc"}\n\n',
      ]),
      (e) => events.push(e),
    );
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({ event: "token" });
    expect(events[1]).toMatchObject({ event: "done" });
  });

  it("ignores events with malformed JSON", async () => {
    const events: ChatEvent[] = [];
    await consumeSseStream(
      stream([
        "event: token\ndata: not-json{\n\n",
        'event: done\ndata: {"trace_id":"x"}\n\n',
      ]),
      (e) => events.push(e),
    );
    // Only the done event should have been emitted.
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ event: "done" });
  });

  it("does not call handler when body ends mid-event", async () => {
    const handler = vi.fn();
    await consumeSseStream(
      stream(["event: token\ndata: {\"text\":\"x\",\"index\":0}"]),
      handler,
    );
    // No trailing blank line → event never flushed.
    expect(handler).not.toHaveBeenCalled();
  });
});
