export function hasUnsavedEditorDraft(
  serializedDocument: string,
  savedDocument: string,
  invalidQuantityCount: number,
): boolean {
  return serializedDocument !== savedDocument || invalidQuantityCount > 0;
}
