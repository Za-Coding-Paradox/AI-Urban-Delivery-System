import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],

  resolve: {
    alias: {
      // Lets you write: import { foo } from "@/store/sim"
      // instead of:     import { foo } from "../../store/sim"
      // The "@" alias always resolves from src/ regardless of file depth.
      "@": path.resolve(__dirname, "./src"),
    },
  },

  server: {
    port: 5173,

    proxy: {
      // REST API — any request to /api/* is forwarded to the FastAPI server.
      // The frontend calls fetch("/api/profiles") and Vite rewrites it to
      // http://localhost:8000/profiles before sending.
      // rewrite strips the /api prefix because the backend routes don't have it.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },

      // WebSocket — the frontend connects to ws://localhost:5173/ws/...
      // Vite forwards it to ws://localhost:8000/ws/...
      // ws: true tells Vite this is a WebSocket upgrade, not a regular HTTP request.
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
