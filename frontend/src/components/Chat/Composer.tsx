import { useCallback, useState, type FormEvent } from "react";
import { useI18n } from "../../hooks/useI18n";

interface Props {
  onSend: (query: string) => void | Promise<void>;
  disabled?: boolean;
}

/**
 * Query composer. Ctrl/Cmd+Enter submits. Disabled while streaming
 * so clinicians don't stack queries on a server already mid-stream.
 */
export function Composer({ onSend, disabled = false }: Props) {
  const { t } = useI18n();
  const [value, setValue] = useState("");

  const submit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (disabled || !value.trim()) return;
      await onSend(value);
      setValue("");
    },
    [disabled, onSend, value],
  );

  return (
    <form
      onSubmit={submit}
      className="flex items-end gap-2 border-t border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900"
    >
      <label htmlFor="composer-textarea" className="sr-only">
        {t("chat.placeholder")}
      </label>
      <textarea
        id="composer-textarea"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            void submit(e as unknown as FormEvent);
          }
        }}
        placeholder={t("chat.placeholder")}
        rows={2}
        disabled={disabled}
        maxLength={4000}
        className="flex-1 resize-none rounded-md border border-slate-300 bg-white p-2 text-sm text-slate-900 focus:border-clinical-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded-md bg-clinical-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {disabled ? t("chat.sending") : t("chat.send")}
      </button>
    </form>
  );
}
