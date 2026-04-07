import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { writeFileSync, readFileSync } from "fs";

// Plugin para crear 200.html (Render SPA fallback)
function renderSpaFallback() {
  return {
    name: "render-spa-fallback",
    closeBundle() {
      try {
        const index = readFileSync("dist/index.html", "utf-8");
        writeFileSync("dist/200.html", index);
      } catch { /* ignore if dist doesn't exist yet */ }
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), renderSpaFallback()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://localhost:8000",
        changeOrigin: true,
        timeout: 300000,       // 5 min — suficiente para análisis IA con Ollama
      },
    },
  },
});
