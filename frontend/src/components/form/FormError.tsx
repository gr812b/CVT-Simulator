import { useEffect, useRef, type ReactNode } from 'react';
import { Alert } from '@mantine/core';

export function FormError({ children, title = 'Please check this', ...props }: {
  children: ReactNode;
  title?: string;
  role?: string;
  color?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    node.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'center' });
    node.focus({ preventScroll: true });
    if (!reduced) {
      node.animate([
        { transform: 'translateX(0)' },
        { transform: 'translateX(-5px)' },
        { transform: 'translateX(5px)' },
        { transform: 'translateX(-3px)' },
        { transform: 'translateX(0)' },
      ], { duration: 280, iterations: 1 });
    }
  }, []);
  return (
    <Alert {...props} ref={ref} tabIndex={-1} color="red" title={title} role="alert">
      {children}
    </Alert>
  );
}
