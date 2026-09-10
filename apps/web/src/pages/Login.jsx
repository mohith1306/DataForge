import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Login() {
  const [loginType, setLoginType] = useState('apikey'); // 'apikey' or 'dev'
  const [apiKey, setApiKey] = useState('');
  const [devPassword, setDevPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, devLogin } = useAuth();
  const navigate = useNavigate();

  const handleApiKeySubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const success = await login(apiKey);
      if (success) {
        navigate('/dashboard');
      } else {
        setError('Invalid API key. Please check and try again.');
      }
    } catch (err) {
      setError('Failed to authenticate. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleDevLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const success = await devLogin(devPassword);
      if (success) {
        navigate('/dashboard');
      } else {
        setError('Invalid dev password.');
      }
    } catch (err) {
      setError('Failed to authenticate. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: '#f3f4f6',
    }}>
      <div style={{
        maxWidth: '400px',
        width: '100%',
        padding: '2rem',
        backgroundColor: 'white',
        borderRadius: '8px',
        boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <h1 style={{
            fontSize: '1.5rem',
            fontWeight: 'bold',
            color: '#111827',
            margin: '0 0 0.5rem 0',
          }}>
            DataForge
          </h1>
          <p style={{
            fontSize: '0.875rem',
            color: '#6b7280',
            margin: 0,
          }}>
            Autonomous Data Reliability Engineer
          </p>
        </div>

        {/* Login Type Tabs */}
        <div style={{
          display: 'flex',
          marginBottom: '1.5rem',
          borderBottom: '1px solid #e5e7eb',
        }}>
          <button
            onClick={() => setLoginType('apikey')}
            style={{
              flex: 1,
              padding: '0.75rem',
              border: 'none',
              borderBottom: loginType === 'apikey' ? '2px solid #2563eb' : '2px solid transparent',
              backgroundColor: 'transparent',
              color: loginType === 'apikey' ? '#2563eb' : '#6b7280',
              fontWeight: loginType === 'apikey' ? '500' : '400',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            API Key
          </button>
          <button
            onClick={() => setLoginType('dev')}
            style={{
              flex: 1,
              padding: '0.75rem',
              border: 'none',
              borderBottom: loginType === 'dev' ? '2px solid #2563eb' : '2px solid transparent',
              backgroundColor: 'transparent',
              color: loginType === 'dev' ? '#2563eb' : '#6b7280',
              fontWeight: loginType === 'dev' ? '500' : '400',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            Developer
          </button>
        </div>

        {/* API Key Login Form */}
        {loginType === 'apikey' && (
          <form onSubmit={handleApiKeySubmit}>
            <div style={{ marginBottom: '1rem' }}>
              <label
                htmlFor="apiKey"
                style={{
                  display: 'block',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  color: '#374151',
                  marginBottom: '0.5rem',
                }}
              >
                API Key
              </label>
              <input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="df_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                required
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '0.875rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {error && (
              <div style={{
                padding: '0.75rem',
                backgroundColor: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '6px',
                color: '#dc2626',
                fontSize: '0.875rem',
                marginBottom: '1rem',
              }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !apiKey}
              style={{
                width: '100%',
                padding: '0.75rem',
                backgroundColor: loading || !apiKey ? '#9ca3af' : '#2563eb',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                fontSize: '0.875rem',
                fontWeight: '500',
                cursor: loading || !apiKey ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>
        )}

        {/* Dev Login Form */}
        {loginType === 'dev' && (
          <form onSubmit={handleDevLogin}>
            <div style={{ marginBottom: '1rem' }}>
              <label
                htmlFor="devPassword"
                style={{
                  display: 'block',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  color: '#374151',
                  marginBottom: '0.5rem',
                }}
              >
                Developer Password
              </label>
              <input
                id="devPassword"
                type="password"
                value={devPassword}
                onChange={(e) => setDevPassword(e.target.value)}
                placeholder="Enter dev password"
                required
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '0.875rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {error && (
              <div style={{
                padding: '0.75rem',
                backgroundColor: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '6px',
                color: '#dc2626',
                fontSize: '0.875rem',
                marginBottom: '1rem',
              }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !devPassword}
              style={{
                width: '100%',
                padding: '0.75rem',
                backgroundColor: loading || !devPassword ? '#9ca3af' : '#2563eb',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                fontSize: '0.875rem',
                fontWeight: '500',
                cursor: loading || !devPassword ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Authenticating...' : 'Dev Login'}
            </button>
          </form>
        )}

        {/* Help Section */}
        <div style={{
          marginTop: '1.5rem',
          padding: '1rem',
          backgroundColor: '#f9fafb',
          borderRadius: '6px',
          fontSize: '0.75rem',
          color: '#6b7280',
        }}>
          {loginType === 'apikey' ? (
            <>
              <p style={{ margin: '0 0 0.5rem 0', fontWeight: '500' }}>
                Don&apos;t have an API key?
              </p>
              <p style={{ margin: 0 }}>
                First time? Run: <code>curl -X POST http://localhost:8000/api/auth/setup</code>
              </p>
              <p style={{ margin: '0.5rem 0 0 0' }}>
                Or use the <strong>Developer</strong> tab with password: <code>dataforge-dev-2024</code>
              </p>
            </>
          ) : (
            <>
              <p style={{ margin: '0 0 0.5rem 0', fontWeight: '500' }}>
                Default dev password:
              </p>
              <p style={{ margin: 0 }}>
                <code>dataforge-dev-2024</code>
              </p>
              <p style={{ margin: '0.5rem 0 0 0' }}>
                Set <code>DEV_PASSWORD</code> env var to change it.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
