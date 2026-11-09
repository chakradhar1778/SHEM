import { useEffect, useRef, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate, Navigate } from 'react-router-dom';
import { OverviewPage } from './pages/OverviewPage';
import { HomeGate } from './components/system/HomeGate';
import { DataGate } from './components/system/DataGate';
import { ConnectionBanner } from './components/system/ConnectionBanner';
import { HomeSetupPage } from './pages/HomeSetupPage';
import { DevicesHomePage } from './pages/devices/DevicesHomePage';
import { AddDevicePage } from './pages/devices/AddDevicePage';
import { CategoryPage } from './pages/devices/CategoryPage';
import { ApplianceFormPage } from './pages/devices/ApplianceFormPage';
import { RoomsGridPage } from './pages/devices/RoomsGridPage';
import { HomeSummaryPage } from './pages/devices/HomeSummaryPage';
import { NavIcon, ShemLogo, type NavIconName } from './components/nav/NavIcons';
import { BillPage } from './pages/BillPage';
import { SettingsPage } from './pages/SettingsPage';
import { TargetPage } from './pages/TargetPage';
import { InsightsPage } from './pages/InsightsPage';
import { EnergyTodayPage } from './pages/EnergyTodayPage';
import { AIEnergyGuidePage } from './pages/AIEnergyGuidePage';
import { LiveUsagePage } from './pages/LiveUsagePage';
import { ApplianceMapPage } from './pages/ApplianceMapPage';
import { LiveDataProvider } from './context/LiveDataContext';
import { HomeProvider } from './context/HomeContext';
import { InventoryProvider } from './context/InventoryContext';
import { BillProvider } from './context/BillContext';
import { TargetProvider } from './context/TargetContext';
import { AIProvider } from './context/AIContext';
import { AIAssistant } from './components/ai/AIAssistant';
import { useHomeConfig } from './hooks/useHomeConfig';
import './styles/ui.css';
import './styles/charts.css';
import './App.css';

interface NavDestination {
  path: string;
  label: string;
  icon: NavIconName;
}

const NAV_DESTINATIONS: NavDestination[] = [
  { path: '/', label: 'Home', icon: 'home' },
  { path: '/devices', label: 'Devices', icon: 'devices' },
  { path: '/live', label: 'Live Usage', icon: 'live' },
  { path: '/bill', label: 'Bill', icon: 'bill' },
  { path: '/target', label: 'Target', icon: 'target' },
  { path: '/insights', label: 'Insights', icon: 'insights' },
];

/** Screens that are tab roots — everything else shows a back button. */
const TAB_ROOTS = new Set(['/', '/devices', '/live', '/bill', '/target', '/insights']);

function isTabActive(dest: string, pathname: string): boolean {
  if (dest === '/') return pathname === '/' || pathname === '/setup' || pathname === '/dashboard';
  if (dest === '/insights') return pathname.startsWith('/insights') || pathname === '/map';
  return pathname === dest || pathname.startsWith(`${dest}/`);
}

