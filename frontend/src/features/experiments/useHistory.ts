import { useCallback, useState } from 'react';

/** Local editor state, not a second API contract. Every action is reversible. */
export function useHistory<T>(initial: T) {
  const [history, setHistory] = useState({
    past: [] as T[],
    present: initial,
    future: [] as T[],
  });
  const change = useCallback(
    (next: T) =>
      setHistory((previous) =>
        JSON.stringify(previous.present) === JSON.stringify(next)
          ? previous
          : {
              past: [...previous.past, previous.present].slice(-60),
              present: next,
              future: [],
            },
      ),
    [],
  );
  const reset = useCallback(
    (next: T) => setHistory({ past: [], present: next, future: [] }),
    [],
  );
  const undo = () =>
    setHistory((previous) =>
      previous.past.length
        ? {
            past: previous.past.slice(0, -1),
            present: previous.past.at(-1)!,
            future: [previous.present, ...previous.future],
          }
        : previous,
    );
  const redo = () =>
    setHistory((previous) =>
      previous.future.length
        ? {
            past: [...previous.past, previous.present],
            present: previous.future[0],
            future: previous.future.slice(1),
          }
        : previous,
    );
  return {
    value: history.present,
    change,
    reset,
    undo,
    redo,
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
  };
}
