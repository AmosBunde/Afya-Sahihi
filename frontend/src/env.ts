/**
 * Typed access to VITE_* env vars. Keep string-coercion in one place
 * so components don't re-derive booleans from "true"/"false" strings.
 */

const env = import.meta.env;

function bool(raw: string | boolean | undefined, fallback: boolean): boolean {
  if (typeof raw === "boolean") return raw;
  if (raw === undefined || raw === "") return fallback;
  return raw === "true" || raw === "1";
}

function num(raw: string | number | undefined, fallback: number): number {
  if (typeof raw === "number") return raw;
  if (raw === undefined || raw === "") return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export const config = {
  appName: env.VITE_APP_NAME ?? "Afya Sahihi",
  appVersion: env.VITE_APP_VERSION ?? "0.0.1",
  apiBaseUrl: env.VITE_API_BASE_URL ?? "/api",
  sseReconnectDelayMs: num(env.VITE_SSE_RECONNECT_DELAY_MS, 3000),
  defaultLocale: (env.VITE_DEFAULT_LOCALE ?? "en") as "en" | "sw",
  availableLocales: (env.VITE_AVAILABLE_LOCALES ?? "en,sw").split(",") as (
    | "en"
    | "sw"
  )[],
  features: {
    conformalSets: bool(env.VITE_FEATURE_CONFORMAL_SETS, true),
    provenancePanel: bool(env.VITE_FEATURE_PROVENANCE_PANEL, true),
    citationHighlight: bool(env.VITE_FEATURE_CITATION_HIGHLIGHT, true),
    darkMode: bool(env.VITE_FEATURE_DARK_MODE, true),
    offlineBanner: bool(env.VITE_FEATURE_OFFLINE_BANNER, true),
  },
  oidc: {
    authority: env.VITE_OIDC_AUTHORITY ?? "",
    clientId: env.VITE_OIDC_CLIENT_ID ?? "",
    redirectUri: env.VITE_OIDC_REDIRECT_URI ?? "",
    scope: env.VITE_OIDC_SCOPE ?? "openid profile email",
  },
} as const;

export type AppConfig = typeof config;
