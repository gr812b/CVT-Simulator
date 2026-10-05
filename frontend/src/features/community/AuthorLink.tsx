import { Anchor, Text } from '@mantine/core';
import { Link } from 'react-router-dom';

export function AuthorLink({ name, id }: { name: string; id?: string | null }) {
  return id ? (
    <Anchor
      component={Link}
      to={`/catalog?kind=users&user=${encodeURIComponent(id)}`}
      inherit
    >
      {name}
    </Anchor>
  ) : (
    <Text component="span" inherit>
      {name}
    </Text>
  );
}
