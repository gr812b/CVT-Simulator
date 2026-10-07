import type { DisplayUnit, QuantityDimension } from '../../utils/units';

export interface QuantityDraft {
  text: string;
  entryUnit: DisplayUnit;
  dimension: QuantityDimension;
  sourceValue: number | null;
  valueSi: number | null;
  error?: string;
  documentPath?: string;
}
export interface DraftFrame<T> {
  value: T;
  quantities: Readonly<Record<string, QuantityDraft>>;
}
export interface DraftSnapshot<T> extends DraftFrame<T> {
  canUndo: boolean;
  canRedo: boolean;
  dirty: boolean;
  invalidCount: number;
  epoch: number;
}
function atPointer(root: unknown, pointer: string): unknown {
  let value = root;
  for (const part of pointer.split('/').slice(1)) {
    if (value === null || typeof value !== 'object') return undefined;
    value = (value as Record<string, unknown>)[part.replace(/~1/g, '/').replace(/~0/g, '~')];
  }
  return value;
}
const equal = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** In-memory editing history. Display preferences and preview/camera state never enter it.
 * A transaction combines a quantity's raw text and canonical edit; focus/drag
 * groups combine repeated edits. Saved revisions are not an undo stack.
 */
export class DraftHistory<T> {
  private frame: DraftFrame<T>;
  private saved: T;
  private past: DraftFrame<T>[] = [];
  private future: DraftFrame<T>[] = [];
  private listeners = new Set<() => void>();
  private group: string | null = null;
  private groupStart: DraftFrame<T> | null = null;
  private groupRecorded = false;
  private groupFuture: DraftFrame<T>[] = [];
  private depth = 0;
  private before: DraftFrame<T> | null = null;
  private epoch = 0;
  private snapshot: DraftSnapshot<T>;

  constructor(initial: T, private readonly limit = 100) {
    this.saved = structuredClone(initial);
    this.frame = { value: structuredClone(initial), quantities: {} };
    this.snapshot = this.buildSnapshot();
  }
  getSnapshot = (): DraftSnapshot<T> => this.snapshot;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private buildSnapshot(): DraftSnapshot<T> {
    const drafts = Object.values(this.frame.quantities);
    return { ...this.frame, canUndo: this.past.length > 0, canRedo: this.future.length > 0,
      dirty: !equal(this.frame.value, this.saved) || drafts.length > 0,
      invalidCount: drafts.filter(draft => draft.error !== undefined).length, epoch: this.epoch };
  }
  private publish() {
    this.snapshot = this.buildSnapshot();
    this.listeners.forEach(listener => listener());
  }
  transaction = (action: () => void): void => {
    const outer = this.depth === 0;
    if (outer) this.before = this.frame;
    this.depth++;
    try { action(); }
    catch (error) {
      if (outer && this.before) this.frame = this.before;
      throw error;
    } finally {
      this.depth--;
      if (outer) {
        const previous = this.before!;
        this.before = null;
        if (!equal(previous, this.frame)) {
          if (!this.group || !this.groupRecorded) {
            this.past.push(structuredClone(this.groupStart ?? previous));
            if (this.past.length > this.limit) this.past.shift();
            this.groupRecorded = this.group !== null;
          }
          this.future = [];
          this.publish();
        }
      }
    }
  };
  setValue = (next: T | ((current: T) => T)): void => {
    this.transaction(() => {
      const value = typeof next === 'function' ? (next as (current: T) => T)(structuredClone(this.frame.value)) : next;
      const quantities = Object.fromEntries(Object.entries(this.frame.quantities).filter(([, draft]) =>
        !draft.documentPath || atPointer(value, draft.documentPath) != null,
      ));
      this.frame = { value: structuredClone(value), quantities };
    });
  };
  setQuantity = (key: string, draft: QuantityDraft | undefined): void => {
    this.transaction(() => {
      const quantities = { ...this.frame.quantities };
      if (draft) quantities[key] = { ...draft };
      else delete quantities[key];
      this.frame = { ...this.frame, quantities };
    });
  };
  clearQuantities = (prefix: string): void => {
    this.transaction(() => {
      this.frame = { ...this.frame, quantities: Object.fromEntries(
        Object.entries(this.frame.quantities).filter(([key]) => !key.startsWith(prefix)),
      ) };
    });
  };
  beginGroup = (key: string): void => {
    if (this.group === key) return;
    this.endGroup();
    this.group = key;
    this.groupStart = this.frame;
    this.groupFuture = this.future.slice();
  };
  endGroup = (): void => {
    // Typing an equivalent quantity then normalizing it must not add an undo/revision.
    if (this.groupRecorded && this.groupStart && equal(this.groupStart, this.frame)) {
      this.past.pop();
      this.future = this.groupFuture;
      this.publish();
    }
    this.group = null;
    this.groupStart = null;
    this.groupFuture = [];
    this.groupRecorded = false;
  };
  undo = (): void => {
    this.endGroup();
    const prior = this.past.pop();
    if (!prior) return;
    this.future.push(this.frame);
    this.frame = prior;
    this.epoch++;
    this.publish();
  };
  redo = (): void => {
    this.endGroup();
    const next = this.future.pop();
    if (!next) return;
    this.past.push(this.frame);
    this.frame = next;
    this.epoch++;
    this.publish();
  };
  reset = (value: T): void => {
    this.group = null; this.groupStart = null; this.groupRecorded = false;
    this.past = []; this.future = []; this.groupFuture = [];
    this.saved = structuredClone(value);
    this.frame = { value: structuredClone(value), quantities: {} };
    this.epoch++;
    this.publish();
  };
  markSaved = (value: T): void => {
    this.endGroup();
    this.saved = structuredClone(value);
    this.frame = { value: structuredClone(value), quantities: {} };
    this.epoch++;
    this.publish();
  };
}
