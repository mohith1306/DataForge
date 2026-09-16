import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div style={{
      padding: '40px',
      textAlign: 'center',
      fontFamily: 'system-ui, sans-serif',
      maxWidth: '500px',
      margin: '60px auto',
    }}>
      <h1 style={{ fontSize: '48px', color: '#1f2937', marginBottom: '8px' }}>
        404
      </h1>
      <h2 style={{ color: '#6b7280', marginBottom: '24px', fontWeight: 'normal' }}>
        Page not found
      </h2>
      <p style={{ color: '#9ca3af', marginBottom: '24px' }}>
        The page you're looking for doesn't exist or has been moved.
      </p>
      <Link
        to="/"
        style={{
          display: 'inline-block',
          background: '#2563eb',
          color: 'white',
          textDecoration: 'none',
          borderRadius: '6px',
          padding: '10px 24px',
          fontSize: '14px',
        }}
      >
        Back to Home
      </Link>
    </div>
  );
}
