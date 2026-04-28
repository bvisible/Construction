/**
 * Layout utilisé quand le SPA tourne embarqué dans Frappe (/neoconstruction/*).
 *
 * Frappe-pattern layout : flex-row at the root, sidebar and main as
 * siblings. Navbar lives INSIDE main (not full-width), so it starts
 * right of the sidebar and the app-switcher in the sidebar aligns
 * naturally with the logo in the navbar (same Y=0 modulo padding).
 *
 * Le flag `frappe-integration` dans window est posé par main.tsx. Si absent,
 * AppLayout natif reste utilisé (cas du dev server vite standalone).
 */
import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { FrappeSidebar } from './FrappeSidebar';
import { FrappeNavbar } from './FrappeNavbar';

interface FrappeLayoutProps {
  title?: string;
  children: ReactNode;
}

export function FrappeLayout({ title, children }: FrappeLayoutProps) {
  useEffect(() => {
    document.title = title ? `${title} | Construction` : 'Construction';
  }, [title]);

  return (
    <div
      className="frappe-desk-root"
      style={{
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'flex-start',
        minHeight: '100vh',
        width: '100%',
      }}
    >
      <FrappeSidebar />
      <main
        className="main-section"
        style={{
          flex: 1,
          height: '100vh',
          overflowY: 'auto',
          position: 'relative',
          minWidth: 0,
        }}
      >
        <FrappeNavbar />
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}