function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { config } = useHomeConfig();
  const showBack = !TAB_ROOTS.has(location.pathname);
  const initial = (config.homeName || 'R').trim().charAt(0).toUpperCase();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMenuOpen(false), [location.pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [menuOpen]);

  return (
    <div className="app-viewport-wrapper">
      <div className="mobile-shell">
        <header className="mobile-topbar" aria-label="SHEM Header">
          <div className="mobile-topbar__brand-wrap">
            {showBack && (
              <button
                type="button"
                className="mobile-topbar__back-btn"
                onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/'))}
                aria-label="Go back"
              >
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M15 18l-6-6 6-6" />
                </svg>
              </button>
            )}
            <NavLink to="/" className="mobile-topbar__brand" title="SHEM Home">
              <ShemLogo size={24} />
              <span className="mobile-topbar__title">SHEM</span>
            </NavLink>
          </div>

          <div className="mobile-topbar__actions">
            <button type="button" className="mobile-topbar__btn" title="Notifications" aria-label="Notifications">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="mobile-topbar__badge-dot" aria-hidden="true" />
            </button>
            <div className="profile-menu" ref={menuRef}>
              <button
                type="button"
                className="mobile-topbar__avatar"
                aria-label="Account menu"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((o) => !o)}
              >
                {initial}
              </button>
              {menuOpen && (
                <div className="profile-menu__panel" role="menu">
                  <div className="profile-menu__who">
                    <b>{config.homeName || 'My Home'}</b>
                    <span>{[config.homeType, config.location].filter(Boolean).join(' · ')}</span>
                  </div>
                  <NavLink to="/setup" role="menuitem" className="profile-menu__item">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 11 12 4l9 7M5 10v10h14V10M10 20v-6h4v6" /></svg>
                    Configure home
                  </NavLink>
                  <NavLink to="/settings" role="menuitem" className="profile-menu__item">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" /></svg>
                    Settings
                  </NavLink>
                </div>
              )}
            </div>
          </div>
        </header>

        <ConnectionBanner />

        <main className="mobile-main">
          <DataGate>
            <Routes>
              <Route path="/" element={<HomeGate />} />
              <Route path="/overview" element={<Navigate to="/" replace />} />
              <Route path="/dashboard" element={<OverviewPage />} />
              <Route path="/setup" element={<HomeSetupPage isEditMode={config.isConfigured} />} />
              <Route path="/onboarding" element={<Navigate to="/setup" replace />} />

              <Route path="/devices" element={<DevicesHomePage />} />
              <Route path="/devices/add" element={<AddDevicePage />} />
              <Route path="/devices/category/:categoryId" element={<CategoryPage />} />
              <Route path="/devices/mine" element={<Navigate to="/devices" replace />} />
              <Route path="/devices/new/:catalogueId" element={<ApplianceFormPage />} />
              <Route path="/devices/custom" element={<ApplianceFormPage />} />
              <Route path="/devices/edit/:applianceId" element={<ApplianceFormPage />} />
              <Route path="/devices/rooms" element={<RoomsGridPage />} />
              <Route path="/devices/summary" element={<HomeSummaryPage />} />

              <Route path="/bill" element={<BillPage />} />
              <Route path="/target" element={<TargetPage />} />
              <Route path="/insights" element={<InsightsPage />} />
              <Route path="/insights/daily" element={<EnergyTodayPage />} />
              <Route path="/insights/guide" element={<AIEnergyGuidePage />} />
              <Route path="/live" element={<LiveUsagePage />} />
              <Route path="/live-usage" element={<Navigate to="/live" replace />} />
              <Route path="/map" element={<ApplianceMapPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </DataGate>
        </main>

        <nav className="mobile-bottomnav" aria-label="Bottom Navigation">
          <div className="mobile-bottomnav__inner">
            {NAV_DESTINATIONS.map((dest) => {
              const active = isTabActive(dest.path, location.pathname);
              return (
                <NavLink
                  key={dest.path}
                  to={dest.path}
                  end={dest.path === '/'}
                  className={`bottomnav-tab ${dest.icon === 'live' ? 'bottomnav-tab--live' : ''} ${active ? 'active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                >
                  <NavIcon name={dest.icon} size={26} />
                  <span className="bottomnav-tab__label">{dest.label}</span>
                  {active && <span className="bottomnav-tab__indicator" aria-hidden="true" />}
                </NavLink>
              );
            })}
          </div>
        </nav>
        <AIAssistant />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <HomeProvider>
        <LiveDataProvider>
          <InventoryProvider>
            <BillProvider>
              <TargetProvider>
                <AIProvider>
                  <AppLayout />
                </AIProvider>
              </TargetProvider>
            </BillProvider>
          </InventoryProvider>
        </LiveDataProvider>
      </HomeProvider>
    </BrowserRouter>
  );
}

