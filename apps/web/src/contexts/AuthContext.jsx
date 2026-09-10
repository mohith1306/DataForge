import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

const API_KEY_STORAGE_KEY = 'dataforge_api_key';
const DEV_TOKEN_STORAGE_KEY = 'dataforge_dev_token';
const DEV_USER_STORAGE_KEY = 'dataforge_dev_user';

export function AuthProvider({ children }) {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(API_KEY_STORAGE_KEY));
  const [devToken, setDevToken] = useState(() => localStorage.getItem(DEV_TOKEN_STORAGE_KEY));
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
      // Check for dev token first
      const savedDevToken = localStorage.getItem(DEV_TOKEN_STORAGE_KEY);
      const savedDevUser = localStorage.getItem(DEV_USER_STORAGE_KEY);
      
      if (savedDevToken && savedDevUser) {
        setDevToken(savedDevToken);
        setUser(JSON.parse(savedDevUser));
        setLoading(false);
        return;
      }
      
      // Check for API key
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

  const devLogin = async (password) => {
    try {
      const API_BASE = import.meta.env.VITE_API_URL || '';
      const response = await fetch(`${API_BASE}/api/auth/dev-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      
      if (response.ok) {
        const data = await response.json();
        localStorage.setItem(DEV_TOKEN_STORAGE_KEY, data.access_token);
        localStorage.setItem(DEV_USER_STORAGE_KEY, JSON.stringify(data.user));
        setDevToken(data.access_token);
        setUser(data.user);
        return true;
      }
      return false;
    } catch (error) {
      console.error('Dev login failed:', error);
      return false;
    }
  };

  const logout = () => {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
    localStorage.removeItem(DEV_TOKEN_STORAGE_KEY);
    localStorage.removeItem(DEV_USER_STORAGE_KEY);
    setApiKey(null);
    setDevToken(null);
    setUser(null);
  };

  const getHeaders = useCallback(() => {
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    } else if (devToken) {
      headers['Authorization'] = `Bearer ${devToken}`;
    }
    return headers;
  }, [apiKey, devToken]);

  const value = {
    apiKey,
    devToken,
    user,
    loading,
    isAuthenticated: !!user,
    login,
    devLogin,
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
