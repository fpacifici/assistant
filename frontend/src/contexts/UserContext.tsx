import { createContext, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchUsers } from '../api/users';

interface UserContextValue {
  userId: string;
}

const UserContext = createContext<UserContextValue | null>(null);

export function UserProvider({ children }: { children: React.ReactNode }) {
  const { data: users, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: () => fetchUsers(1),
    staleTime: Infinity,
  });

  if (isLoading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Failed to load user: {error.message}</div>;

  const userId = users?.[0]?.uid;
  if (!userId) {
    return (
      <div className="error">
        No user found. Create one first via the API:
        <pre>
          curl -X POST http://localhost:8000/user -H 'Content-Type: application/json' -d
          '{'"email":"you@example.com","firstname":"Your","lastname":"Name"'}'
        </pre>
      </div>
    );
  }

  return (
    <UserContext.Provider value={{ userId }}>
      {children}
    </UserContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useUser(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error('useUser must be used within UserProvider');
  return ctx;
}
