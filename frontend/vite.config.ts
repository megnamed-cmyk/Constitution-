import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server proxies /api to FastAPI, so the browser sees one origin (no CORS, no hardcoded port).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.API_URL ?? 'http://localhost:8000', changeOrigin: true } },
  },
});
