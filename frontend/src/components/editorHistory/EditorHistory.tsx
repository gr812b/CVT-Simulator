import { useRef, type ReactNode } from 'react';
import { Group } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { EditorHistoryContext, type QuantityHistory } from './context';

const textControl = (target: EventTarget | null) => target instanceof HTMLElement && (
  target.isContentEditable || target instanceof HTMLTextAreaElement || (
    target instanceof HTMLInputElement && !['checkbox', 'radio', 'range', 'button', 'submit'].includes(target.type)
  )
);

export function EditorHistoryBoundary({ history, disabled = false, onRestore, children }: {
  history: QuantityHistory;
  disabled?: boolean;
  onRestore?: () => void;
  children: ReactNode;
}) {
  const identities = useRef(new WeakMap<object, string>());
  const sequence = useRef(0);
  const owns = (target: EventTarget | null, current: HTMLElement) =>
    target instanceof HTMLElement && target.closest('[data-editor-history]') === current;
  return (
    <EditorHistoryContext.Provider value={history}>
      <div data-editor-history onFocusCapture={event => {
        if (disabled || !owns(event.target, event.currentTarget) || !textControl(event.target)) return;
        let key = identities.current.get(event.target);
        if (!key) { key = `text-${++sequence.current}`; identities.current.set(event.target, key); }
        history.beginGroup(key);
      }} onBlur={event => {
        if (owns(event.target, event.currentTarget) && textControl(event.target)) history.endGroup();
      }} onPointerDown={event => {
        if (!disabled && owns(event.target, event.currentTarget)
          && event.target instanceof HTMLElement && event.target.closest('[role="slider"],input[type="range"]'))
          history.beginGroup(`drag-${++sequence.current}`);
      }} onPointerUp={event => {
        if (event.target instanceof HTMLElement && event.target.closest('[role="slider"],input[type="range"]')) history.endGroup();
      }} onPointerCancel={() => history.endGroup()}
        onKeyDown={event => {
          // Let native text editing (including menu/touch historyUndo/historyRedo) work locally.
          if (disabled || event.defaultPrevented || !owns(event.target, event.currentTarget)
            || textControl(event.target) || event.nativeEvent.isComposing || event.altKey
            || !(event.ctrlKey || event.metaKey)) return;
          const key = event.key.toLowerCase();
          const redo = key === 'y' || (key === 'z' && event.shiftKey);
          if (key !== 'z' && key !== 'y') return;
          event.preventDefault(); event.stopPropagation();
          const state = history.getSnapshot();
          if (redo ? state.canRedo : state.canUndo) {
            if (redo) history.redo(); else history.undo();
            onRestore?.();
          }
        }}>
        {children}
      </div>
    </EditorHistoryContext.Provider>
  );
}

export function UndoRedoControls({ history, disabled = false, onRestore }: {
  history: QuantityHistory;
  disabled?: boolean;
  onRestore?: () => void;
}) {
  const snapshot = history.getSnapshot();
  return <Group gap="xs" aria-label="Draft edit history">
    <Button type="button" size="xs" variant="default" disabled={disabled || !snapshot.canUndo}
      title="Undo last edit (Ctrl+Z / Command+Z outside a text field)"
      onClick={() => { history.undo(); onRestore?.(); }}>Undo</Button>
    <Button type="button" size="xs" variant="default" disabled={disabled || !snapshot.canRedo}
      title="Redo last edit (Ctrl+Shift+Z / Ctrl+Y)"
      onClick={() => { history.redo(); onRestore?.(); }}>Redo</Button>
  </Group>;
}
