/**
 * NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OCE.
 *
 * FrappeNavbar — Pixel-perfect React reimplementation of the Frappe Desk navbar.
 *
 * We cannot load desk.bundle.js in our website page (timing + dependency
 * hell leads to crashes in billing.bundle, nora_debug, etc.). Instead we
 * render a compatible navbar here, styled by the same CSS classes
 * (.navbar, .navbar-brand, .nav-link...) as /app/home, and fed by the
 * mini-boot returned by neoconstruction.api.boot.get_navbar_boot().
 *
 * Mirrors the exact structure of frappe/public/js/frappe/ui/toolbar/navbar.html
 * with the additions from neoffice_theme prepended to the right nav:
 * - NORA quick chat icon
 * - Real-time clock
 * - Custom calendar SVG (month/day/weekday)
 *
 * Dropdowns are pure React state (no jQuery, no Bootstrap JS).
 */
import { useState, useEffect, useRef } from 'react';
import type { FC } from 'react';

// Local extended boot shape. We cast through unknown because the global
// Window.frappe type (declared by @neoffice/frappe-sidebar-react) does not
// know about the extra keys populated by get_navbar_boot() on the server.
interface NavbarBoot {
  user?: { name?: string; email?: string; user_image?: string; full_name?: string };
  app_logo_url?: string;
  navbar_settings?: Record<string, unknown>;
  is_fc_site?: boolean;
  developer_mode?: boolean;
}

interface CalendarData {
  month: string;
  day: string;
  weekday: string;
}

const formatTime = () =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

const formatCalendar = (): CalendarData => {
  const d = new Date();
  return {
    month: d.toLocaleDateString('fr-FR', { month: 'short' }).toUpperCase().replace('.', ''),
    day: String(d.getDate()).padStart(2, '0'),
    weekday: d.toLocaleDateString('fr-FR', { weekday: 'long' }),
  };
};

