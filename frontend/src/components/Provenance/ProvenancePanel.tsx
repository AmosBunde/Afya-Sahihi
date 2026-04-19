import type { Citation } from "../../types/provenance";
import { useI18n } from "../../hooks/useI18n";

interface Props {
  citations: readonly Citation[];
  onSelect?: (citation: Citation) => void;
}

/**
 * Right-rail provenance panel. Each citation is a button; clicking it
 * either opens the PDF viewer in a new tab or calls `onSelect` for
 * the parent to render an inline viewer. Screen readers get a full
 * label via aria-label including the document title and page.
 */
export function ProvenancePanel({ citations, onSelect }: Props) {
  const { t } = useI18n();

  if (citations.length === 0) {
    return null;
  }

  return (
    <aside
      aria-label={t("provenance.title")}
      className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-800"
    >
      <h3 className="text-sm font-semibold">{t("provenance.title")}</h3>
      <ul className="flex flex-col gap-2">
        {citations.map((citation) => (
          <li key={citation.chunk_id}>
            <button
              type="button"
              onClick={() => onSelect?.(citation)}
              aria-label={t("a11y.citationLink", {
                title: citation.document_title,
                page: citation.bounding_box.page,
              })}
              className="w-full rounded-md px-2 py-1 text-left text-clinical-700 hover:bg-clinical-50 focus:bg-clinical-50 dark:text-clinical-50 dark:hover:bg-slate-700"
            >
              <span className="block truncate font-medium">
                {citation.document_title}
              </span>
              <span className="block text-xs text-slate-600 dark:text-slate-300">
                {t("provenance.page", { page: citation.bounding_box.page })}
                {citation.section_path.length > 0
                  ? ` · ${citation.section_path.join(" › ")}`
                  : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
