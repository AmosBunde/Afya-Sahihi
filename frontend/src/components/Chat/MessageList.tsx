import { useEffect, useRef } from "react";
import type { ChatMessage } from "../../types/chat";
import { Message } from "./Message";
import { useI18n } from "../../hooks/useI18n";

interface Props {
  messages: readonly ChatMessage[];
}

export function MessageList({ messages }: Props) {
  const { t } = useI18n();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new message or streaming token.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <p className="p-4 text-center text-sm text-slate-500 dark:text-slate-400">
        {t("chat.empty")}
      </p>
    );
  }

  return (
    <section
      className="flex flex-col gap-3 overflow-y-auto p-4"
      aria-label={t("a11y.messageList")}
      // role="log" announces new children to screen readers incrementally.
      role="log"
      aria-live="polite"
    >
      {messages.map((m) => (
        <Message key={m.id} message={m} />
      ))}
      <div ref={bottomRef} />
    </section>
  );
}
