# Afya Sahihi — Frontend

React 19 + Vite + Tanstack Query + Tailwind. Clinician chat UI with SSE streaming, provenance panel, prediction-set display, dark/light theme, English/Swahili toggle, and offline banner.

## Develop

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173
```

## Build

```bash
npm run build
# output in dist/; served by nginx in the container image.
```

## Test

```bash
npm run test        # vitest, one-shot
npm run test:watch  # vitest, watch mode
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
```

## Architecture

- `src/App.tsx` — root layout (offline banner + header + chat area).
- `src/components/Chat/` — compose/send, streamed message list.
- `src/components/Conformal/PredictionSet.tsx` — top-answer + also-consider render.
- `src/components/Provenance/ProvenancePanel.tsx` — citation list with keyboard-accessible buttons.
- `src/hooks/useSseChat.ts` — SSE stream consumer; fetch + ReadableStream (not EventSource because we need a POST body + Bearer).
- `src/hooks/useI18n.ts` — minimal i18n, localStorage-persisted locale.
- `src/hooks/useTheme.ts` — localStorage-persisted + prefers-color-scheme fallback.

## Performance targets (from issue #35)

- Lighthouse > 90 on throttled Moto G4.
- First-token-visible under 2s on staging.
- Manual chunking in `vite.config.ts` splits React + Tanstack into separate chunks so the main bundle can stream paint.

## Accessibility

- Every interactive element has a visible focus ring (`src/index.css` sets outline and ring).
- Message list uses `role="log"` + `aria-live="polite"` so screen readers announce streamed assistant text.
- Provenance buttons carry descriptive `aria-label` with the document title and page number.
- Language attribute on `<html>` updates when the user toggles locale (for screen reader pronunciation).
