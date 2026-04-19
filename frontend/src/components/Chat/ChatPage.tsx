import { useCallback } from "react";
import { MessageList } from "./MessageList";
import { Composer } from "./Composer";
import { useSseChat } from "../../hooks/useSseChat";

/**
 * Top-level chat view. Owns the SSE hook and wires it into the list +
 * composer. Authentication token threading is a placeholder — when
 * OIDC flow is implemented, pass the access token to `send`.
 */
export function ChatPage() {
  const { messages, streaming, send } = useSseChat();

  const handleSend = useCallback(
    (query: string) => send({ query, token: null }),
    [send],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-hidden">
        <MessageList messages={messages} />
      </div>
      <Composer onSend={handleSend} disabled={streaming} />
    </div>
  );
}
