import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },

  server: {
    port: 5173,
    proxy: {
      "/api": {
        target:     "http://localhost:8000",
        changeOrigin: true,
        rewrite:    (path) => path.replace(/^\/api/, ""),
      },
      "/ws": {
        target:     "ws://localhost:8000",
        ws:         true,
        changeOrigin: true,
      },
    },
  },

  build: {
    outDir:          "dist",
    sourcemap:       false,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react":   ["react", "react-dom"],
          "vendor-three":   ["three", "@react-three/fiber", "@react-three/drei"],
          "vendor-charts":  ["recharts"],
          "vendor-zustand": ["zustand"],
        },
      },
    },
  },
});
