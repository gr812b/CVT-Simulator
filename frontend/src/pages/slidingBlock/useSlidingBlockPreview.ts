import { useEffect, useRef, useState } from 'react';
import {
  getSlidingBlockDemo,
  previewSlidingBlock,
  type SlidingBlockDemo,
  type SlidingBlockInputs,
  type SlidingBlockPreview,
} from '@api/client';
import { useEditorHistory } from '@components/editorHistory/useEditorHistory';

const message = (cause: unknown) =>
  cause instanceof Error
    ? cause.message
    : 'Unable to update the geometry preview.';

export function useSlidingBlockPreview() {
  const draft = useEditorHistory<SlidingBlockInputs | null>(null);
  const { history, value, invalidCount } = draft;
  const [defaults, setDefaults] = useState<SlidingBlockInputs | null>(null);
  const [data, setData] = useState<SlidingBlockDemo | null>(null);
  const [reply, setReply] = useState<{
    key: string;
    attempt: number;
    result: SlidingBlockPreview;
  } | null>(null);
  const [failure, setFailure] = useState<{
    key: string | null;
    attempt: number;
    message: string;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const sequence = useRef(0);
  const key = value ? JSON.stringify(value) : null;

  useEffect(() => {
    if (defaults) return;
    let active = true;
    const controller = new AbortController();
    void getSlidingBlockDemo(controller.signal)
      .then((next) => {
        if (!active) return;
        setDefaults(next.inputs);
        setData(next);
        history.reset(next.inputs);
        setReply({
          key: JSON.stringify(next.inputs),
          attempt,
          result: { revision: 0, preview: next, findings: next.findings },
        });
        setFailure(null);
      })
      .catch((cause) => {
        if (active) setFailure({ key: null, attempt, message: message(cause) });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [defaults, history, attempt]);

  useEffect(() => {
    if (
      !key ||
      invalidCount ||
      (reply?.key === key && reply.attempt === attempt)
    )
      return;
    let active = true;
    const revision = ++sequence.current;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void previewSlidingBlock(JSON.parse(key), revision, controller.signal)
        .then((result) => {
          if (!active) return;
          if (result.revision !== revision)
            throw new Error(
              'Preview revision did not match this edit. Retry the preview.'
            );
          setReply({ key, attempt, result });
          if (result.preview) setData(result.preview);
          setFailure(null);
        })
        .catch((cause) => {
          if (active) setFailure({ key, attempt, message: message(cause) });
        });
    }, 350);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
    // A reply completes this request; it must not restart the request lifecycle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, invalidCount, attempt]);

  const current =
    invalidCount === 0 && reply?.key === key && reply?.attempt === attempt;
  const error =
    failure?.key === key && failure?.attempt === attempt
      ? failure.message
      : null;
  const findings = current ? (reply?.result.findings ?? []) : [];
  const geometryCurrent = current && reply?.result.preview != null;
  return {
    draft,
    defaults,
    data,
    error,
    findings,
    geometryCurrent,
    loadsCurrent: geometryCurrent && findings.length === 0,
    invalid: invalidCount > 0,
    loading: !current && !error && invalidCount === 0,
    stale: data !== null && !geometryCurrent,
    retry: () => setAttempt((n) => n + 1),
    restoreDefaults: () => {
      if (!defaults) return;
      history.endGroup();
      history.transaction(() => {
        history.clearQuantities('sliding:');
        history.setValue(defaults);
      });
    },
  };
}
