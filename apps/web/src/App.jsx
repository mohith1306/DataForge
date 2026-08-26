import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import IncidentDetail from './pages/IncidentDetail';
import ChaosLab from './pages/ChaosLab';

function NavLink({ to, children }) {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Link to={to} className={isActive ? 'active' : ''}>
      {children}
    </Link>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="nav">
          <Link to="/" style={{ fontWeight: 700, color: '#e5e5e5', fontSize: '1rem' }}>
            ⚡ DataForge
          </Link>
          <div className="nav-links">
            <NavLink to="/">Dashboard</NavLink>
            <NavLink to="/chaos">Chaos Lab</NavLink>
          </div>
        </nav>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
          <Route path="/chaos" element={<ChaosLab />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
