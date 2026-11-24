/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Django API has no /api prefix of its own (it serves /products/, /auth/login, ...),
// so the frontend calls /api/* and the dev server strips the prefix. Same origin,
// so no CORS setup is needed. nginx does the same in the Docker image.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      // Invoice PDFs. Django serves /media only with DEBUG on (local runserver); the
      // Docker stack serves them from nginx instead.
      "/media": { target: API_TARGET },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
