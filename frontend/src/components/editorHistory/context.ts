import { createContext } from 'react';
import type { DraftHistory, DraftSnapshot } from './draftHistory';

/** Erase only the document type; quantities and commands have identical signatures. */
export type QuantityHistory = Pick<DraftHistory<unknown>,
  'subscribe' | 'setQuantity' | 'clearQuantities' | 'transaction' | 'beginGroup' | 'endGroup' | 'undo' | 'redo'
> & { getSnapshot: () => Pick<DraftSnapshot<unknown>, 'quantities' | 'epoch' | 'canUndo' | 'canRedo'> };
export const EditorHistoryContext = createContext<QuantityHistory | null>(null);
