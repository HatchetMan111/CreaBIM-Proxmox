import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Der Build landet direkt im Backend, damit FastAPI die SPA unter "/" ausliefert.
// `base: './'` ist Pflicht: die Assets werden relativ eingebunden, damit die
// Auslieferung auch unter einem Reverse-Proxy-Unterpfad funktioniert.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: '../app/backend/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8031',
    },
  },
});