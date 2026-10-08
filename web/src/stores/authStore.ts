import { create } from 'zustand';
import { api } from '../lib/api';
import { User, UserRole } from '../types/api';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
  hasRole: (role: UserRole) => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: localStorage.getItem('idra_access_token'),
  isAuthenticated: !!localStorage.getItem('idra_access_token'),
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.login(email, password);
      localStorage.setItem('idra_access_token', res.access_token);
      set({ token: res.access_token, isAuthenticated: true });

      const user = await api.getMe();
      set({ user, isLoading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Login failed';
      set({ error: message, isLoading: false, isAuthenticated: false, token: null });
      localStorage.removeItem('idra_access_token');
      throw err;
    }
  },

  logout: () => {
    localStorage.removeItem('idra_access_token');
    set({ user: null, token: null, isAuthenticated: false, error: null });
  },

  checkAuth: async () => {
    const token = localStorage.getItem('idra_access_token');
    if (!token) {
      set({ user: null, isAuthenticated: false });
      return;
    }

    set({ isLoading: true });
    try {
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      localStorage.removeItem('idra_access_token');
      set({ user: null, token: null, isAuthenticated: false, isLoading: false });
    }
  },

  hasRole: (role: UserRole) => {
    const { user } = get();
    if (!user) return false;
    if (user.role === 'ADMIN') return true;
    if (user.role === 'RESPONDER' && role !== 'ADMIN') return true;
    return user.role === role;
  },
}));

window.addEventListener('idra:unauthorized', () => {
  useAuthStore.getState().logout();
});
