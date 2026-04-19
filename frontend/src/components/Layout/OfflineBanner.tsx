import { useOnline } from "../../hooks/useOnline";
import { useI18n } from "../../hooks/useI18n";

export function OfflineBanner() {
  const online = useOnline();
  const { t } = useI18n();

  if (online) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-warn-500 px-4 py-2 text-center text-sm text-white"
    >
      {t("offline.banner")}
    </div>
  );
}
