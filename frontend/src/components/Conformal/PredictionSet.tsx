import type { ConformalSet } from "../../types/conformal";
import { useI18n } from "../../hooks/useI18n";

interface Props {
  set: ConformalSet;
}

/**
 * Renders the prediction set. "Top answer" is the argmax; "also
 * consider" lists the within-set alternatives. Coverage is shown as
 * the integer percentage (90% not 0.9) because that is what
 * clinicians asked for in design review — the decimals read as noise.
 */
export function PredictionSet({ set }: Props) {
  const { t } = useI18n();
  const coveragePct = Math.round(set.target_coverage * 100);

  return (
    <section
      className="rounded-md border border-clinical-700 bg-clinical-50 p-3 dark:bg-slate-800 dark:border-clinical-700"
      aria-label="Prediction set"
    >
      <h3 className="text-sm font-semibold text-clinical-900 dark:text-clinical-50">
        {t("conformal.top_answer")}
      </h3>
      <p className="mt-1 text-base text-slate-900 dark:text-slate-100">
        {set.top_answer}
      </p>

      {set.also_consider.length > 0 && (
        <>
          <h4 className="mt-3 text-xs font-medium text-slate-600 dark:text-slate-300">
            {t("conformal.also_consider", { coverage: coveragePct })}
          </h4>
          <ul className="mt-1 space-y-1 text-sm text-slate-700 dark:text-slate-200">
            {set.also_consider.map((alt) => (
              <li
                key={alt}
                className="before:mr-2 before:text-clinical-700 before:content-['•']"
              >
                {alt}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
