import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider, MutationCache } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from './app/App';
// //// NEOFFICE PATCH — useAuthStore needed for Frappe-embedded boot
import { useAuthStore } from '@/stores/useAuthStore';
// //// END NEOFFICE PATCH
import { useToastStore } from '@/stores/useToastStore';
import './app/i18n';
import './index.css';
// //// NEOFFICE PATCH — Brand overrides (must load after index.css so cascade wins)
import './styles/neoffice-theme-overrides.css';
// //// END NEOFFICE PATCH

// //// NEOFFICE PATCH — Frappe-embedded boot: detect mode, set basename, hydrate auth
// WHY: When the SPA boots inside /neoconstruction/* (Frappe Desk page), we need to:
//   1. Pose window.__FRAPPE_INTEGRATION__ flag → drives Layout swap + auth bypass in App.tsx
//   2. Set BrowserRouter basename="/neoconstruction" → routes match correctly
//   3. Hydrate useAuthStore with isAuthenticated=true so RequireAuth lets us through
//      WITHOUT going through OCE /login (Frappe is the source of truth here —
//      _enforce_access() in www/neoconstruction.py has already validated).
//   4. Inject window.oce_jwt as the access token so api.ts intercepts /api/v1/* with Bearer.
// REVIEW: permanent (core Frappe integration). Upstream PR would expose a
// boot config hook that does all this declaratively.
interface FrappeWindow {
  frappe?: { boot?: { user?: { email?: string; name?: string } } };
  oce_jwt?: string | null;
  __FRAPPE_INTEGRATION__?: boolean;
  __FRAPPE_BASENAME__?: string;
}
const _w = window as unknown as FrappeWindow;
// Sticky + multi-signal detection: respect the flag already posted by the
// Jinja template, fall back to positive signals (frappe.boot / oce_jwt /
// URL path) when running without a template.
const FRAPPE_INTEGRATION =
  _w.__FRAPPE_INTEGRATION__ === true ||
  Boolean(_w.frappe?.boot) ||
  Boolean(_w.oce_jwt) ||
  (typeof window !== 'undefined' && window.location.pathname.startsWith('/neoconstruction'));
_w.__FRAPPE_INTEGRATION__ = FRAPPE_INTEGRATION;
_w.__FRAPPE_BASENAME__ = FRAPPE_INTEGRATION ? '/neoconstruction' : '/';

if (FRAPPE_INTEGRATION) {
  // In Frappe-embedded mode we TRUST the Frappe session: _enforce_access()
  // on the controller side has already validated (guest → /login Frappe,
  // role missing → 403). If we're here, the user is legitimate.
  // The OCE JWT may be absent (provisioning failed, OCE down) — a later
  // 401 triggers get_oce_jwt to refresh.
  if (_w.oce_jwt) {
    // Persist in sessionStorage so loadFromStorage() in App.tsx picks it up
    // (constant KEY_ACCESS = 'oe_access_token' in useAuthStore).
    sessionStorage.setItem('oe_access_token', _w.oce_jwt);
  }
  const frappeUser = _w.frappe?.boot?.user;
  const email = frappeUser?.email ?? frappeUser?.name ?? null;
  if (email) {
    localStorage.setItem('oe_user_email', email);
  }
  useAuthStore.setState({
    accessToken: _w.oce_jwt ?? null,
    isAuthenticated: true,  // ALWAYS true in Frappe-embedded mode
    userEmail: email,
    userRole: null,
  });
}

const __routerBasename = FRAPPE_INTEGRATION ? '/neoconstruction' : undefined;
// //// END NEOFFICE PATCH

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
    onError: (error, _variables, _context, mutation) => {
      const message = error instanceof Error ? error.message : 'Operation failed';
      // Auth-related failures redirect via api.ts; surfacing them again
      // produces noisy stack traces in the console for anon flows
      // (login/register) where 401 is the expected branch.
      const status = (error as { status?: number } | null)?.status;
      const isAuthFailure = status === 401 || status === 403 || message.includes('401');
      // Per-mutation opt-out: mutations that already surface their own
      // contextual error toast (e.g. PermissionsMatrixPage's "Update
      // failed") should set ``meta: { suppressGlobalErrorToast: true }``
      // so the user does not see two stacked toasts for the same failure.
      const suppress = Boolean(
        (mutation?.meta as { suppressGlobalErrorToast?: boolean } | undefined)
          ?.suppressGlobalErrorToast,
      );
      if (!isAuthFailure && !suppress) {
        if (import.meta.env.DEV) console.warn('Mutation error:', message);
        useToastStore.getState().addToast({
          type: 'error',
          title: 'Operation failed',
          message,
        });
      }
    },
  }),
});

// Stamp the root element with an origin token. Survives in the live DOM
// and any saved-page snapshot — looks like a deterministic build id.
// Decodes to "DDC-CWICR-OE-2026" by reversing the hex.
const __rootEl = document.getElementById('root')!;
__rootEl.setAttribute(
  'data-build-rev',
  '4443432d4357494352-4f452d32303236',
);

ReactDOM.createRoot(__rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* //// NEOFFICE PATCH — Pass basename when Frappe-embedded */}
      <BrowserRouter basename={__routerBasename} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </BrowserRouter>
      {/* //// END NEOFFICE PATCH */}
    </QueryClientProvider>
  </React.StrictMode>,
);
