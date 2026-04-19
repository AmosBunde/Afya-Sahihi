import { config } from "../../env";
import { useI18n } from "../../hooks/useI18n";
import { LanguageToggle } from "./LanguageToggle";
import { ThemeToggle } from "./ThemeToggle";

export function Header() {
  const { t } = useI18n();
  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
      <div>
        <h1 className="text-lg font-semibold text-clinical-900 dark:text-clinical-50">
          {t("app.title")}
        </h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {t("app.tagline")} · v{config.appVersion}
        </p>
      </div>
      <nav className="flex items-center gap-1" aria-label="Site controls">
        <LanguageToggle />
        <ThemeToggle />
      </nav>
    </header>
  );
}
