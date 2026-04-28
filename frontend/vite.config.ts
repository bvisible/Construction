/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import path from 'path';
import { readFileSync } from 'fs';

// Read the version from package.json once at build time so the entire app
// (sidebar, About page, error reports, update checker) stays in sync.
const pkg = JSON.parse(readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'));

// Frappe integration: when building for the Frappe `neoconstruction` app, the
// bundle is served under /assets/neoconstruction/neoconstruction/. Enable with
// FRAPPE_BUILD=1 ; override FRAPPE_OUT_DIR to point at a different checkout
// of the neoconstruction repo.
const FRAPPE_BUILD = process.env.FRAPPE_BUILD === '1';
const FRAPPE_OUT_DIR =
  process.env.FRAPPE_OUT_DIR ||
  path.resolve(__dirname, '../../neoconstruction/neoconstruction/public/neoconstruction');

export default defineConfig({
  base: FRAPPE_BUILD ? '/assets/neoconstruction/neoconstruction/' : '/',
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  plugins: [
    react(),
    visualizer({
      filename: 'stats.html',
      gzipSize: true,
      brotliSize: true,
      open: false,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 300000,
      },
    },
  },
  build: {
    outDir: FRAPPE_BUILD ? FRAPPE_OUT_DIR : 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Vendor chunks
          if (id.includes('node_modules/react-dom/')) return 'vendor-react';
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-router-dom/')) return 'vendor-react';
          if (id.includes('node_modules/ag-grid-')) return 'vendor-ag-grid';
          if (id.includes('node_modules/@tanstack/react-query')) return 'vendor-query';
          if (id.includes('node_modules/i18next') || id.includes('node_modules/react-i18next') || id.includes('node_modules/i18next-browser-languagedetector') || id.includes('node_modules/i18next-http-backend')) return 'vendor-i18n';
          if (id.includes('node_modules/pdfjs-dist')) return 'vendor-pdf';
          if (id.includes('node_modules/yjs') || id.includes('node_modules/y-webrtc')) return 'vendor-collab';
          if (id.includes('node_modules/jspdf') || id.includes('node_modules/html2canvas')) return 'vendor-charts';
          // i18n fallback translations — separate chunk (~2MB of translation data)
          if (id.includes('i18n-fallbacks')) return 'i18n-data';
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
