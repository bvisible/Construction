import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider, MutationCache } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from './app/App';
import { useAuthStore } from '@/stores/useAuthStore';
import { useToastStore } from '@/stores/useToastStore';
import './app/i18n';
import './index.css';

// Frappe integration boot :
// - __FRAPPE_INTEGRATION__ est détecté via window.frappe.boot posé par le
//   template Jinja côté Frappe (neoconstruction/www/neoconstruction.html).
// - Si window.oce_jwt est fourni, on l'injecte dans l'auth store pour que
//   api.ts l'envoie comme Bearer sur les appels /api/v1/*.
interface FrappeWindow {
  frappe?: { boot?: unknown };
  oce_jwt?: string | null;
  __FRAPPE_INTEGRATION__?: boolean;
  __FRAPPE_BASENAME__?: string;
}
const _w = window as unknown as FrappeWindow;
// Sticky + multi-signal detection: respect the flag already posted by the
// Jinja template, fall back to positive signals (frappe.boot / oce_jwt /
// URL path) when running without a template. This guarantees the flag
// stays true across reloads even if frappe.boot arrives late.
const FRAPPE_INTEGRATION =
  _w.__FRAPPE_INTEGRATION__ === true ||
  Boolean(_w.frappe?.boot) ||
  Boolean(_w.oce_jwt) ||
  (typeof window !== 'undefined' && window.location.pathname.startsWith('/neoconstruction'));
_w.__FRAPPE_INTEGRATION__ = FRAPPE_INTEGRATION;
_w.__FRAPPE_BASENAME__ = FRAPPE_INTEGRATION ? '/neoconstruction' : '/';

if (FRAPPE_INTEGRATION) {
  // En mode Frappe, on FAIT CONFIANCE à la session Frappe :
  // _enforce_access() côté controller a déjà validé (guest → /login Frappe,
  // role missing → 403). Si on est ici, l'utilisateur est légitime.
  // Le JWT OCE peut être absent (provisioning échoué, OCE down) — un 401
  // ultérieur déclenchera get_oce_jwt pour rafraîchir.
  if (_w.oce_jwt) {
    // Persist en sessionStorage pour survivre au loadFromStorage() du App.tsx
    // (constante KEY_ACCESS = 'oe_access_token' dans useAuthStore).
    sessionStorage.setItem('oe_access_token', _w.oce_jwt);
  }
  const frappeUser = (_w.frappe?.boot as { user?: { email?: string; name?: string } } | undefined)?.user;
  const email = frappeUser?.email ?? frappeUser?.name ?? null;
  if (email) {
    localStorage.setItem('oe_user_email', email);
  }
  useAuthStore.setState({
    accessToken: _w.oce_jwt ?? null,
    isAuthenticated: true,  // TOUJOURS true en mode Frappe embarqué
    userEmail: email,
    userRole: null,
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // 30s — data considered fresh for 30s, then refetch on focus/mount
      gcTime: 5 * 60_000, // 5min — keep in cache for 5 min after unmount
      // Offline-first: try the cache before spinning a 300s AbortController.
      // `api.ts` falls back to IndexedDB via offlineStore on network errors,
      // so we never want to retry a query that's going to fail for the same
      // reason anyway.
      networkMode: 'offlineFirst',
      retry: (count, error) => {
        if (!navigator.onLine) return false;
        // 4xx responses are deterministic — don't retry.
        if (error && typeof error === 'object' && 'status' in error) {
          const status = (error as { status: number }).status;
          if (status >= 400 && status < 500) return false;
        }
        return count < 1;
      },
      refetchOnWindowFocus: true, // refetch when user tabs back
    },
    mutations: {
      // Mutations while offline are queued by offlineStore and replayed on
      // reconnect — no need for react-query-level retry.
      networkMode: 'offlineFirst',
      retry: 0,
    },
  },
  mutationCache: new MutationCache({
    onSuccess: (_data, _variables, _context, mutation) => {
      // Global: after ANY successful mutation, invalidate related queries
      // This ensures lists refresh immediately after create/update/delete
      const key = mutation.options.mutationKey;
      if (key && Array.isArray(key) && key.length > 0) {
        queryClient.invalidateQueries({ queryKey: [key[0]] });
      }
    },
    onError: (error) => {
      console.error('Mutation error:', error);
      const message = error instanceof Error ? error.message : 'Operation failed';
      if (!message.includes('401')) {
        useToastStore.getState().addToast({
          type: 'error',
          title: 'Operation failed',
          message,
        });
      }
    },
  }),
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={_w.__FRAPPE_BASENAME__} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
