import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import * as auth from '@api/auth';
import { ApiClientError, SESSION_EXPIRED, setCsrfToken } from '@api/transport';
import { normalizeUnitPreferences, type UnitPreferences } from '@utils/units';

interface AuthState {
  session: auth.AuthSession | null;
  loading: boolean;
  error: string | null;
  unitPreferences: UnitPreferences;
  refresh: () => Promise<void>;
  accept: (session: auth.AuthSession) => void;
  saveUnitPreferences: (preferences: UnitPreferences) => Promise<void>;
  signOut: () => Promise<void>;
}
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<auth.AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const revision = useRef(0);
  const channel = useRef<BroadcastChannel | null>(null);
  const setCurrent = useCallback((next: auth.AuthSession | null) => {
    revision.current += 1;
    setCsrfToken(next?.csrf_token ?? null);
    setSession(next);
    setError(null);
    setLoading(false);
  }, []);
  const refresh = useCallback(async () => {
    const requestRevision = revision.current;
    try {
      const next = await auth.getSession();
      if (revision.current === requestRevision) setCurrent(next);
    } catch (reason) {
      if (revision.current !== requestRevision) return;
      if (reason instanceof ApiClientError && reason.status === 401) setCurrent(null);
      else {
        setError('Unable to reach CINDER. Check your connection and try again.');
        setLoading(false);
      }
    }
  }, [setCurrent]);
  useEffect(() => {
    localStorage.removeItem('cinder-simulation-case-v2');
    localStorage.removeItem('cinder-simulation-case-source-v2');
    sessionStorage.removeItem('cinder-active-run-id-v3');
    void refresh();
    const expired = () => setCurrent(null);
    const focused = () => {
      void refresh();
    };
    window.addEventListener(SESSION_EXPIRED, expired);
    window.addEventListener('focus', focused);
    if ('BroadcastChannel' in window) {
      channel.current = new BroadcastChannel('cinder-auth');
      channel.current.onmessage = () => {
        setCurrent(null);
        void refresh();
      };
    }
    return () => {
      window.removeEventListener(SESSION_EXPIRED, expired);
      window.removeEventListener('focus', focused);
      channel.current?.close();
    };
  }, [refresh, setCurrent]);
  useEffect(() => {
    if (!session) return;
    const delay = Math.max(0, Date.parse(session.expires_at) - Date.now());
    const timer = window.setTimeout(() => setCurrent(null), Math.min(delay, 2147483647));
    return () => window.clearTimeout(timer);
  }, [session, setCurrent]);
  const accept = useCallback(
    (next: auth.AuthSession) => {
      setCurrent(next);
      channel.current?.postMessage('changed');
    },
    [setCurrent],
  );
  const saveUnitPreferences = useCallback(async (preferences: UnitPreferences) => {
    accept(await auth.updateUnitPreferences(preferences));
  }, [accept]);
  const signOut = useCallback(async () => {
    try {
      await auth.logout();
    } catch (reason) {
      if (!(reason instanceof ApiClientError && reason.status === 401)) throw reason;
    }
    setCurrent(null);
    channel.current?.postMessage('changed');
  }, [setCurrent]);
  const unitPreferences = useMemo(
    () => normalizeUnitPreferences(session?.user.unit_preferences),
    [session?.user.unit_preferences],
  );
  const value = useMemo(
    () => ({ session, loading, error, unitPreferences, refresh, accept, saveUnitPreferences, signOut }),
    [session, loading, error, unitPreferences, refresh, accept, saveUnitPreferences, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth requires AuthProvider.');
  return context;
}
