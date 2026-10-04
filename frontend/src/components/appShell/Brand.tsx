import { Anchor } from '@mantine/core';
import { Link } from 'react-router-dom';

export function Brand() {
  return (
    <Anchor
      component={Link}
      to="/"
      fw={900}
      size="xl"
      c="red.4"
      underline="never"
      aria-label="CINDER home"
    >
      CINDER
    </Anchor>
  );
}
