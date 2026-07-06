/** Generic RFC 6901 helpers for a JSON-compatible CINDER document. */
export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

function tokens(pointer: string): string[] {
  if (pointer === '') return [];
  if (!pointer.startsWith('/')) throw new Error(`JSON Pointer must start with '/': ${pointer}`);
  return pointer
    .slice(1)
    .split('/')
    .map((token) => token.replace(/~1/g, '/').replace(/~0/g, '~'));
}

function isContainer(value: unknown): value is Record<string, unknown> | unknown[] {
  return typeof value === 'object' && value !== null;
}

function child(container: Record<string, unknown> | unknown[], token: string): unknown {
  if (Array.isArray(container)) {
    const index = Number(token);
    if (!Number.isInteger(index) || index < 0 || index >= container.length) {
      throw new Error(`Invalid JSON Pointer array index '${token}'.`);
    }
    return container[index];
  }
  if (!(token in container)) throw new Error(`JSON Pointer token '${token}' does not exist.`);
  return container[token];
}

export function getValueAtJsonPointer(document: unknown, pointer: string): unknown {
  let current = document;
  for (const token of tokens(pointer)) {
    if (!isContainer(current)) throw new Error(`Pointer enters a non-container at '${token}'.`);
    current = child(current, token);
  }
  return current;
}

/**
 * Replace an existing document field immutably. CINDER documents are plain JSON,
 * so cloning does not involve model classes, browser-only APIs, or CVT logic.
 */
export function setValueAtJsonPointer<T>(document: T, pointer: string, value: JsonValue): T {
  const path = tokens(pointer);
  if (path.length === 0) return value as T;

  const next = JSON.parse(JSON.stringify(document)) as unknown;
  if (!isContainer(next)) throw new Error('Document must be a JSON object or array.');

  let current: Record<string, unknown> | unknown[] = next;
  for (const token of path.slice(0, -1)) {
    const nextChild = child(current, token);
    if (!isContainer(nextChild)) throw new Error(`Pointer enters a non-container at '${token}'.`);
    current = nextChild;
  }

  const finalToken = path[path.length - 1];
  if (Array.isArray(current)) {
    const index = Number(finalToken);
    if (!Number.isInteger(index) || index < 0 || index >= current.length) {
      throw new Error(`Invalid JSON Pointer array index '${finalToken}'.`);
    }
    current[index] = value;
  } else {
    if (!(finalToken in current)) throw new Error(`JSON Pointer token '${finalToken}' does not exist.`);
    current[finalToken] = value;
  }
  return next as T;
}
