import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { NAV_ITEMS } from "../auth/roles";
import { NotificationsDrawer, useUnreadCount } from "./NotificationsDrawer";

export function AppShell() {
  const { user, role, logout } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const unread = useUnreadCount();
  const unreadCount = unread.data ?? 0;

  // Collapse the phone menu after navigating.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  const items = NAV_ITEMS.filter((i) => role && i.roles.includes(role));

  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      <header className="topbar">
        <button
          type="button"
          className="btn btn-ghost menu-toggle"
          aria-expanded={menuOpen}
          aria-controls="sidebar"
          onClick={() => setMenuOpen((o) => !o)}
        >
          <span aria-hidden="true">☰</span> Menu
        </button>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">IV</span> <span className="brand-name">Inventra</span>
        </div>
        <div className="topbar-right">
          <button
            type="button"
            className="btn btn-ghost"
            aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
            onClick={() => setNotifOpen(true)}
          >
            <span aria-hidden="true">🔔</span>
            <span className="btn-label" aria-hidden="true">Notifications</span>
            {unreadCount > 0 && (
              <span className="badge badge-danger count-badge" aria-hidden="true">
                {unreadCount}
              </span>
            )}
          </button>
          <span className="user-chip">
            {user?.full_name} · {user?.role}
          </span>
          <button type="button" className="btn btn-ghost" onClick={() => void logout()}>
            Log out
          </button>
        </div>
      </header>

      <aside id="sidebar" className={menuOpen ? "sidebar open" : "sidebar"}>
        <nav aria-label="Main">
          <ul>
            {items.map((item) => (
              <li key={item.path}>
                <NavLink to={item.path} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <main id="main" className="content">
        <Outlet />
      </main>

      {notifOpen && <NotificationsDrawer onClose={() => setNotifOpen(false)} />}
    </div>
  );
}
