import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      // Forward API calls to the FastAPI backend so the frontend can use
      // relative "/api/v1" URLs without CORS gymnastics.
      "/api": {
        target: "http://localhost:8010",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    exclude: [...configDefaults.exclude, "e2e/**"],
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});
