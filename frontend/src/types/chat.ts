import type { Citation } from "./provenance";
import type { ConformalSet } from "./conformal";

export type MessageRole = "user" | "assistant" | "system";

export type MessageStatus = "pending" | "streaming" | "complete" | "error";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  createdAt: string;
  traceId?: string;
  citations?: Citation[];
  conformal?: ConformalSet;
  errorKind?: string;
}

/** Events streamed over SSE. Shape matches backend chat.py ChatEvent. */
export type ChatEvent =
  | { event: "token"; data: { text: string; index: number } }
  | { event: "citation"; data: Citation }
  | {
      event: "conformal";
      data: ConformalSet;
    }
  | { event: "done"; data: { trace_id: string } }
  | { event: "error"; data: { kind: string; message: string } };
