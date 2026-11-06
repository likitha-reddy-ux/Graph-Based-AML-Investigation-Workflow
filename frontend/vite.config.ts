import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Requests to /api/... are forwarded to the FastAPI backend on port 8000,
// so the browser only ever talks to the dashboard's own address.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
