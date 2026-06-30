/**
 * NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OCE.
 *
 * Layout utilisé quand le SPA tourne embarqué dans Frappe (/neoconstruction/*).
 *
 * Now delegates to the shared NeoCockpit chrome (bvisible/frappe-sidebar-react):
 * one sidebar that absorbs the header, gray frame + floating white panel around
 * the content. Replaces the old copy-pasted FrappeSidebar.tsx + FrappeNavbar.tsx
 * (deleted — they were the genesis of the now-superseded copy-paste pattern).
 * NeoCockpit reads window.frappe.boot (the curated mini-boot) and navigates via
 * window.location.href (env="spa").
 *
 * Le flag `__FRAPPE_INTEGRATION__` dans window est posé par main.tsx. Si absent,
 * AppLayout natif reste utilisé (cas du dev server vite standalone).
 */
import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { NeoCockpit } from '@neoffice/frappe-sidebar-react';
import { resolvePageTitleKey } from './Header';

interface FrappeLayoutProps {
  title?: string;
  children: ReactNode;
}

export function FrappeLayout({ title, children }: FrappeLayoutProps) {
  const { t, i18n } = useTranslation();

  useEffect(() => {
    // Translate the browser-tab title through the same map the on-screen page
    // heading uses (e.g. "BOQ Editor" -> "Éditeur de devis"), so the embedded
    // tab follows the active language instead of leaking raw English. Mirrors
    // AppLayout's title handling.
    const key = resolvePageTitleKey(title);
    const translated = title ? (key ? t(key, { defaultValue: title }) : title) : null;
    document.title = translated ? `${translated} | Construction` : 'Construction';
    // i18n.language in deps so the tab re-translates on a language switch.
  }, [title, t, i18n.language]);

  return (
    // Neoconstruction surface: pin the Construction module in the menu
    <NeoCockpit env="spa" defaultApp="neoconstruction">
      <div className="page-content">{children}</div>
    </NeoCockpit>
  );
}
