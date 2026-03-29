CSS = """
/* ============================================================
   Admin Pro Dashboard — Complete Stylesheet
   Dark charcoal theme, ap- prefix, mobile-responsive
   ============================================================ */

/* --- Reset ------------------------------------------------- */
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

/* --- CSS Custom Properties --------------------------------- */
:root {
  --ap-bg: #0f0f0f;
  --ap-surface: #1a1a1a;
  --ap-card: #222222;
  --ap-card-hover: #2a2a2a;
  --ap-border: #333333;
  --ap-border-light: #444444;
  --ap-primary: #C8102E;
  --ap-primary-dark: #A00D22;
  --ap-primary-light: #E8304A;
  --ap-accent: #C8102E;
  --ap-accent-hover: #A00D22;
  --ap-green: #22c55e;
  --ap-amber: #f59e0b;
  --ap-red: #ef4444;
  --ap-purple: #8b5cf6;
  --ap-teal: #14b8a6;
  --ap-orange: #f97316;
  --ap-text: #f1f5f9;
  --ap-text-muted: #64748b;
  --ap-text-dim: #94a3b8;
  --ap-radius: 12px;
  --ap-radius-sm: 8px;
  --ap-shadow: 0 4px 24px rgba(0,0,0,0.4);
  --ap-sidebar-width: 240px;
  --ap-sidebar-collapsed: 60px;
  --ap-topbar-height: 60px;
  --ap-transition: 200ms ease;
  --ap-sidebar-bg: #1A1A1A;
  --ap-sidebar-border: #2a2a2a;
}

/* --- Keyframes --------------------------------------------- */
@keyframes ap-shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}

@keyframes ap-fade-in-up {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes ap-slide-up {
  from {
    opacity: 0;
    transform: translateY(40px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes ap-slide-in-right {
  from {
    opacity: 0;
    transform: translateX(120%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes ap-spin {
  to { transform: rotate(360deg); }
}

@keyframes ap-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.6; transform: scale(1.05); }
}

@keyframes ap-flow {
  0%   { stroke-dashoffset: 24; }
  100% { stroke-dashoffset: 0; }
}

@keyframes ap-status-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5); }
  50%       { box-shadow: 0 0 0 5px rgba(34, 197, 94, 0); }
}

/* --- Body & Layout ----------------------------------------- */
body.ap-body {
  background: var(--ap-bg);
  color: var(--ap-text);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  min-height: 100vh;
  overflow-x: hidden;
}

/* --- Mobile Sidebar Overlay -------------------------------- */
.ap-sidebar-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 99;
  backdrop-filter: blur(2px);
}
.ap-sidebar-overlay.active {
  display: block;
}

/* --- Hamburger Button (mobile only) ----------------------- */
.ap-hamburger {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  width: 36px;
  height: 36px;
  padding: 6px;
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: var(--ap-radius-sm);
  flex-shrink: 0;
}
.ap-hamburger span {
  display: block;
  height: 2px;
  width: 100%;
  background: var(--ap-text-dim);
  border-radius: 2px;
  transition: background var(--ap-transition);
}
.ap-hamburger:hover span {
  background: var(--ap-text);
}

/* --- Sidebar ----------------------------------------------- */
.ap-sidebar {
  width: var(--ap-sidebar-width);
  min-width: var(--ap-sidebar-width);
  height: 100vh;
  background: var(--ap-sidebar-bg);
  border-right: 1px solid var(--ap-sidebar-border);
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 100;
  overflow-x: hidden;
  overflow-y: hidden;
  transition: width var(--ap-transition), min-width var(--ap-transition);
}

.ap-sidebar.collapsed {
  width: var(--ap-sidebar-collapsed);
  min-width: var(--ap-sidebar-collapsed);
}

.ap-sidebar-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 16px;
  border-bottom: 1px solid var(--ap-sidebar-border);
  min-height: var(--ap-topbar-height);
  white-space: nowrap;
  overflow: hidden;
}

.ap-sidebar-logo-icon {
  width: 32px;
  height: 32px;
  min-width: 32px;
  background: var(--ap-accent);
  border-radius: var(--ap-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.ap-sidebar-logo-text {
  font-weight: 700;
  font-size: 15px;
  color: var(--ap-text);
  transition: opacity var(--ap-transition);
}

.ap-sidebar.collapsed .ap-sidebar-logo-text,
.ap-sidebar.collapsed .ap-nav-label,
.ap-sidebar.collapsed .ap-nav-section-label {
  opacity: 0;
  pointer-events: none;
  width: 0;
}

.ap-sidebar-nav,
.ap-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 0;
}

.ap-sidebar-footer {
  padding: 12px 0;
  border-top: 1px solid var(--ap-sidebar-border);
}

/* --- Sidebar Brand Strip ----------------------------------- */
.ap-brand-strip {
  padding: 16px 16px 0;
  white-space: nowrap;
  overflow: hidden;
}

.ap-brand-name {
  font-size: 13px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 0.02em;
  line-height: 1.3;
  text-transform: uppercase;
  display: block;
}

.ap-brand-accent-line {
  display: block;
  height: 2px;
  background: var(--ap-primary);
  border-radius: 1px;
  margin-top: 8px;
  width: 32px;
}

.ap-sidebar.collapsed .ap-brand-strip {
  opacity: 0;
  pointer-events: none;
}

/* --- Nav Section Labels ------------------------------------ */
.ap-nav-section-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ap-text-muted);
  padding: 12px 16px 4px;
  white-space: nowrap;
  overflow: hidden;
  transition: opacity var(--ap-transition);
}

/* --- Nav Items --------------------------------------------- */
.ap-nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  cursor: pointer;
  border-radius: 0;
  color: var(--ap-text-dim);
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
  transition: background var(--ap-transition), color var(--ap-transition);
  position: relative;
  border: none;
  background: transparent;
  width: 100%;
  text-align: left;
  font-size: 14px;
}

.ap-nav-item:hover {
  background: rgba(200, 16, 46, 0.12);
  color: var(--ap-text);
  padding-left: 20px;
  transition: background var(--ap-transition), color var(--ap-transition),
              padding-left 150ms ease;
}

.ap-nav-item.active {
  background: rgba(200, 16, 46, 0.18);
  color: #ffffff;
  font-weight: 600;
}

.ap-nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--ap-accent);
  border-radius: 0 2px 2px 0;
}

.ap-nav-icon {
  width: 20px;
  min-width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.ap-nav-label {
  transition: opacity var(--ap-transition);
  overflow: hidden;
  text-overflow: ellipsis;
}

.ap-nav-badge {
  margin-left: auto;
  background: var(--ap-accent);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  min-width: 18px;
  text-align: center;
}

/* --- Sidebar Toggle Button --------------------------------- */
.ap-sidebar-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--ap-border);
  border-radius: 50%;
  color: var(--ap-text-dim);
  cursor: pointer;
  margin: 12px auto 8px;
  transition: color var(--ap-transition), background var(--ap-transition),
              transform var(--ap-transition);
}
.ap-sidebar-toggle:hover {
  color: var(--ap-text);
  background: rgba(255,255,255,0.06);
}
.ap-sidebar.collapsed .ap-sidebar-toggle {
  transform: rotate(180deg);
}

/* --- Main Content Area ------------------------------------- */
.ap-main {
  margin-left: var(--ap-sidebar-width);
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  transition: margin-left var(--ap-transition);
}

.ap-main.sidebar-collapsed {
  margin-left: var(--ap-sidebar-collapsed);
}

/* --- Topbar ------------------------------------------------ */
.ap-topbar {
  position: sticky;
  top: 0;
  z-index: 50;
  height: var(--ap-topbar-height);
  background: linear-gradient(135deg, #C8102E 0%, #A00D22 100%);
  border-bottom: 1px solid #8a0b1c;
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.35);
}

.ap-topbar-toggle {
  background: transparent;
  border: none;
  color: var(--ap-text-dim);
  cursor: pointer;
  padding: 6px;
  border-radius: var(--ap-radius-sm);
  display: flex;
  align-items: center;
  font-size: 18px;
  transition: color var(--ap-transition), background var(--ap-transition);
}

.ap-topbar-toggle:hover {
  color: var(--ap-text);
  background: rgba(255,255,255,0.06);
}

.ap-topbar-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ap-text);
  flex: 1;
}

.ap-topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ap-topbar-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  border-radius: var(--ap-radius-sm);
  cursor: pointer;
  transition: background var(--ap-transition);
}

.ap-topbar-user:hover {
  background: rgba(255,255,255,0.06);
}

.ap-topbar-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--ap-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}

.ap-topbar-username {
  font-size: 13px;
  font-weight: 500;
  color: var(--ap-text);
}

/* --- Topbar Layout Zones ----------------------------------- */
.ap-topbar-left {
  display: flex;
  flex-direction: column;
  justify-content: center;
  flex-shrink: 0;
}

.ap-topbar-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ap-topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.ap-page-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--ap-text);
  line-height: 1.2;
}

.ap-page-subtitle {
  font-size: 12px;
  color: var(--ap-text-muted);
  line-height: 1.2;
}

/* --- Search Wrap ------------------------------------------- */
.ap-search-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.ap-search-icon {
  position: absolute;
  left: 10px;
  color: var(--ap-text-muted);
  pointer-events: none;
  z-index: 1;
}

.ap-search-clear {
  position: absolute;
  right: 10px;
  color: var(--ap-text-muted);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  transition: color var(--ap-transition);
}

.ap-search-clear:hover {
  color: var(--ap-text);
}

/* --- User Badge -------------------------------------------- */
.ap-user-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: var(--ap-radius-sm);
  font-size: 13px;
  font-weight: 600;
  color: #ffffff;
  cursor: pointer;
  position: relative;
  transition: background var(--ap-transition), border-color var(--ap-transition);
  user-select: none;
}

.ap-user-badge:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.4);
}

/* Admin dropdown menu */
.ap-user-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 180px;
  background: var(--ap-card);
  border: 1px solid var(--ap-border-light);
  border-radius: var(--ap-radius-sm);
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 200;
  overflow: hidden;
  animation: ap-fade-in-up 160ms ease both;
}

.ap-user-dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  font-size: 13px;
  color: var(--ap-text-dim);
  cursor: pointer;
  transition: background var(--ap-transition), color var(--ap-transition);
  border: none;
  background: transparent;
  width: 100%;
  text-align: left;
}

.ap-user-dropdown-item:hover {
  background: rgba(200, 16, 46, 0.1);
  color: var(--ap-text);
}

.ap-user-dropdown-item.danger:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--ap-red);
}

.ap-user-dropdown-divider {
  border: none;
  border-top: 1px solid var(--ap-border);
  margin: 4px 0;
}

/* --- Notification Bell ------------------------------------ */
.ap-notification-bell {
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: var(--ap-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--ap-text-dim);
  transition: background var(--ap-transition), color var(--ap-transition);
}

.ap-notification-bell:hover {
  background: rgba(255,255,255,0.06);
  color: var(--ap-text);
}

.ap-notif-count {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 16px;
  height: 16px;
  background: var(--ap-red);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 3px;
  pointer-events: none;
}

/* --- Notification Panel ------------------------------------ */
.ap-notification-panel {
  position: fixed;
  top: calc(var(--ap-topbar-height) + 8px);
  right: 24px;
  width: 320px;
  background: var(--ap-card);
  border: 1px solid var(--ap-border-light);
  border-radius: var(--ap-radius);
  box-shadow: 0 16px 40px rgba(0,0,0,0.5);
  z-index: 300;
  overflow: hidden;
}

.ap-notif-panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ap-border);
}

.ap-notif-panel-header .ap-card-title {
  flex: 1;
}

.ap-notif-list {
  max-height: 360px;
  overflow-y: auto;
  padding: 8px 0;
}

.ap-notif-empty {
  padding: 24px 16px;
  text-align: center;
  color: var(--ap-text-muted);
  font-size: 13px;
}

/* --- Search Input ------------------------------------------ */
.ap-search-input {
  background: var(--ap-card);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius-sm);
  color: var(--ap-text);
  font-size: 13px;
  padding: 7px 12px 7px 34px;
  width: 220px;
  outline: none;
  transition: border-color var(--ap-transition), width 300ms ease;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: 10px center;
}

.ap-search-input:focus {
  border-color: var(--ap-accent);
  width: 280px;
}

.ap-search-input::placeholder {
  color: var(--ap-text-muted);
}

/* --- Page Content ------------------------------------------ */
.ap-content {
  padding: 24px;
  max-width: 1400px;
  width: 100%;
  flex: 1;
  margin: 0 auto;
}

/* --- Dashboard section fills full width ------------------- */
#section-dashboard {
  width: 100%;
}

/* Calendar section fills full available width and height */
#section-calendar {
  width: 100%;
  max-width: none;
  height: calc(100vh - var(--ap-topbar-height, 56px) - 48px);
  display: flex;
  flex-direction: column;
}

/* When calendar (or other full-width section) is active, remove content cap */
.ap-content.ap-content--fullwidth {
  max-width: 100%;
  padding: 16px;
}

/* --- Sections ---------------------------------------------- */
.ap-section {
  display: none;
}

.ap-section.active {
  display: block;
  animation: ap-fade-in-up 280ms ease both;
}

.ap-section-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--ap-text);
  margin-bottom: 4px;
}

.ap-section-subtitle {
  font-size: 13px;
  color: var(--ap-text-muted);
  margin-bottom: 24px;
}

/* --- Cards ------------------------------------------------- */
.ap-card {
  background: var(--ap-card);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  box-shadow: var(--ap-shadow);
  padding: 20px;
  transition: border-color var(--ap-transition), background var(--ap-transition),
              box-shadow var(--ap-transition);
  margin-bottom: 16px;
}

/* Cards inside grids don't double up margins */
.ap-grid-2 .ap-card,
.ap-grid-3 .ap-card,
.ap-grid-4 .ap-card,
.ap-kpi-row .ap-card {
  margin-bottom: 0;
}

.ap-card:hover {
  border-color: var(--ap-border-light);
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}

.ap-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.ap-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ap-text);
}

.ap-card-subtitle {
  font-size: 12px;
  color: var(--ap-text-muted);
  margin-top: 2px;
}

/* --- KPI Cards --------------------------------------------- */
.ap-kpi-card {
  background: var(--ap-card);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  box-shadow: var(--ap-shadow);
  padding: 20px 24px;
  border-top: 3px solid var(--ap-accent);
  transition: border-color var(--ap-transition), transform var(--ap-transition),
              background var(--ap-transition), box-shadow var(--ap-transition);
}

.ap-kpi-card:hover {
  border-color: var(--ap-border-light);
  border-top-color: var(--ap-accent);
  background: var(--ap-card-hover);
  transform: translateY(-2px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 8px 24px rgba(200,16,46,0.15);
  cursor: pointer;
}

.ap-kpi-card.ap-kpi-accent {
  border-top-color: var(--ap-green);
}

.ap-kpi-card#kpi-pending  { border-top-color: var(--ap-primary); }
.ap-kpi-card#kpi-today    { border-top-color: var(--ap-green); }
.ap-kpi-card#kpi-week     { border-top-color: var(--ap-accent); }
.ap-kpi-card#kpi-total    { border-top-color: var(--ap-primary); }
.ap-kpi-card#ana-conversion  { border-top-color: var(--ap-teal); }
.ap-kpi-card#ana-avg-confirm { border-top-color: var(--ap-amber); }
.ap-kpi-card#ana-week        { border-top-color: var(--ap-green); }
.ap-kpi-card#ana-revenue     { border-top-color: var(--ap-orange); }

.ap-kpi-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--ap-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  margin-bottom: 12px;
}

.ap-kpi-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--ap-text);
  line-height: 1;
  margin-bottom: 6px;
}

.ap-kpi-label {
  font-size: 12px;
  color: var(--ap-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
}

.ap-kpi-trend {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 600;
  margin-top: 8px;
}

.ap-kpi-trend.up {
  color: var(--ap-green);
}

.ap-kpi-trend.down {
  color: var(--ap-red);
}

/* --- Tables ------------------------------------------------ */
.ap-table-wrap {
  overflow-x: auto;
  border-radius: var(--ap-radius);
  border: 1px solid var(--ap-border);
}

.ap-recent-bookings-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.ap-recent-bookings-wrap table {
  min-width: 600px;
}

.ap-table {
  width: 100%;
  min-width: 700px;
  border-collapse: collapse;
  font-size: 13px;
}

.ap-table th {
  background: var(--ap-surface);
  color: var(--ap-text-muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 10px 16px;
  text-align: left;
  border-bottom: 1px solid var(--ap-border);
  white-space: nowrap;
}

.ap-table td {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(26, 58, 92, 0.5);
  color: var(--ap-text);
  vertical-align: middle;
}

.ap-table tr:last-child td {
  border-bottom: none;
}

.ap-table tbody tr {
  transition: background var(--ap-transition);
}

.ap-table tbody tr:hover {
  background: rgba(200, 16, 46, 0.05);
}

.ap-table-row-clickable {
  cursor: pointer;
}

.ap-table-row-clickable:hover {
  background: rgba(200, 16, 46, 0.1) !important;
}

.ap-table-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

/* --- Buttons ----------------------------------------------- */
.ap-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--ap-radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  outline: none;
  text-decoration: none;
  transition: background var(--ap-transition), color var(--ap-transition),
              border-color var(--ap-transition), transform var(--ap-transition),
              box-shadow var(--ap-transition);
  white-space: nowrap;
  line-height: 1;
}

.ap-btn:active {
  transform: scale(0.97);
}

.ap-btn-primary {
  background: var(--ap-accent);
  color: #fff;
  border-color: var(--ap-accent);
}

.ap-btn-primary:hover {
  background: var(--ap-accent-hover);
  border-color: var(--ap-accent-hover);
}

.ap-btn-success {
  background: var(--ap-green);
  color: #fff;
  border-color: var(--ap-green);
}

.ap-btn-success:hover {
  background: #16a34a;
  border-color: #16a34a;
}

.ap-btn-danger {
  background: var(--ap-red);
  color: #fff;
  border-color: var(--ap-red);
}

.ap-btn-danger:hover {
  background: #dc2626;
  border-color: #dc2626;
}

.ap-btn-ghost {
  background: transparent;
  color: var(--ap-text-dim);
  border-color: var(--ap-border-light);
}

.ap-btn-ghost:hover {
  background: rgba(255,255,255,0.06);
  color: var(--ap-text);
  border-color: var(--ap-border-light);
}

.ap-btn-sm {
  padding: 5px 10px;
  font-size: 12px;
}

.ap-btn-icon {
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 50%;
  font-size: 14px;
}

/* --- Forms ------------------------------------------------- */
.ap-form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ap-form-group label {
  font-size: 12px;
  font-weight: 500;
  color: var(--ap-text-dim);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ap-input,
.ap-select,
.ap-textarea {
  background: var(--ap-bg);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius-sm);
  color: var(--ap-text);
  font-size: 13px;
  padding: 9px 12px;
  outline: none;
  transition: border-color var(--ap-transition), box-shadow var(--ap-transition);
  width: 100%;
  font-family: inherit;
}

.ap-input:focus,
.ap-select:focus,
.ap-textarea:focus {
  border-color: var(--ap-accent);
  box-shadow: 0 0 0 3px rgba(200,16,46,0.15);
}

.ap-input::placeholder,
.ap-textarea::placeholder {
  color: var(--ap-text-muted);
}

.ap-select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 32px;
}

.ap-select option {
  background: var(--ap-card);
  color: var(--ap-text);
}

.ap-textarea {
  resize: vertical;
  min-height: 80px;
  line-height: 1.5;
}

/* --- Badges / Status --------------------------------------- */
.ap-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.ap-badge-green {
  background: rgba(34, 197, 94, 0.15);
  color: var(--ap-green);
}

.ap-badge-amber {
  background: rgba(245, 158, 11, 0.15);
  color: var(--ap-amber);
}

.ap-badge-red {
  background: rgba(239, 68, 68, 0.15);
  color: var(--ap-red);
}

.ap-badge-blue {
  background: rgba(200, 16, 46, 0.15);
  color: var(--ap-primary);
}

.ap-badge-purple {
  background: rgba(139, 92, 246, 0.15);
  color: var(--ap-purple);
}

.ap-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ap-status-dot.green  { background: var(--ap-green); animation: ap-status-pulse 2s ease-in-out infinite; }
.ap-status-dot.amber  { background: var(--ap-amber); }
.ap-status-dot.red    { background: var(--ap-red); }
.ap-status-dot.blue   { background: var(--ap-accent); }
.ap-status-dot.purple { background: var(--ap-purple); }

/* --- Modal ------------------------------------------------- */
.ap-modal-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: var(--ap-sidebar-width, 240px);
  z-index: 500;
  background: rgba(7, 17, 31, 0.8);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 200ms ease;
}

.ap-modal-wide {
  max-width: 680px !important;
  width: 90vw;
}

/* When sidebar is collapsed, shrink the modal overlay left offset */
#ap-main.sidebar-collapsed ~ * .ap-modal-overlay,
.sidebar-collapsed .ap-modal-overlay {
  left: var(--ap-sidebar-collapsed, 60px);
}

.ap-modal-overlay.open {
  opacity: 1;
  pointer-events: all;
}

.ap-modal {
  background: var(--ap-card);
  border: 1px solid var(--ap-border-light);
  border-radius: var(--ap-radius);
  box-shadow: 0 24px 64px rgba(0,0,0,0.6);
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  animation: ap-slide-up 260ms ease both;
  position: relative;
}

.ap-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--ap-border);
  flex-shrink: 0;
}

.ap-modal-header h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--ap-text);
}

.ap-modal-close {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: none;
  background: rgba(255,255,255,0.06);
  color: var(--ap-text-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  transition: background var(--ap-transition), color var(--ap-transition);
  flex-shrink: 0;
}

.ap-modal-close:hover {
  background: rgba(239,68,68,0.15);
  color: var(--ap-red);
}

.ap-modal-body {
  padding: 20px 24px;
  overflow-y: auto;
  flex: 1;
}

.ap-modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 24px 20px;
  border-top: 1px solid var(--ap-border);
  flex-shrink: 0;
}

/* --- Booking Detail Modal ---------------------------------- */
.ap-booking-detail { font-size: 14px; line-height: 1.5; }

.ap-bd-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 24px;
  margin-bottom: 4px;
}

@media (max-width: 540px) {
  .ap-bd-cols { grid-template-columns: 1fr; }
}

.ap-bd-sep {
  height: 1px;
  background: var(--ap-border);
  margin: 14px 0;
}

.ap-detail-heading {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--ap-primary);
  margin: 0 0 8px;
}

.ap-dl {
  display: grid;
  grid-template-columns: 68px 1fr;
  row-gap: 4px;
  column-gap: 10px;
  margin: 0 0 4px;
}
.ap-dl dt {
  font-size: 12px;
  font-weight: 500;
  color: var(--ap-text-muted);
  padding-top: 1px;
  white-space: nowrap;
}
.ap-dl dd {
  font-size: 13px;
  color: var(--ap-text);
  margin: 0;
  word-break: break-word;
}
.ap-dl dd a.ap-link {
  color: var(--ap-text);
  text-decoration: underline;
  text-decoration-color: rgba(255,255,255,0.4);
}
.ap-dl dd a.ap-link:hover {
  text-decoration-color: var(--ap-text);
}

.ap-notes-text {
  font-size: 13px;
  color: var(--ap-text);
  background: var(--ap-surface);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius-sm);
  padding: 10px 12px;
  margin-bottom: 8px;
  min-height: 38px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}

/* Timeline */
.ap-timeline { display: flex; flex-direction: column; }
.ap-timeline-item {
  display: flex;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid var(--ap-border);
}
.ap-timeline-item:last-child { border-bottom: none; padding-bottom: 0; }
.ap-timeline-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ap-primary);
  opacity: 0.7;
  flex-shrink: 0;
  margin-top: 4px;
}
.ap-timeline-content { flex: 1; min-width: 0; }
.ap-timeline-header { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.ap-timeline-type {
  font-size: 12px;
  font-weight: 600;
  color: var(--ap-text);
  text-transform: capitalize;
}
.ap-timeline-actor { font-size: 11px; color: var(--ap-text-muted); }
.ap-timeline-detail { font-size: 12px; color: var(--ap-text-muted); margin-top: 2px; }
.ap-timeline-time { font-size: 11px; color: var(--ap-text-muted); margin-top: 1px; }

/* --- Toast Notifications ----------------------------------- */
.ap-toast-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.ap-toast {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: var(--ap-card);
  border: 1px solid var(--ap-border-light);
  border-left-width: 3px;
  border-radius: var(--ap-radius-sm);
  padding: 12px 14px;
  min-width: 280px;
  max-width: 360px;
  box-shadow: var(--ap-shadow);
  pointer-events: all;
  animation: ap-slide-in-right 280ms ease both;
}

.ap-toast.success { border-left-color: var(--ap-green); }
.ap-toast.error   { border-left-color: var(--ap-red); }
.ap-toast.warning { border-left-color: var(--ap-amber); }
.ap-toast.info    { border-left-color: var(--ap-accent); }

.ap-toast-icon {
  font-size: 16px;
  margin-top: 1px;
  flex-shrink: 0;
}

.ap-toast.success .ap-toast-icon { color: var(--ap-green); }
.ap-toast.error   .ap-toast-icon { color: var(--ap-red); }
.ap-toast.warning .ap-toast-icon { color: var(--ap-amber); }
.ap-toast.info    .ap-toast-icon { color: var(--ap-accent); }

.ap-toast-body {
  flex: 1;
}

.ap-toast-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ap-text);
  margin-bottom: 2px;
}

.ap-toast-message {
  font-size: 12px;
  color: var(--ap-text-dim);
  line-height: 1.4;
}

.ap-toast-dismiss {
  background: transparent;
  border: none;
  color: var(--ap-text-muted);
  cursor: pointer;
  font-size: 14px;
  padding: 0;
  line-height: 1;
  transition: color var(--ap-transition);
  flex-shrink: 0;
}

.ap-toast-dismiss:hover {
  color: var(--ap-text);
}

/* --- Charts ----------------------------------------------- */
.ap-chart-card {
  background: var(--ap-card);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  box-shadow: var(--ap-shadow);
  padding: 20px;
}

.ap-chart-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ap-text);
  margin-bottom: 16px;
}

.ap-chart-container {
  position: relative;
  height: 300px;
  width: 100%;
}

/* --- Pipeline Visualization -------------------------------- */
.ap-pipeline {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  padding: 16px 0;
}

.ap-pipeline-track {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 0;
  overflow-x: auto;
  min-width: max-content;
}

.ap-pipeline-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  background: linear-gradient(160deg, var(--ap-card) 0%, var(--ap-surface) 100%);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  padding: 14px 18px;
  min-width: 120px;
  flex: 1;
  text-align: center;
  transition: border-color var(--ap-transition), transform var(--ap-transition),
              box-shadow var(--ap-transition);
  position: relative;
  overflow: hidden;
}

.ap-pipeline-node::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--ap-accent);
  opacity: 0;
  transition: opacity var(--ap-transition);
}

.ap-pipeline-node:hover {
  border-color: var(--ap-accent);
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(200,16,46,0.2);
}

.ap-pipeline-node:hover::before {
  opacity: 1;
}

.ap-pipeline-node-icon {
  font-size: 22px;
}

.ap-pipeline-node-count {
  font-size: 20px;
  font-weight: 700;
  color: var(--ap-text);
}

.ap-pipeline-node-label {
  font-size: 11px;
  color: var(--ap-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ap-pipeline-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  width: 40px;
  flex-shrink: 0;
  font-size: 20px;
  color: var(--ap-border-light);
}

.ap-pipeline-arrow-anim {
  display: inline-block;
  animation: ap-pulse 1.2s ease-in-out infinite;
}

.ap-pipeline-arrow line,
.ap-pipeline-arrow polyline {
  stroke: var(--ap-border-light);
  stroke-width: 2;
  stroke-dasharray: 6;
  stroke-dashoffset: 24;
  animation: ap-flow 600ms linear infinite;
}

/* --- Activity Feed ---------------------------------------- */
.ap-activity-list {
  display: flex;
  flex-direction: column;
}

.ap-activity-item {
  display: flex;
  gap: 14px;
  position: relative;
  padding-bottom: 16px;
}

.ap-activity-item:last-child {
  padding-bottom: 0;
}

.ap-activity-item:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 7px;
  top: 20px;
  bottom: 0;
  width: 1px;
  background: var(--ap-border);
}

.ap-activity-dot {
  width: 16px;
  height: 16px;
  min-width: 16px;
  border-radius: 50%;
  margin-top: 3px;
  border: 2px solid var(--ap-bg);
  flex-shrink: 0;
}

.ap-activity-content {
  flex: 1;
}

.ap-activity-text {
  font-size: 13px;
  color: var(--ap-text);
  line-height: 1.4;
}

.ap-activity-time {
  font-size: 11px;
  color: var(--ap-text-muted);
  margin-top: 3px;
}

/* --- Pills / Filter Tabs ---------------------------------- */
.ap-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--ap-border-light);
  background: transparent;
  color: var(--ap-text-dim);
  transition: background var(--ap-transition), color var(--ap-transition),
              border-color var(--ap-transition);
  white-space: nowrap;
}

.ap-pill:hover {
  background: rgba(200, 16, 46, 0.1);
  color: var(--ap-text);
  border-color: var(--ap-accent);
}

.ap-pill.active {
  background: rgba(200, 16, 46, 0.18);
  color: var(--ap-accent);
  border-color: var(--ap-accent);
  font-weight: 600;
}

.ap-pill-xs {
  padding: 3px 8px;
  font-size: 11px;
}

/* --- Tabs -------------------------------------------------- */
.ap-tabs {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--ap-border);
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.ap-tab {
  display: inline-flex;
  align-items: center;
  padding: 9px 16px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  background: transparent;
  color: var(--ap-text-muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color var(--ap-transition), border-color var(--ap-transition);
  white-space: nowrap;
}

.ap-tab:hover {
  color: var(--ap-text);
}

.ap-tab.active {
  color: var(--ap-accent);
  border-bottom-color: var(--ap-accent);
  font-weight: 600;
}

.ap-tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--ap-red);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  border-radius: 999px;
  margin-left: 6px;
}

.ap-tab-badge:empty { display: none; }

.ap-tab-content {
  display: none;
}

.ap-tab-content.active {
  display: block;
  animation: ap-fade-in-up 240ms ease both;
}

/* --- Filter Bar ------------------------------------------- */
.ap-filter-bar {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.ap-status-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ap-filter-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
}

.ap-input-sm {
  padding: 6px 10px;
  font-size: 12px;
  height: 32px;
}

.ap-input-xs {
  padding: 4px 8px;
  font-size: 11px;
  height: 28px;
}

.ap-bulk-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ap-bulk-count {
  font-size: 12px;
  color: var(--ap-text-muted);
}

/* --- Pagination ------------------------------------------- */
.ap-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 0 4px;
  flex-wrap: wrap;
}

.ap-page-info {
  font-size: 12px;
  color: var(--ap-text-muted);
  padding: 0 8px;
}

/* --- KPI row ---------------------------------------------- */
.ap-kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
  width: 100%;
}

.ap-kpi-sub {
  font-size: 11px;
  color: var(--ap-text-muted);
  margin-top: 4px;
}

/* --- Card Badge / Sub ------------------------------------- */
.ap-card-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: rgba(34, 197, 94, 0.15);
  color: var(--ap-green);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.ap-card-sub {
  font-size: 12px;
  color: var(--ap-text-muted);
}

/* --- Today Jobs List -------------------------------------- */
.ap-today-jobs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.ap-today-empty {
  font-size: 13px;
  color: var(--ap-text-muted);
  text-align: center;
  padding: 24px 0;
}

.ap-today-job-card {
  background: var(--ap-surface);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius-sm);
  padding: 10px 12px;
  font-size: 13px;
  cursor: pointer;
  transition: background var(--ap-transition), border-color var(--ap-transition);
}

.ap-today-job-card:hover {
  background: rgba(200,16,46,0.1);
  border-color: var(--ap-border-light);
}

/* --- Status Indicator ------------------------------------- */
.ap-status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ap-text-dim);
}

.ap-status-card {
  padding: 14px 18px;
}

/* --- System / Health Cards -------------------------------- */
.ap-health-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
  padding: 20px;
}

.ap-health-icon {
  color: var(--ap-text-dim);
  margin-bottom: 4px;
}

.ap-health-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ap-text);
}

.ap-health-status {
  font-size: 12px;
  color: var(--ap-text-muted);
}

/* --- Feature Flags / Toggles ------------------------------ */
.ap-feature-flags {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ap-flag-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--ap-border);
}

.ap-flag-row:last-child {
  border-bottom: none;
}

.ap-flag-label {
  font-size: 13px;
  color: var(--ap-text);
}

.ap-toggle {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}

.ap-toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.ap-toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--ap-border-light);
  border-radius: 999px;
  transition: background var(--ap-transition);
}

.ap-toggle-slider::before {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  left: 3px;
  top: 3px;
  transition: transform var(--ap-transition);
}

.ap-toggle input:checked + .ap-toggle-slider {
  background: var(--ap-green);
}

.ap-toggle input:checked + .ap-toggle-slider::before {
  transform: translateX(18px);
}

/* --- DB Stats --------------------------------------------- */
.ap-db-stats {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ap-stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--ap-border);
  font-size: 13px;
}

.ap-stat-row:last-child { border-bottom: none; }

.ap-stat-label { color: var(--ap-text-muted); }
.ap-stat-val   { color: var(--ap-text); font-weight: 600; }

/* --- Danger Text ------------------------------------------ */
.ap-danger-text { color: var(--ap-red); }

/* --- Form Actions / Inline -------------------------------- */
.ap-form-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.ap-form-inline {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: flex-end;
}

.ap-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--ap-text-dim);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ap-input-hint {
  font-size: 11px;
  color: var(--ap-text-muted);
  margin-top: 2px;
}

/* --- App State Viewer ------------------------------------- */
.ap-app-state {
  background: var(--ap-bg);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius-sm);
  padding: 12px;
  font-size: 12px;
  max-height: 400px;
  overflow-y: auto;
}

.ap-app-state pre {
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--ap-text-dim);
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

/* --- SMS History / Comms ---------------------------------- */
.ap-sms-history-header {
  margin-top: 20px;
  margin-bottom: 10px;
  padding-top: 16px;
  border-top: 1px solid var(--ap-border);
}

/* --- Charts ----------------------------------------------- */
.ap-chart-controls {
  display: flex;
  gap: 4px;
}

.ap-chart-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--ap-text-muted);
  font-size: 13px;
}

/* --- Funnel Chart ----------------------------------------- */
.ap-funnel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 0;
}

.ap-funnel-step {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ap-funnel-bar {
  height: 28px;
  background: linear-gradient(90deg, var(--ap-accent) 0%, rgba(200,16,46,0.3) 100%);
  border-radius: 4px;
  min-width: 20px;
  transition: width 600ms ease;
}

.ap-funnel-label {
  font-size: 13px;
  color: var(--ap-text-dim);
  white-space: nowrap;
  min-width: 120px;
}

/* --- Suburbs Card + List ---------------------------------- */
.ap-card-suburbs {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ap-suburbs-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 0;
  max-height: 320px;
  overflow-y: auto;
}

/* --- Revenue Bar ------------------------------------------ */
.ap-revenue-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ap-revenue-label {
  font-size: 12px;
  color: var(--ap-text-muted);
  min-width: 90px;
}

.ap-revenue-bar-wrap {
  flex: 1;
  height: 8px;
  background: var(--ap-border);
  border-radius: 999px;
  overflow: hidden;
}

.ap-revenue-bar {
  height: 100%;
  background: var(--ap-accent);
  border-radius: 999px;
  transition: width 600ms ease;
}

.ap-revenue-val {
  font-size: 12px;
  font-weight: 600;
  color: var(--ap-text);
  min-width: 50px;
  text-align: right;
}

/* --- Customers Grid --------------------------------------- */
.ap-grid-customers {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 16px;
  align-items: start;
}

.ap-customers-list-card {
  min-width: 0;
}

.ap-customer-detail-card {
  position: sticky;
  top: calc(var(--ap-topbar-height) + 16px);
}

.ap-customer-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.ap-info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 0;
  border-bottom: 1px solid var(--ap-border);
  font-size: 13px;
}

.ap-info-row:last-child { border-bottom: none; }

.ap-info-label {
  color: var(--ap-text-muted);
  font-size: 12px;
  font-weight: 500;
}

.ap-customer-bookings-header {
  margin-top: 14px;
  margin-bottom: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--ap-border);
}

.ap-search-inline {
  margin-bottom: 12px;
}

/* --- Activity Feed Controls ------------------------------- */
.ap-activity-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ap-activity-feed {
  display: flex;
  flex-direction: column;
}

.ap-activity-footer {
  display: flex;
  justify-content: center;
  margin-top: 12px;
}

.ap-activity-loading {
  padding: 24px;
  text-align: center;
  color: var(--ap-text-muted);
  font-size: 13px;
}

.ap-toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--ap-text-dim);
  cursor: pointer;
  user-select: none;
}

/* --- Sortable Table Headers ------------------------------- */
.ap-th-sortable {
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.ap-th-sortable:hover {
  color: var(--ap-text);
}

.ap-sort-arrow {
  opacity: 0.4;
  font-size: 10px;
}

.ap-th-check {
  width: 40px;
}

/* --- Table empty state ------------------------------------ */
.ap-table-empty {
  text-align: center;
  color: var(--ap-text-muted);
  font-size: 13px;
  padding: 24px 0;
}

/* --- Calendar --------------------------------------------- */
.ap-calendar-layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 16px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}

.ap-calendar-main {
  background: var(--ap-card);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  box-shadow: var(--ap-shadow);
  padding: 16px;
  min-width: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.ap-calendar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.ap-calendar-month-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--ap-text);
  flex: 1;
  text-align: center;
}

.ap-calendar-view-toggle {
  display: flex;
  gap: 6px;
}

.ap-calendar-month {
  font-size: 15px;
  font-weight: 600;
  color: var(--ap-text);
}

.ap-calendar-nav {
  display: flex;
  gap: 4px;
}

.ap-calendar-nav-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--ap-radius-sm);
  border: 1px solid var(--ap-border);
  background: transparent;
  color: var(--ap-text-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: background var(--ap-transition), color var(--ap-transition);
}

.ap-calendar-nav-btn:hover {
  background: rgba(255,255,255,0.06);
  color: var(--ap-text);
}

/* Day-of-week header row */
.ap-calendar-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  margin-bottom: 2px;
  background: var(--ap-border);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius-sm) var(--ap-radius-sm) 0 0;
  overflow: hidden;
}

.ap-calendar-weekdays > div {
  background: var(--ap-surface);
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--ap-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 8px 0;
}

.ap-calendar-weekday {
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--ap-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 4px 0;
}

/* DOW row built by JS */
.ap-calendar-dow-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  margin-bottom: 2px;
  background: var(--ap-border);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius-sm) var(--ap-radius-sm) 0 0;
  overflow: hidden;
}

.ap-calendar-dow {
  background: var(--ap-surface);
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--ap-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 8px 4px;
}

/* Grid cells container */
.ap-calendar-grid,
.ap-calendar-grid-cells {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--ap-border);
  border: 1px solid var(--ap-border);
  border-radius: 0 0 var(--ap-radius-sm) var(--ap-radius-sm);
  overflow: hidden;
}

.ap-calendar-day {
  min-height: 100px;
  height: 110px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  padding: 6px 8px 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  color: var(--ap-text);
  position: relative;
  transition: background var(--ap-transition), color var(--ap-transition);
  border: none;
  background: var(--ap-card);
}

.ap-calendar-day:hover {
  background: rgba(200,16,46,0.12);
}

.ap-calendar-day.today {
  background: rgba(200,16,46,0.18);
  outline: 2px solid var(--ap-accent);
  outline-offset: -2px;
  color: var(--ap-accent);
  font-weight: 700;
}

.ap-calendar-day.today .ap-cal-day-num {
  background: var(--ap-accent);
  color: #fff;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.ap-calendar-day.has-jobs {
  background: rgba(34, 197, 94, 0.07);
}

.ap-calendar-day.other-month {
  opacity: 0.35;
  background: rgba(7,17,31,0.4);
}

.ap-calendar-day.selected {
  background: rgba(200,16,46,0.22);
  outline: 2px solid var(--ap-accent);
  outline-offset: -2px;
  color: var(--ap-text);
}

/* Day number — top-left */
.ap-cal-day-num {
  font-size: 13px;
  font-weight: 600;
  color: var(--ap-text);
  line-height: 1;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  min-height: 22px;
}

/* Booking dots at bottom */
.ap-cal-dots {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: auto;
  padding-bottom: 2px;
}

.ap-cal-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  padding: 0 4px;
  line-height: 1;
}

.ap-cal-dot.confirmed {
  background: rgba(34, 197, 94, 0.25);
  color: var(--ap-green);
}

.ap-cal-dot.pending {
  background: rgba(245, 158, 11, 0.25);
  color: var(--ap-amber);
}

/* Day detail side panel */
.ap-day-detail-panel {
  background: var(--ap-card);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  box-shadow: var(--ap-shadow);
  padding: 16px;
  min-height: 300px;
}

.ap-day-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ap-border);
}

.ap-day-jobs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ap-day-detail-actions {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--ap-border);
}

/* --- Week View Calendar ----------------------------------- */
.ap-week-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.ap-week-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--ap-text);
  flex: 1;
  text-align: center;
}

.ap-week-grid {
  display: grid;
  grid-template-columns: 60px repeat(5, 1fr);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  overflow: hidden;
  background: var(--ap-border);
  gap: 1px;
}

.ap-week-corner {
  background: var(--ap-surface);
  padding: 8px;
}

.ap-week-day-header {
  background: var(--ap-surface);
  text-align: center;
  padding: 10px 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ap-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  cursor: pointer;
  transition: background var(--ap-transition);
}

.ap-week-day-header:hover {
  background: rgba(200,16,46,0.08);
}

.ap-week-day-header.today {
  color: var(--ap-accent);
  background: rgba(200,16,46,0.12);
}

.ap-week-day-header .day-num {
  display: block;
  font-size: 18px;
  font-weight: 700;
  margin-top: 2px;
}

.ap-week-time-label {
  background: var(--ap-card);
  padding: 4px 8px;
  font-size: 11px;
  color: var(--ap-text-muted);
  text-align: right;
  border-right: 1px solid var(--ap-border);
  min-height: 48px;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
}

.ap-week-cell {
  background: var(--ap-card);
  min-height: 48px;
  padding: 2px;
  position: relative;
  transition: background 0.15s;
}

.ap-week-cell:hover {
  background: rgba(255,255,255,0.03);
}

.ap-week-cell.drag-over {
  background: rgba(200,16,46,0.15) !important;
  outline: 2px dashed var(--ap-accent);
  outline-offset: -2px;
}

/* Booking cards in week view */
.ap-week-booking {
  background: rgba(34, 197, 94, 0.15);
  border-left: 3px solid var(--ap-green);
  border-radius: 4px;
  padding: 4px 6px;
  margin: 1px;
  font-size: 12px;
  cursor: grab;
  transition: opacity 0.2s, transform 0.15s, box-shadow 0.15s;
  position: relative;
  overflow: hidden;
}

.ap-week-booking:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  transform: translateY(-1px);
}

.ap-week-booking.dragging {
  opacity: 0.4;
  transform: scale(0.95);
}

.ap-week-booking.pending {
  background: rgba(245, 158, 11, 0.15);
  border-left-color: var(--ap-amber);
}

.ap-week-booking.changed {
  background: rgba(249, 115, 22, 0.18);
  border-left-color: #f97316;
}

.ap-week-booking .booking-name {
  font-weight: 600;
  color: var(--ap-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ap-week-booking .booking-time {
  color: var(--ap-text-muted);
  font-size: 11px;
}

.ap-week-booking .booking-service {
  color: var(--ap-text-dim);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Notify button on changed bookings */
.ap-notify-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #f97316;
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 3px;
  animation: notifyPulse 2s ease-in-out infinite;
  transition: background 0.15s;
}

.ap-notify-btn:hover {
  background: #ea580c;
  animation: none;
}

@keyframes notifyPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(249, 115, 22, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(249, 115, 22, 0); }
}

/* Notify button in booking detail modal */
.ap-notify-btn-lg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #f97316;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  animation: notifyPulse 2s ease-in-out infinite;
  transition: background 0.15s;
}

.ap-notify-btn-lg:hover {
  background: #ea580c;
  animation: none;
}

/* Week view responsive */
@media (max-width: 900px) {
  .ap-week-grid {
    grid-template-columns: 50px repeat(5, 1fr);
  }
  .ap-week-booking .booking-service {
    display: none;
  }
}

/* Pending confirmation panel (right side of calendar) */
.ap-calendar-pending-panel {
  background: var(--ap-card);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  box-shadow: var(--ap-shadow);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.ap-pending-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--ap-border);
  flex-shrink: 0;
}

.ap-pending-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.ap-pending-card {
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-left: 3px solid var(--ap-amber);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: grab;
  transition: box-shadow 0.15s, transform 0.15s, opacity 0.2s;
  font-size: 13px;
}

.ap-pending-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  transform: translateY(-1px);
}

.ap-pending-card:active {
  cursor: grabbing;
}

.ap-pending-card.dragging {
  opacity: 0.4;
  transform: scale(0.95);
}

.ap-pending-card .pending-name {
  font-weight: 600;
  color: var(--ap-text);
  margin-bottom: 2px;
}

.ap-pending-card .pending-meta {
  color: var(--ap-text-muted);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.ap-pending-card .pending-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.ap-pending-card .pending-actions button {
  flex: 1;
}

@media (max-width: 1100px) {
  .ap-calendar-layout {
    grid-template-columns: 1fr;
  }
  .ap-calendar-pending-panel {
    max-height: 300px;
  }
}

/* --- Loading / Animations ---------------------------------- */
.ap-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(200,16,46,0.2);
  border-top-color: var(--ap-accent);
  border-radius: 50%;
  animation: ap-spin 600ms linear infinite;
  display: inline-block;
}

.ap-spinner-sm {
  width: 16px;
  height: 16px;
  border-width: 2px;
}

.ap-skeleton {
  border-radius: var(--ap-radius-sm);
  background: linear-gradient(
    90deg,
    var(--ap-card) 0px,
    var(--ap-card-hover) 200px,
    var(--ap-card) 400px
  );
  background-size: 800px 100%;
  animation: ap-shimmer 1.4s ease-in-out infinite;
}

.ap-skeleton-text {
  height: 14px;
  margin-bottom: 8px;
}

.ap-skeleton-text.wide  { width: 80%; }
.ap-skeleton-text.mid   { width: 60%; }
.ap-skeleton-text.short { width: 40%; }

.ap-animate-in {
  animation: ap-fade-in-up 280ms ease both;
}

.ap-pulse {
  animation: ap-pulse 1.5s ease-in-out infinite;
}

/* --- Grids & Utilities ------------------------------------- */
.ap-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.ap-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.ap-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.ap-flex {
  display: flex;
  align-items: center;
}

.ap-flex-between {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ap-flex-center {
  display: flex;
  align-items: center;
  justify-content: center;
}

.ap-gap-4  { gap: 4px; }
.ap-gap-8  { gap: 8px; }
.ap-gap-16 { gap: 16px; }

.ap-mt-8  { margin-top: 8px; }
.ap-mt-16 { margin-top: 16px; }
.ap-mt-24 { margin-top: 24px; }

.ap-text-muted   { color: var(--ap-text-muted) !important; }
.ap-text-dim     { color: var(--ap-text-dim) !important; }
.ap-text-success { color: var(--ap-green) !important; }
.ap-text-danger  { color: var(--ap-red) !important; }
.ap-text-warning { color: var(--ap-amber) !important; }
.ap-text-accent  { color: var(--ap-accent) !important; }

.ap-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* --- Divider ----------------------------------------------- */
.ap-divider {
  border: none;
  border-top: 1px solid var(--ap-border);
  margin: 16px 0;
}

/* --- Empty State ------------------------------------------ */
.ap-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  color: var(--ap-text-muted);
  text-align: center;
  gap: 12px;
}

.ap-empty-icon {
  font-size: 40px;
  opacity: 0.4;
}

.ap-empty-text {
  font-size: 14px;
  font-weight: 500;
}

/* --- Scrollbar Styling ------------------------------------- */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--ap-border-light);
  border-radius: 999px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--ap-text-muted);
}

/* ═══════════════════════════════════════════════════════════
   RESPONSIVE DESIGN
   ════════════════════════════════════════════════════════ */

/* --- Large tablets / small laptops (1100px) --------------- */
@media (max-width: 1100px) {
  .ap-grid-4 { grid-template-columns: repeat(2, 1fr); }
}

/* --- Tablets (900px) --------------------------------------- */
@media (max-width: 900px) {
  .ap-grid-3 { grid-template-columns: repeat(2, 1fr); }

  .ap-content { padding: 20px; }

  .ap-calendar-layout {
    grid-template-columns: 1fr;
  }
  .ap-calendar-grid-cells,
  .ap-calendar-grid {
    font-size: 12px;
  }
  .ap-calendar-day {
    min-height: 70px;
    height: 80px;
    padding: 4px;
  }
}

/* --- Mobile / portrait tablet (768px) --------------------- */
@media (max-width: 768px) {
  /* Show hamburger, hide desktop sidebar toggle */
  .ap-hamburger { display: flex; }
  .ap-sidebar-toggle { display: none; }

  /* Sidebar: hidden off-screen by default; slides in as overlay */
  .ap-sidebar {
    transform: translateX(-100%);
    transition: transform var(--ap-transition), width var(--ap-transition);
    width: var(--ap-sidebar-width) !important;
    z-index: 101;
  }
  .ap-sidebar.mobile-open {
    transform: translateX(0);
  }

  /* Main fills full width — no sidebar margin */
  .ap-main,
  .ap-main.sidebar-collapsed {
    margin-left: 0 !important;
  }

  .ap-content { padding: 14px; }

  .ap-grid-2,
  .ap-grid-3,
  .ap-grid-4 {
    grid-template-columns: 1fr;
  }

  .ap-search-wrap { display: none; }

  .ap-topbar {
    gap: 10px;
    padding: 0 14px;
  }

  .ap-topbar-left h1 { font-size: 14px; }
  .ap-topbar-left span { display: none; }

  .ap-user-badge span { display: none; }

  .ap-pipeline {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .ap-pipeline-track {
    min-width: max-content;
  }
  .ap-pipeline-arrow { display: flex; }

  /* Calendar mobile */
  .ap-calendar-layout {
    grid-template-columns: 1fr;
  }

  /* Customers grid mobile */
  .ap-grid-customers {
    grid-template-columns: 1fr;
  }
  .ap-customer-detail-card {
    position: static;
  }

  /* KPI row 2-col on mobile */
  .ap-kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .ap-calendar-dow-row {
    font-size: 10px;
  }
  .ap-calendar-day {
    min-height: 52px;
    height: 60px;
    padding: 3px 4px;
    font-size: 11px;
  }
  .ap-cal-day-num { font-size: 11px; }
  .ap-cal-dot { font-size: 8px; min-width: 14px; height: 14px; }

  /* Modals full-screen on mobile */
  .ap-modal-dialog,
  .ap-modal {
    max-width: 100% !important;
    margin: 0;
    border-radius: 0;
    min-height: 40vh;
    max-height: 90vh;
  }
  .ap-modal-overlay {
    align-items: flex-end;
    left: 0;
  }

  /* Toast */
  .ap-toast-container {
    right: 8px;
    bottom: 8px;
    left: 8px;
  }
  .ap-toast { max-width: 100%; }

  /* Tables horizontal scroll */
  .ap-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }

  /* KPI row stacks */
  .ap-kpi-row { gap: 10px; }
}

/* --- Small phones (480px) ---------------------------------- */
@media (max-width: 480px) {
  :root {
    --ap-topbar-height: 52px;
  }

  .ap-topbar { padding: 0 10px; gap: 8px; }

  .ap-kpi-value { font-size: 1.8rem !important; }

  .ap-content { padding: 10px; }

  .ap-card { padding: 14px; }

  /* Calendar: tighten cells further */
  .ap-calendar-day {
    min-height: 40px;
    height: 46px;
    padding: 2px 3px;
  }
  .ap-cal-day-num { font-size: 10px; }
  .ap-cal-dot { display: none; }

  /* Sidebar full width on very small screens */
  .ap-sidebar { width: min(280px, 85vw) !important; }
}
"""
