import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Keep the bundle tight — the target platform is a Moto G4 on a
// throttled mobile network, and every KB counts against the
// first-token-visible budget.
export default defineConfig({
  plugins: [react()],
  build: {
    target: "es2022",
    sourcemap: true,
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    coverage: {
      reporter: ["text", "lcov"],
    },
  },
});
