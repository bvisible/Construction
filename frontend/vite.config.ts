/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import path from 'path';
import { readFileSync } from 'fs';

// Read the version from package.json once at build time so the entire app
// (sidebar, About page, error reports, update checker) stays in sync.
const pkg = JSON.parse(readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'));

// //// NEOFFICE PATCH — Frappe build mode
// WHY: When building for the Frappe `neoconstruction` app, the bundle is
// served under /assets/neoconstruction/neoconstruction/ (not from /). Set
// FRAPPE_BUILD=1 to switch the public base + redirect output into the
// neoconstruction/ checkout. FRAPPE_OUT_DIR can override the target dir.
// REVIEW: permanent — this is how the SPA gets embedded in Frappe.
const FRAPPE_BUILD = process.env.FRAPPE_BUILD === '1';
const FRAPPE_OUT_DIR =
  process.env.FRAPPE_OUT_DIR ||
  path.resolve(__dirname, '../../neoconstruction/neoconstruction/public/neoconstruction');
// //// END NEOFFICE PATCH

export default defineConfig({
  // //// NEOFFICE PATCH — Frappe build base path
  base: FRAPPE_BUILD ? '/assets/neoconstruction/neoconstruction/' : '/',
  // //// END NEOFFICE PATCH
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
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 300000,
      },
    },
  },
  // Pre-bundle heavy deps that are imported lazily by route-level chunks.
  // Without this, Vite discovers them only when the chunk first loads and
  // triggers a "504 Outdated Optimize Dep" on the in-flight import — which
  // surfaces as "Failed to fetch dynamically imported module" on the takeoff
  // and BIM pages.  Including them up-front keeps the version hash stable
  // across the dev session.
  optimizeDeps: {
    include: [
      'pdfjs-dist',
      'pdfjs-dist/build/pdf.worker.min.mjs',
      'three',
      // High-risk: heavy deps reached only via lazy route chunks.  Without
      // pre-bundling, Vite discovers them mid-navigation and the in-flight
      // import 504s with "Failed to fetch dynamically imported module".
      'ag-grid-react',
      'ag-grid-community',
      'recharts',
      'jspdf',
      'jspdf-autotable',
      'maplibre-gl',
      'react-map-gl/maplibre',
      'exceljs',
      'yjs',
      'y-websocket',
      'y-webrtc',
      '@xyflow/react',
      '@dnd-kit/core',
      '@dnd-kit/sortable',
      '@dnd-kit/utilities',
    ],
  },
  build: {
    // //// NEOFFICE PATCH — Frappe build output dir
    // WHY: redirect Vite output into the neoconstruction/ Frappe app
    // public folder so `bench build` picks up the new assets.
    outDir: FRAPPE_BUILD ? FRAPPE_OUT_DIR : 'dist',
    emptyOutDir: true,
    // //// END NEOFFICE PATCH
    rollupOptions: {
      output: {
        manualChunks(id) {
          // i18n locales: each ``src/app/locales/<code>.ts`` is fetched
          // on demand via dynamic import in ``i18n.ts``. Vite emits one
          // chunk per locale automatically; pin a stable name so cache
          // keys survive minor unrelated edits.  Checked first because
          // these are source files, not node_modules (the guard below
          // would otherwise skip them).
          const localeMatch = id.match(/[\\/]src[\\/]app[\\/]locales[\\/]([a-z]{2})\.ts$/);
          if (localeMatch) return `i18n-${localeMatch[1]}`;
          if (!id.includes('node_modules')) return;
          // ── Heavy, route-only vendors → dedicated async chunks ───────
          // These libraries are only reached through `lazy()` route
          // chunks (BOQ editor, dashboard map, PDF/DWG takeoff, Excel
          // export, flow editor).  Pinning each to its own chunk keeps
          // them OUT of the initial `index` chunk and lets multiple
          // routes share a single cached copy instead of duplicating the
          // payload per route chunk (V320-PERF-01).  Order: most specific
          // first; map rule before any generic react rule so the
          // `react-map-gl` adapter rides with maplibre, not vendor-react.
          if (id.includes('node_modules/exceljs')) return 'vendor-exceljs';
          if (
            id.includes('node_modules/maplibre-gl') ||
            id.includes('node_modules/react-map-gl')
          )
            return 'vendor-maplibre';
          if (id.includes('node_modules/ag-grid-')) return 'vendor-ag-grid';
          if (id.includes('node_modules/recharts') || id.includes('node_modules/d3-'))
            return 'vendor-recharts';
          if (id.includes('node_modules/@xyflow/')) return 'vendor-flow';
          if (id.includes('node_modules/@dnd-kit/')) return 'vendor-dnd';
          if (id.includes('node_modules/three')) return 'vendor-three';
          if (id.includes('node_modules/pdfjs-dist')) return 'vendor-pdf';
          // jsPDF + html2canvas (PDF report export) — distinct from the
          // recharts charting stack so a page that only charts doesn't
          // drag in the PDF generator and vice-versa.
          if (id.includes('node_modules/jspdf') || id.includes('node_modules/html2canvas'))
            return 'vendor-pdf-export';
          if (
            id.includes('node_modules/yjs') ||
            id.includes('node_modules/y-webrtc') ||
            id.includes('node_modules/y-websocket') ||
            id.includes('node_modules/y-protocols') ||
            id.includes('node_modules/lib0')
          )
            return 'vendor-collab';
          // ── Framework / always-loaded vendors ────────────────────────
          if (id.includes('node_modules/react-dom/')) return 'vendor-react';
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-router-dom/') || id.includes('node_modules/react-router/')) return 'vendor-react';
          if (id.includes('node_modules/@tanstack/react-query')) return 'vendor-query';
          if (id.includes('node_modules/i18next') || id.includes('node_modules/react-i18next') || id.includes('node_modules/i18next-browser-languagedetector') || id.includes('node_modules/i18next-http-backend')) return 'vendor-i18n';
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
