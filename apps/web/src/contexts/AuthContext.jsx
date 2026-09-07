import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

const API_KEY_STORAGE_KEY = 'dataforge_api_key';

export function AuthProvider({ children }) {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(API_KEY_STORAGE_KEY));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async (key) => {
    try {
      const API_BASE = import.meta.env.VITE_API_URL || '';
      const response = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { 'X-API-Key': key },
      });
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
        return true;
      } else {
        // Invalid API key
        localStorage.removeItem(API_KEY_STORAGE_KEY);
        setApiKey(null);
        setUser(null);
        return false;
      }
    } catch (error) {
      console.error('Failed to fetch user:', error);
      return false;
    }
  }, []);

  useEffect(() => {
    const initAuth = async () => {
      if (apiKey) {
        await fetchUser(apiKey);
      }
      setLoading(false);
    };
    initAuth();
  }, [apiKey, fetchUser]);

  const login = async (newApiKey) => {
    localStorage.setItem(API_KEY_STORAGE_KEY, newApiKey);
    setApiKey(newApiKey);
    const success = await fetchUser(newApiKey);
    return success;
  };

  const logout = () => {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
    setApiKey(null);
    setUser(null);
  };

  const getHeaders = useCallback(() => {
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    return headers;
  }, [apiKey]);

  const value = {
    apiKey,
    user,
    loading,
    isAuthenticated: !!user,
    login,
    logout,
    getHeaders,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
