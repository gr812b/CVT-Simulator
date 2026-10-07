import { useState, useSyncExternalStore } from 'react';
import { DraftHistory } from './draftHistory';

export function useEditorHistory<T>(initial: T | (() => T), retained?: DraftHistory<T>) {
  const [history] = useState(() => retained ?? new DraftHistory(
    typeof initial === 'function' ? (initial as () => T)() : initial,
  ));
  const snapshot = useSyncExternalStore(history.subscribe, history.getSnapshot, history.getSnapshot);
  return { history, ...snapshot, setValue: history.setValue };
}
