import type { ReactNode } from 'react';
import { Anchor } from '@mantine/core';
import { Link, useLocation } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';

interface ReturnContext {
  backTo: string;
  backLabel: string;
  parentState?: unknown;
}
function returnContext(value: unknown): ReturnContext | null {
  if (!value || typeof value !== 'object') return null;
  const state = value as Partial<ReturnContext>;
  return typeof state.backTo === 'string' &&
    state.backTo.startsWith('/') &&
    !state.backTo.startsWith('//') &&
    typeof state.backLabel === 'string'
    ? (state as ReturnContext)
    : null;
}
export function ConfigurationLink({
  to,
  from,
  children,
}: {
  to: string;
  from: string;
  children: ReactNode;
}) {
  const location = useLocation();
  return (
    <Anchor
      component={Link}
      to={to}
      state={{
        backTo: location.pathname + location.search + location.hash,
        backLabel: from,
        parentState: location.state,
      }}
    >
      {children}
    </Anchor>
  );
}
export function ConfigurationBack({
  to,
  label,
}: {
  to: string;
  label: string;
}) {
  const location = useLocation();
  const context = returnContext(location.state);
  return (
    <Button
      component={Link}
      to={context?.backTo ?? to}
      state={context?.parentState ?? null}
      variant="subtle"
      w="fit-content"
    >
      Back to {context?.backLabel ?? label}
    </Button>
  );
}
