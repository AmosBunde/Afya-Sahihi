import { useTheme } from "../../hooks/useTheme";
import { useI18n } from "../../hooks/useI18n";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const { t } = useI18n();

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={t("theme.toggle")}
      aria-pressed={theme === "dark"}
      className="rounded px-2 py-1 text-xs font-medium text-clinical-700 hover:bg-clinical-50 dark:text-clinical-50 dark:hover:bg-slate-700"
    >
      {theme === "dark" ? t("theme.light") : t("theme.dark")}
    </button>
  );
}
