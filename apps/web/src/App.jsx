import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import Dashboard from './pages/Dashboard';

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="nav">
          <Link to="/" style={{ fontWeight: 700, color: '#e5e5e5', fontSize: '1rem' }}>
            DataForge
          </Link>
          <Link to="/">Dashboard</Link>
        </nav>
        <Routes>
          <Route path="/" element={<Dashboard />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
