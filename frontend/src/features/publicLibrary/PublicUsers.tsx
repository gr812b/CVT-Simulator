import { useEffect, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Group,
  LoadingOverlay,
  Pagination,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useSearchParams } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';
import { getUsers, type PublicUserPage } from '../community/api';
import { SchoolSelect } from '../community/SchoolSelect';
import { AuthorLink } from '../community/AuthorLink';
import { message } from '../experiments/api';

export function PublicUsers() {
  const [params, setParams] = useSearchParams();
  const search = params.get('q') ?? '';
  const [query] = useDebouncedValue(search, 250);
  const school = params.get('school') ?? '';
  const userId = params.get('user') ?? undefined;
  const page = Math.max(1, Number(params.get('page')) || 1);
  const [data, setData] = useState<PublicUserPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const update = (key: string, value: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== 'page') next.delete('page');
        if (key !== 'user') next.delete('user');
        return next;
      },
      { replace: key === 'q' },
    );
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError(null);
    void getUsers(
      { q: query, school, user_id: userId, limit: 24, offset: (page - 1) * 24 },
      abort.signal,
    )
      .then((next) => {
        if (!abort.signal.aborted) setData(next);
      })
      .catch((cause) => {
        if (!abort.signal.aborted) setError(message(cause));
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [query, school, userId, page, retry]);
  return (
    <Stack>
      <Group align="start">
        <TextInput
          label="Find people"
          placeholder="Search names or schools"
          value={search}
          onChange={(event) => update('q', event.currentTarget.value)}
        />
        <SchoolSelect
          label="Filter by school"
          description={null}
          value={school}
          onChange={(value) => update('school', value ?? '')}
          w={340}
          maw="100%"
        />
        {userId && (
          <Button variant="subtle" onClick={() => update('user', '')}>
            Browse all people
          </Button>
        )}
      </Group>
      <Box pos="relative" mih={300} aria-busy={loading}>
        <LoadingOverlay visible={loading} />
        <div inert={loading}>
          {error ? (
            <Alert color="red">
              {error}
              <Button variant="subtle" onClick={() => setRetry((x) => x + 1)}>
                Try again
              </Button>
            </Alert>
          ) : (
            <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
              {data?.items.map((user) => (
                <Paper withBorder p="lg" key={user.id}>
                  <Group wrap="nowrap">
                    <Avatar name={user.display_name} color="initials" />
                    <div>
                      <Text fw={600}>
                        <AuthorLink id={user.id} name={user.display_name} />
                      </Text>
                      <Text c="dimmed" size="sm">
                        {user.school || 'Independent member'}
                      </Text>
                    </div>
                  </Group>
                </Paper>
              ))}
            </SimpleGrid>
          )}
          {!loading && data?.total === 0 && (
            <Text c="dimmed">No matching people yet.</Text>
          )}
        </div>
      </Box>
      {data && data.total > 24 && (
        <Group justify="center" py="xl">
          <Pagination
            value={page}
            total={Math.ceil(data.total / 24)}
            onChange={(next) => update('page', String(next))}
          />
        </Group>
      )}
    </Stack>
  );
}
