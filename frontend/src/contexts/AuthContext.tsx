import { createContext, useContext, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getMe, logout as apiLogout } from '../api/auth';
import type { User } from '../types';

interface AuthContextValue {
  user: User;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const { data: user, isLoading, error } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: getMe,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) return <div className="loading">Loading...</div>;

  if (error || !user) {
    window.location.href = '/login';
    return null;
  }

  const logout = async () => {
    setIsLoggingOut(true);
    try {
      await apiLogout();
    } finally {
      queryClient.clear();
      window.location.href = '/login';
    }
  };

  if (isLoggingOut) return <div className="loading">Logging out...</div>;

  return (
    <AuthContext.Provider value={{ user, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
