import { useEffect, useState } from 'react';
import { Alert, Loader, Center } from '@mantine/core';
import { api, dataOrThrow } from '@api/transport';
import GeometryScene from '@components/scene3DViewer/GeometryScene';
import type { ScenePreview } from '@components/scene3DViewer/sceneSpec';

/** One fixed default setup. Landing visitors only rotate the camera. */
export default function HomeCvtPreview() {
  const [preview, setPreview] = useState<ScenePreview | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    void api
      .GET('/api/v1/demo/scene', { signal: abort.signal })
      .then(dataOrThrow)
      .then((value) => {
        if (!abort.signal.aborted) setPreview(value);
      })
      .catch(() => {
        if (!abort.signal.aborted) setError(true);
      });
    return () => abort.abort();
  }, []);
  if (error)
    return (
      <Center h="100%" p="lg">
        <Alert title="Preview unavailable">
          The sample CVT could not load. You can still explore CINDER using the
          links on this page.
        </Alert>
      </Center>
    );
  if (!preview)
    return (
      <Center h="100%">
        <Loader aria-label="Loading sample CVT" size="sm" />
      </Center>
    );
  return <GeometryScene preview={preview} />;
}
