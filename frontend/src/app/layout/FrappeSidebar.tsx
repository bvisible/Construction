/**
 * FrappeSidebar — Pixel-perfect React reimplementation of the Frappe Desk
 * sidebar (`/app/home`), styled by the same CSS classes as `desk.bundle.css`
 * (.body-sidebar, .standard-sidebar-section, .sidebar-item-container...) and
 * fed by the mini-boot returned by `neoconstruction.api.boot.get_navbar_boot()`.
 *
 * Mirrors the exact DOM produced by:
 *   - frappe/public/js/frappe/ui/sidebar.html       (outer skeleton)
 *   - frappe/public/js/frappe/ui/sidebar.js         (workspace + module sections)
 *   - frappe/public/js/frappe/ui/apps_switcher.html (app switcher dropdown)
 *
 * Same approach as FrappeNavbar.tsx (commit 683e69d): we do NOT load
 * desk.bundle.js, so we render React markup that mimics the markup Frappe
 * itself would produce, and we let neoffice_theme CSS take care of styling.
 *
 * The hover-expand behaviour (collapsed by default, overlay-expand on hover)
 * is normally injected at runtime by neoffice-theme.js. Since we don't load
 * that bundle either, the equivalent CSS rules are added in
 * neoconstruction/scripts/sync-html.py inside a <style> tag.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FC } from 'react';

interface SidebarPage {
  name: string;
  title: string;
  label?: string;
  public?: number | boolean;
  parent_page?: string | null;
  icon?: string;
  indicator_color?: string;
  sequence_id?: number;
  is_hidden?: number;
  app?: string;
  module?: string;
}

interface AppEntry {
  app_name: string;
  app_title: string;
  app_logo_url?: string;
  app_route?: string;
  workspaces?: string[];
  sort_order?: number;
}

interface SidebarBoot {
  app_data?: AppEntry[];
  app_logo_url?: string;
  sidebar_pages?: { pages?: SidebarPage[] };
  allowed_workspaces?: SidebarPage[];
  workspace_to_app_map?: Record<string, string>;
  module_app?: Record<string, string>;
}

const slugify = (s: string): string =>
  s.toLowerCase().replace(/\s+/g, '-').replace(/[()&]/g, '');

const FALLBACK_LOGO = '/assets/neoffice_theme/images/neoffice_logo.svg';

export const FrappeSidebar: FC = () => {
  const boot = (typeof window !== 'undefined'
    ? ((window as unknown as { frappe?: { boot?: SidebarBoot } }).frappe?.boot)
    : undefined);

  // Pinned (persistent) state — `sidebar_expanded` matches the localStorage
  // key shape used by neoffice_theme so a Desk session and our SPA stay in
  // sync if the user toggles either.
  const [expanded, setExpanded] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    const v = window.localStorage.getItem('sidebar_expanded');
    return v === 'true';
  });
  const togglePin = () => {
    setExpanded((prev) => {
      const next = !prev;
      window.localStorage.setItem('sidebar_expanded', String(next));
      return next;
    });
  };

  // Hover-expand state — temporary overlay on mouseenter (with 100ms debounce).
  const [hoverExpanded, setHoverExpanded] = useState(false);
  const hoverTimerRef = useRef<number | null>(null);

  const onMouseEnter = () => {
    if (expanded) return; // already pinned, no-op
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
    }
    hoverTimerRef.current = window.setTimeout(() => {
      setHoverExpanded(true);
    }, 100);
  };

  const onMouseLeave = () => {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    setHoverExpanded(false);
  };

  useEffect(() => {
    return () => {
      if (hoverTimerRef.current !== null) {
        window.clearTimeout(hoverTimerRef.current);
      }
    };
  }, []);

  // App switcher dropdown
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const sidebarRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!sidebarRef.current?.contains(e.target as Node)) {
        setSwitcherOpen(false);
      }
    };
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  // Resolve apps + current app
  const apps: AppEntry[] = useMemo(() => boot?.app_data || [], [boot]);
  const sortedApps = useMemo(
    () =>
      [...apps].sort((a, b) => {
        const sa = a.sort_order ?? 999;
        const sb = b.sort_order ?? 999;
        if (sa !== sb) return sa - sb;
        return (a.app_title || a.app_name).localeCompare(b.app_title || b.app_name);
      }),
    [apps],
  );

  // Pick the "current" app:
  //   1. The app that has the most workspaces (heuristic from sidebar.js
  //      `set_default_app` when no route match is available).
  //   2. Fallback to the first sorted app.
  //   3. Fallback to a synthetic "Workspaces" entry.
  const currentApp: AppEntry = useMemo(() => {
    const fallback: AppEntry = {
      app_name: 'frappe',
      app_title: 'Workspaces',
      app_logo_url: boot?.app_logo_url || FALLBACK_LOGO,
      app_route: '/app',
      sort_order: 999,
    };
    if (apps.length === 0) return fallback;
    const byWsCount = [...apps].sort(
      (a, b) => (b.workspaces?.length || 0) - (a.workspaces?.length || 0),
    );
    return byWsCount[0] ?? apps[0] ?? fallback;
  }, [apps, boot]);

  const allPages: SidebarPage[] = useMemo(
    () => boot?.sidebar_pages?.pages || boot?.allowed_workspaces || [],
    [boot],
  );

  // Visible workspaces for the current app (parents only, non-hidden).
  // Mirrors `make_sidebar` in frappe/public/js/frappe/ui/sidebar.js:
  //   - parent_pages = pages where !parent_page
  //   - if currentApp === 'private': only private (non-public) pages
  //   - else: only public pages whose name is in currentApp.workspaces
  const visibleWorkspaces = useMemo(() => {
    const parents = allPages.filter((p) => !p.parent_page && !p.is_hidden);
    if (currentApp.app_name === 'private') {
      return parents.filter((p) => !p.public);
    }
    const appWs = currentApp.workspaces || [];
    if (appWs.length === 0) {
      // Fallback: show top 20 public workspaces (avoids empty sidebar when
      // app_data is sparse — same defensive behaviour as the legacy package).
      return parents.filter((p) => p.public).slice(0, 20);
    }
    return parents.filter((p) => p.public && appWs.includes(p.name));
  }, [allPages, currentApp]);

  // Active workspace — derived from current URL pathname `/app/<slug>`.
  const activeWorkspace = useMemo(() => {
    if (typeof window === 'undefined') return '';
    const match = window.location.pathname.match(/^\/app\/([^/?#]+)/);
    if (!match) return '';
    const slug = match[1];
    const found = allPages.find((p) => slugify(p.name) === slug);
    return found?.name || '';
  }, [allPages]);

  // Bail out if boot is missing (e.g. dev server without Frappe).
  if (!boot) return null;

  const containerClass = [
    'body-sidebar-container',
    expanded ? 'expanded' : '',
    hoverExpanded ? 'hover-expanded' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const navigateApp = (e: React.MouseEvent, app: AppEntry) => {
    e.preventDefault();
    if (app.app_route) {
      window.location.href = app.app_route;
    }
  };

  const renderWorkspaceIcon = (ws: SidebarPage) => {
    if (ws.icon) {
      return (
        <svg className="icon icon-md">
          <use href={`#icon-${ws.icon}`} />
        </svg>
      );
    }
    return <span className={`indicator ${ws.indicator_color || 'gray'}`} />;
  };

  return (
    <div
      ref={sidebarRef}
      className={containerClass}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="body-sidebar-placeholder" />
      <div className="body-sidebar">
        {/* App switcher button (always visible at the top) */}
        <a
          className="app-switcher-dropdown"
          style={{ textDecoration: 'none', cursor: 'pointer' }}
          onClick={(e) => {
            e.stopPropagation();
            setSwitcherOpen((o) => !o);
          }}
        >
          <div className="standard-sidebar-item">
            <div className="d-flex">
              <div className="sidebar-item-icon app-logo-container">
                <img
                  className="app-logo"
                  src={currentApp.app_logo_url || boot.app_logo_url || FALLBACK_LOGO}
                  alt={currentApp.app_title}
                />
              </div>
              <div className="sidebar-item-label app-title" style={{ marginLeft: 10 }}>
                <div className="app-title-name">{currentApp.app_title}</div>
                <div className="app-title-subtitle">Active Module</div>
              </div>
            </div>
            <div className="sidebar-item-control">
              <button
                className="btn-reset drop-icon show-in-edit-mode"
                aria-label="Open app switcher"
              >
                <svg
                  className="es-icon es-line icon-sm"
                  style={{ display: 'block', margin: 'auto' }}
                  aria-hidden="true"
                >
                  <use href="#es-line-down" />
                </svg>
              </button>
            </div>
          </div>
        </a>

        {/* App switcher menu (controlled by switcherOpen state). The class
            `show` matches the legacy CSS that flips visibility/display. */}
        <div className={`app-switcher-menu ${switcherOpen ? 'show' : 'hidden'}`} role="menu">
          {sortedApps.map((app) => (
            <div
              key={app.app_name}
              className={`app-item ${currentApp.app_name === app.app_name ? 'active' : ''}`}
              data-app-name={app.app_name}
              data-app-route={app.app_route}
            >
              <a
                href={app.app_route || '/app'}
                onClick={(e) => navigateApp(e, app)}
                style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px' }}
              >
                <div className="sidebar-item-icon">
                  <img
                    className="app-logo"
                    src={app.app_logo_url || FALLBACK_LOGO}
                    alt={app.app_title}
                    style={{ width: 20, height: 20, objectFit: 'contain' }}
                  />
                </div>
                <span className="app-item-title">{app.app_title}</span>
              </a>
            </div>
          ))}
        </div>

        {/* Top scroll area : "Navigation" + "All Modules" sections */}
        <div className="body-sidebar-top">
          <div className="sidebar-items">
            {/* Section 1 — Navigation (workspaces of current app) */}
            <div className="standard-sidebar-section nested-container" data-title="All">
              <div className="standard-sidebar-label">Navigation</div>
              {visibleWorkspaces.map((ws) => {
                const slug = slugify(ws.name);
                const isActive = activeWorkspace === ws.name;
                return (
                  <div
                    key={ws.name}
                    className={`sidebar-item-container ${isActive ? 'active-sidebar' : ''}`}
                    item-name={ws.name}
                    item-title={ws.title}
                    item-public={ws.public ? '1' : '0'}
                    item-is-hidden={ws.is_hidden ? '1' : '0'}
                  >
                    <div className={`standard-sidebar-item ${isActive ? 'selected' : ''}`}>
                      <a
                        href={`/app/${slug}`}
                        className="item-anchor"
                        title={ws.title}
                      >
                        <span
                          className="sidebar-item-icon"
                          item-icon={ws.icon || 'folder-normal'}
                        >
                          {renderWorkspaceIcon(ws)}
                        </span>
                        <span className="sidebar-item-label">{ws.title || ws.label || ws.name}</span>
                      </a>
                      <div className="sidebar-item-control" />
                    </div>
                    <div className="sidebar-child-item nested-container" />
                  </div>
                );
              })}
            </div>

            {/* Section 2 — All Modules (mirror of app switcher, with active highlight) */}
            <div className="standard-sidebar-section modules-section" data-title="Modules">
              <div className="standard-sidebar-label">All Modules</div>
              {sortedApps.map((app) => {
                const isActiveApp = currentApp.app_name === app.app_name;
                return (
                  <div
                    key={app.app_name}
                    className={`sidebar-item-container module-item ${isActiveApp ? 'active-sidebar active-module' : ''}`}
                    data-app-name={app.app_name}
                    data-app-route={app.app_route}
                  >
                    <div className="standard-sidebar-item">
                      <a
                        className="item-anchor"
                        href={app.app_route || '/app'}
                        title={app.app_title}
                        onClick={(e) => navigateApp(e, app)}
                      >
                        <span className="sidebar-item-icon app-logo-container">
                          <img
                            className="app-logo"
                            src={app.app_logo_url || FALLBACK_LOGO}
                            alt={app.app_title}
                          />
                        </span>
                        <span className="sidebar-item-label">{app.app_title}</span>
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Bottom — collapse / expand pin toggle */}
        <div className="body-sidebar-bottom">
          <a
            className="collapse-sidebar-link"
            onClick={togglePin}
            style={{ cursor: 'pointer' }}
          >
            <svg className="icon icon-sm" style={{ marginTop: -2 }}>
              <use
                href={
                  expanded ? '#es-line-arrow-left' : '#es-line-arrow-right'
                }
              />
            </svg>
            <span className="collapse-sidebar-label">
              {expanded ? ' Collapse' : ' Expand'}
            </span>
          </a>
        </div>
      </div>

      {/* Mobile overlay (kept for parity, MVP focuses on desktop) */}
      <div className="overlay" style={{ zIndex: 1021 }} />
    </div>
  );
};
