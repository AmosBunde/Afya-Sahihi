import clsx from "clsx";
import type { ChatMessage } from "../../types/chat";
import { PredictionSet } from "../Conformal/PredictionSet";
import { ProvenancePanel } from "../Provenance/ProvenancePanel";
import { useI18n } from "../../hooks/useI18n";

interface Props {
  message: ChatMessage;
}

/**
 * Single message bubble. Assistant messages are keyed off status:
 * streaming shows a cursor, complete shows the full content plus the
 * conformal set and provenance panel, error shows a refusal notice.
 */
export function Message({ message }: Props) {
  const { t } = useI18n();
  const isUser = message.role === "user";

  return (
    <article
      className={clsx(
        "flex flex-col gap-2 rounded-lg p-3 text-sm",
        isUser
          ? "self-end bg-clinical-600 text-white"
          : "self-start bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100",
      )}
      aria-live={message.status === "streaming" ? "polite" : undefined}
      aria-label={isUser ? undefined : t("a11y.newMessage")}
    >
      <p className="whitespace-pre-wrap break-words">
        {message.content}
        {message.status === "streaming" && (
          <span className="ml-0.5 inline-block animate-pulse" aria-hidden>
            ▍
          </span>
        )}
      </p>

      {message.status === "error" && (
        <p className="rounded bg-danger-500/10 p-2 text-xs text-danger-700">
          {message.errorKind === "PrefilterRejected" ||
          message.errorKind === "StrictReviewRejected"
            ? t("chat.refused")
            : t("chat.error")}
        </p>
      )}

      {message.conformal && <PredictionSet set={message.conformal} />}

      {message.citations && message.citations.length > 0 && (
        <ProvenancePanel citations={message.citations} />
      )}
    </article>
  );
}
