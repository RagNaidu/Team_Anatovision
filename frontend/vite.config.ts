import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Development: /api is proxied to the FastAPI backend, so the browser sees ONE origin and the session cookie just works.
// changeOrigin stays false so the Origin/Host pair still matches (the API refuses cross-site writes).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { port: 5173, proxy: { "/api": { target: process.env.VITE_API_PROXY ?? "http://localhost:8000", changeOrigin: false } } },
  preview: { port: 5173, proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } } },
});
