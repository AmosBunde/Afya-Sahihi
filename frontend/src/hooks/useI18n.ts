import { useCallback, useEffect, useState } from "react";
import { config } from "../env";
import en from "../i18n/en.json";
import sw from "../i18n/sw.json";

type Locale = "en" | "sw";
type Bundle = Record<string, string>;

const bundles: Record<Locale, Bundle> = { en, sw };

const STORAGE_KEY = "afya-sahihi.locale";

function format(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = vars[key];
    return value === undefined ? `{${key}}` : String(value);
  });
}

function loadLocale(): Locale {
  const stored = globalThis.localStorage?.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "sw") return stored;
  return config.defaultLocale;
}

export function useI18n() {
  const [locale, setLocaleState] = useState<Locale>(loadLocale);

  useEffect(() => {
    globalThis.localStorage?.setItem(STORAGE_KEY, locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const bundle = bundles[locale];
      const value = bundle[key];
      if (value === undefined) {
        // Fall through to English rather than show the raw key; log in dev.
        return format(en[key as keyof typeof en] ?? key, vars);
      }
      return format(value, vars);
    },
    [locale],
  );

  return { locale, setLocale: setLocaleState, t };
}
