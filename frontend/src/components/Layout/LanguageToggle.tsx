import { useI18n } from "../../hooks/useI18n";

export function LanguageToggle() {
  const { locale, setLocale, t } = useI18n();
  const next = locale === "en" ? "sw" : "en";

  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      aria-label={t("language.toggle")}
      className="rounded px-2 py-1 text-xs font-medium text-clinical-700 hover:bg-clinical-50 dark:text-clinical-50 dark:hover:bg-slate-700"
    >
      {locale === "en" ? t("language.sw") : t("language.en")}
    </button>
  );
}
