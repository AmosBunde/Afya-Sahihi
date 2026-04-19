import { useCallback, useRef, useState } from "react";
import { config } from "../env";
import type { ChatEvent, ChatMessage } from "../types/chat";
import type { Citation } from "../types/provenance";
import type { ConformalSet } from "../types/conformal";

/**
 * SSE client for POST /api/chat.
 *
 * Why fetch + stream reader instead of EventSource: EventSource
 * doesn't support POST bodies, and our chat endpoint needs a POST
 * (query body, OIDC Authorization header). The stream reader
 * pattern gives us both.
 *
 * Tokens accumulate into the current assistant message's `content`.
 * Citations and conformal set are attached once when their events
 * arrive. On `done`, status flips to "complete". On any error the
 * message records errorKind for the UI to surface.
 */

interface SendArgs {
  query: string;
  token: string | null; // OIDC bearer; null in dev mode
}

interface UseSseChat {
  messages: ChatMessage[];
  streaming: boolean;
  error: string | null;
  send: (args: SendArgs) => Promise<void>;
  cancel: () => void;
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `msg-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

export function useSseChat(): UseSseChat {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const appendToken = useCallback((assistantId: string, text: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId ? { ...m, content: m.content + text } : m,
      ),
    );
  }, []);

  const attachCitation = useCallback(
    (assistantId: string, citation: Citation) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, citations: [...(m.citations ?? []), citation] }
            : m,
        ),
      );
    },
    [],
  );

  const attachConformal = useCallback(
    (assistantId: string, conformal: ConformalSet) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, conformal } : m)),
      );
    },
    [],
  );

  const finalize = useCallback(
    (
      assistantId: string,
      status: "complete" | "error",
      patch: Partial<ChatMessage> = {},
    ) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, status, ...patch } : m)),
      );
    },
    [],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const send = useCallback(
    async ({ query, token }: SendArgs) => {
      if (!query.trim()) return;
      setError(null);

      const userId = newId();
      const assistantId = newId();
      const createdAt = new Date().toISOString();

      setMessages((prev) => [
        ...prev,
        {
          id: userId,
          role: "user",
          content: query,
          status: "complete",
          createdAt,
        },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          status: "streaming",
          createdAt,
        },
      ]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch(`${config.apiBaseUrl}/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ query }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          finalize(assistantId, "error", {
            errorKind: `http_${response.status}`,
          });
          setError(`HTTP ${response.status}`);
          return;
        }

        await consumeSseStream(response.body, (evt) => {
          if (evt.event === "token") {
            appendToken(assistantId, evt.data.text);
          } else if (evt.event === "citation") {
            attachCitation(assistantId, evt.data);
          } else if (evt.event === "conformal") {
            attachConformal(assistantId, evt.data);
          } else if (evt.event === "done") {
            finalize(assistantId, "complete", { traceId: evt.data.trace_id });
          } else if (evt.event === "error") {
            finalize(assistantId, "error", { errorKind: evt.data.kind });
            setError(evt.data.message);
          }
        });
      } catch (exc) {
        if (controller.signal.aborted) {
          finalize(assistantId, "error", { errorKind: "aborted" });
        } else {
          finalize(assistantId, "error", { errorKind: "network" });
          setError(exc instanceof Error ? exc.message : String(exc));
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [appendToken, attachCitation, attachConformal, finalize],
  );

  return { messages, streaming, error, send, cancel };
}

/**
 * Parse an SSE stream body incrementally. Yields ChatEvent objects
 * as `event:` / `data:` pairs arrive.
 */
export async function consumeSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (evt: ChatEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Events are delimited by a blank line per the SSE spec.
    let sep = buffer.indexOf("\n\n");
    while (sep !== -1) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const parsed = parseSseEvent(chunk);
      if (parsed) onEvent(parsed);
      sep = buffer.indexOf("\n\n");
    }
  }
}

function parseSseEvent(chunk: string): ChatEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return null;
  try {
    const data = JSON.parse(dataLines.join("\n"));
    return { event, data } as ChatEvent;
  } catch {
    return null;
  }
}
