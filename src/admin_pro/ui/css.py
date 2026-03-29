CSS = """
/* ============================================================
   Admin Pro Dashboard — Complete Stylesheet
   Dark navy theme, ap- prefix, mobile-responsive
   ============================================================ */

/* --- Reset ------------------------------------------------- */
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

/* --- CSS Custom Properties --------------------------------- */
:root {
  --ap-bg: #07111f;
  --ap-surface: #0d1f35;
  --ap-card: #112240;
  --ap-card-hover: #152a4a;
  --ap-border: #1a3a5c;
  --ap-border-light: #253f60;
  --ap-accent: #3b82f6;
  --ap-accent-hover: #2563eb;
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
  background: var(--ap-surface);
  border-right: 1px solid var(--ap-border);
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 100;
  overflow: hidden;
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
  border-bottom: 1px solid var(--ap-border);
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

.ap-sidebar-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 0;
}

.ap-sidebar-footer {
  padding: 12px 0;
  border-top: 1px solid var(--ap-border);
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
  background: rgba(59, 130, 246, 0.08);
  color: var(--ap-text);
}

.ap-nav-item.active {
  background: rgba(59, 130, 246, 0.15);
  color: var(--ap-accent);
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
  background: var(--ap-surface);
  border-bottom: 1px solid var(--ap-border);
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 16px;
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
  transition: border-color var(--ap-transition), background var(--ap-transition);
}

.ap-card:hover {
  border-color: var(--ap-border-light);
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
  transition: border-color var(--ap-transition), transform var(--ap-transition), background var(--ap-transition);
}

.ap-kpi-card:hover {
  border-color: var(--ap-border-light);
  background: var(--ap-card-hover);
  transform: translateY(-2px);
}

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

.ap-table {
  width: 100%;
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
  background: rgba(59, 130, 246, 0.05);
}

.ap-table-actions {
  display: flex;
  align-items: center;
  gap: 6px;
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
  box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
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
  background: rgba(59, 130, 246, 0.15);
  color: var(--ap-accent);
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

.ap-status-dot.green  { background: var(--ap-green); }
.ap-status-dot.amber  { background: var(--ap-amber); }
.ap-status-dot.red    { background: var(--ap-red); }
.ap-status-dot.blue   { background: var(--ap-accent); }
.ap-status-dot.purple { background: var(--ap-purple); }

/* --- Modal ------------------------------------------------- */
.ap-modal-overlay {
  position: fixed;
  inset: 0;
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
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0;
  padding: 16px 0;
}

.ap-pipeline-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  background: var(--ap-card);
  border: 1px solid var(--ap-border);
  border-radius: var(--ap-radius);
  padding: 14px 18px;
  min-width: 90px;
  text-align: center;
  transition: border-color var(--ap-transition), transform var(--ap-transition);
}

.ap-pipeline-node:hover {
  border-color: var(--ap-accent);
  transform: translateY(-2px);
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
  width: 40px;
  height: 24px;
  flex-shrink: 0;
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

/* --- Calendar --------------------------------------------- */
.ap-calendar {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ap-calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
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

.ap-calendar-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
  margin-bottom: 4px;
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

.ap-calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}

.ap-calendar-day {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: var(--ap-radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  color: var(--ap-text);
  position: relative;
  transition: background var(--ap-transition), color var(--ap-transition);
  border: 1px solid transparent;
}

.ap-calendar-day:hover {
  background: rgba(59,130,246,0.1);
  border-color: var(--ap-border);
}

.ap-calendar-day.today {
  background: rgba(59,130,246,0.2);
  border-color: var(--ap-accent);
  color: var(--ap-accent);
  font-weight: 700;
}

.ap-calendar-day.has-jobs::after {
  content: '';
  position: absolute;
  bottom: 4px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--ap-accent);
}

.ap-calendar-day.other-month {
  opacity: 0.3;
}

.ap-calendar-day.selected {
  background: var(--ap-accent);
  color: #fff;
  border-color: var(--ap-accent);
}

/* --- Loading / Animations ---------------------------------- */
.ap-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(59,130,246,0.2);
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
}

.ap-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.ap-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
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

  .ap-calendar-grid-cells {
    font-size: 12px;
  }
  .ap-calendar-day {
    min-height: 60px;
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
    flex-wrap: wrap;
    gap: 8px;
  }
  .ap-pipeline-arrow { display: none; }

  /* Calendar mobile */
  .ap-calendar-dow-row {
    font-size: 10px;
  }
  .ap-calendar-day {
    min-height: 44px;
    padding: 3px;
    font-size: 11px;
  }
  .ap-cal-day-num { font-size: 12px; }

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
    min-height: 36px;
    padding: 2px;
  }
  .ap-cal-day-num { font-size: 11px; }
  .ap-cal-dot { display: none; }

  /* Sidebar full width on very small screens */
  .ap-sidebar { width: min(280px, 85vw) !important; }
}
"""
