import { BrowserRouter, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Dashboard from './pages/Dashboard';
import IncidentDetail from './pages/IncidentDetail';
import ChaosLab from './pages/ChaosLab';
import Connectors from './pages/Connectors';
import DatabaseDetail from './pages/DatabaseDetail';
import Login from './pages/Login';

function NavLink({ to, children }) {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Link to={to} className={isActive ? 'active' : ''}>
      {children}
    </Link>
  );
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        color: '#6b7280',
      }}>
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function AppNav() {
  const { user, logout, isAuthenticated } = useAuth();

  return (
    <nav className="nav">
      <Link to="/" style={{ fontWeight: 700, color: '#e5e5e5', fontSize: '1rem' }}>
        ⚡ DataForge
      </Link>
      <div className="nav-links">
        <NavLink to="/">Databases</NavLink>
        <NavLink to="/dashboard">Dashboard</NavLink>
        <NavLink to="/chaos">Chaos Lab</NavLink>
        {isAuthenticated && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginLeft: '1rem' }}>
            <span style={{ color: '#9ca3af', fontSize: '0.875rem' }}>
              {user?.email || user?.name}
            </span>
            <button
              onClick={logout}
              style={{
                background: 'none',
                border: '1px solid #4b5563',
                color: '#9ca3af',
                padding: '0.25rem 0.75rem',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '0.75rem',
              }}
            >
              Logout
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}

function AppRoutes() {
  return (
    <>
      <AppNav />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={
          <ProtectedRoute>
            <Connectors />
          </ProtectedRoute>
        } />
        <Route path="/dashboard" element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        } />
        <Route path="/databases/:id" element={
          <ProtectedRoute>
            <DatabaseDetail />
          </ProtectedRoute>
        } />
        <Route path="/incidents/:id" element={
          <ProtectedRoute>
            <IncidentDetail />
          </ProtectedRoute>
        } />
        <Route path="/chaos" element={
          <ProtectedRoute>
            <ChaosLab />
          </ProtectedRoute>
        } />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="app">
          <AppRoutes />
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}