export const FrappeNavbar: FC = () => {
  const boot = (typeof window !== 'undefined'
    ? ((window as unknown as { frappe?: { boot?: NavbarBoot } }).frappe?.boot)
    : undefined);

  const [notifOpen, setNotifOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [time, setTime] = useState<string>(formatTime);
  const [calData, setCalData] = useState<CalendarData>(formatCalendar);

  // Update clock every minute
  useEffect(() => {
    const tick = () => setTime(formatTime());
    const interval = setInterval(tick, 60_000);
    return () => clearInterval(interval);
  }, []);

  // Update calendar at next midnight (then daily)
  useEffect(() => {
    const updateCal = () => setCalData(formatCalendar());
    const now = new Date();
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const msUntilMidnight = tomorrow.getTime() - now.getTime();
    let dailyInterval: ReturnType<typeof setInterval> | undefined;
    const timeout = setTimeout(() => {
      updateCal();
      dailyInterval = setInterval(updateCal, 86_400_000);
    }, msUntilMidnight);
    return () => {
      clearTimeout(timeout);
      if (dailyInterval) clearInterval(dailyInterval);
    };
  }, []);

  // Close dropdowns on outside click
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!navRef.current?.contains(e.target as Node)) {
        setNotifOpen(false);
        setHelpOpen(false);
        setUserMenuOpen(false);
      }
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, []);

  if (!boot) return null;

  const logoUrl = boot.app_logo_url || '/assets/neoffice_theme/images/neoffice_logo.svg';
  const userName = boot.user?.full_name || boot.user?.email || boot.user?.name || '';
  const userImage = boot.user?.user_image || '';
  const initial = (userName[0] || '?').toUpperCase();
  const isMac = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform);

  // Click handlers for the neoffice_theme additions
  const goCalendar = () => {
    window.location.href = '/app/event/view/calendar/default';
  };
  const goNora = () => {
    window.location.href = '/app/nora-chat';
  };

  return (
    <div className="sticky-top">
      <header ref={navRef} className="navbar navbar-expand" role="navigation">
        <div className="container">
          {/* Mobile sidebar toggle */}
          <button
            className="btn-reset navbar-toggle-sidebar d-sm-none"
            aria-label="Toggle Sidebar"
          >
            <svg className="es-icon icon-md">
              <use href="#es-line-align-justify" />
            </svg>
          </button>

          {/* Brand logo */}
          <a className="navbar-brand navbar-home" href="/app/home">
            <img className="app-logo" src={logoUrl} alt="App Logo" />
          </a>

          {/* Breadcrumbs (empty in our case, OCE handles routing) */}
          <ul className="nav navbar-nav d-none d-sm-flex" id="navbar-breadcrumbs"></ul>

          {/* Right collapse */}
          <div className="navbar-collapse justify-content-end" style={{ visibility: 'visible', display: 'flex' }}>
            {/* Search bar */}
            <form
              className="form-inline fill-width justify-content-end"
              role="search"
              onSubmit={(e) => e.preventDefault()}
            >
              <div className="input-group search-bar text-muted">
                <input
                  id="navbar-search"
                  type="text"
                  className="form-control"
                  placeholder={`Search or type a command (${isMac ? '⌘ + G' : 'Ctrl + G'})`}
                  aria-haspopup="true"
                />
                <span className="search-icon">
                  <svg className="icon icon-sm">
                    <use href="#icon-search" />
                  </svg>
                </span>
              </div>
            </form>

            {/* Right nav items — neoffice_theme additions PREPENDED */}
            <ul className="navbar-nav">
              {/* NORA quick chat */}
              <li
                className="nav-item nora-quick-chat-btn"
                title="Ask NORA"
                style={{ cursor: 'pointer', margin: '0 8px' }}
                onClick={goNora}
              >
                <a
                  className="nav-link"
                  style={{ padding: 0, display: 'flex', alignItems: 'center' }}
                >
                  <img
                    src="/assets/nora/images/nora_icon.svg"
                    alt="NORA"
                    style={{ width: 30, height: 'auto', marginTop: 2 }}
                  />
                </a>
              </li>

              {/* Clock */}
              <div style={{ width: 35 }} id="timer">
                {time}
              </div>

              {/* Calendar SVG (custom) */}
              <svg
                id="navCalendar"
                style={{ width: 40, margin: '0 10px', cursor: 'pointer' }}
                xmlns="http://www.w3.org/2000/svg"
                x="0px"
                y="0px"
                viewBox="0 0 512 512"
                onClick={goCalendar}
              >
                <title>See the calendar</title>
                <style type="text/css">{`
                  .st0{fill:transparent;stroke:#667777;stroke-width:4;stroke-miterlimit:10;}
                  .st1{fill:var(--primary);}
                  .st2{fill:#FFFFFF;}
                  .st3{font-family:var(--font-stack);}
                  .st4{font-size:140px;}
                  .st5{fill:var(--text-color);}
                  .st6{font-size:330px;}
                  .st7{font-size:90px;}
                `}</style>
                <path
                  className="st0"
                  d="M78.6,2.3h354.9c42.1,0,76.3,34.2,76.3,76.3v354.9c0,42.1-34.2,76.3-76.3,76.3H78.6c-42.1,0-76.3-34.2-76.3-76.3V78.7C2.2,36.5,36.4,2.3,78.6,2.3z"
                />
                <path
                  className="st1"
                  d="M76.8,0.3H435c42.5,0,77,23.9,77,53.3V125H-0.2V53.6C-0.2,24.2,34.3,0.3,76.8,0.3z"
                />
                <g>
                  <text
                    id="m"
                    transform="matrix(1 0 0 1 32.9795 115)"
                    className="st2 st3 st4"
                  >
                    {calData.month}
                  </text>
                  <text
                    id="d"
                    transform="matrix(1 0 0 1 31.3086 456.3828)"
                    className="st5 st3 st6"
                  >
                    {calData.day}
                  </text>
                  <text
                    id="w"
                    transform="matrix(1 0 0 1 40.7808 190.5273)"
                    className="st5 st3 st7"
                  >
                    {calData.weekday}
                  </text>
                </g>
              </svg>

              {/* Notifications dropdown — React state-managed */}
              <li
                className={`nav-item dropdown dropdown-notifications dropdown-mobile ${notifOpen ? 'show' : ''}`}
              >
                <button
                  className="btn-reset nav-link notifications-icon text-muted"
                  onClick={() => setNotifOpen((o) => !o)}
                  aria-haspopup="true"
                  aria-expanded={notifOpen}
                >
                  <span className="notifications-seen">
                    <svg className="es-icon icon-sm" style={{ stroke: 'none' }}>
                      <use href="#es-line-notifications" />
                    </svg>
                  </span>
                </button>
                {notifOpen && (
                  <div
                    className="dropdown-menu notifications-list dropdown-menu-right show"
                    role="menu"
                  >
                    <div className="notification-list-header">
                      <div className="header-items"></div>
                      <div className="header-actions"></div>
                    </div>
                    <div className="notification-list-body">
                      <div className="panel-notifications">No notifications</div>
                    </div>
                  </div>
                )}
              </li>

              {/* Vertical bar */}
              <li className="vertical-bar d-none d-sm-block"></li>

              {/* Help dropdown */}
              <li
                className={`nav-item dropdown dropdown-help dropdown-mobile d-none d-lg-block ${helpOpen ? 'show' : ''}`}
              >
                <button
                  className="btn-reset nav-link"
                  onClick={() => setHelpOpen((o) => !o)}
                  aria-controls="toolbar-help"
                  aria-label="Help Dropdown"
                >
                  <span>
                    Help
                    <svg className="es-icon icon-xs">
                      <use href="#es-line-down" />
                    </svg>
                  </span>
                </button>
                {helpOpen && (
                  <div
                    className="dropdown-menu dropdown-menu-right show"
                    id="toolbar-help"
                    role="menu"
                  >
                    <div id="help-links"></div>
                  </div>
                )}
              </li>

              {/* User menu dropdown */}
              <li
                className={`nav-item dropdown dropdown-navbar-user dropdown-mobile ${userMenuOpen ? 'show' : ''}`}
              >
                <button
                  className="btn-reset nav-link"
                  onClick={() => setUserMenuOpen((o) => !o)}
                  aria-label="User Menu"
                >
                  {userImage ? (
                    <img
                      src={userImage}
                      className="avatar avatar-medium rounded-circle"
                      alt={userName}
                      style={{ width: 28, height: 28 }}
                    />
                  ) : (
                    <div
                      className="avatar avatar-medium"
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: '50%',
                        background: '#e5e7eb',
                        color: '#111',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 600,
                      }}
                    >
                      {initial}
                    </div>
                  )}
                </button>
                {userMenuOpen && (
                  <div
                    className="dropdown-menu dropdown-menu-right show"
                    id="toolbar-user"
                    role="menu"
                  >
                    <a className="dropdown-item" href="/app/user-profile">
                      My Settings
                    </a>
                    <a className="dropdown-item" href="/app/user-permission">
                      Permissions
                    </a>
                    <div className="dropdown-divider"></div>
                    <a className="dropdown-item" href="/api/method/logout">
                      Logout
                    </a>
                  </div>
                )}
              </li>
            </ul>
          </div>
        </div>
      </header>
    </div>
  );
};
