/** Presentation grouping shared by every library-backed selector. */
export function libraryOptions<
  T extends { name: string; owned: boolean; sample?: boolean },
>(items: T[], value: (item: T) => string) {
  return [
    { group: 'My library', items: items.filter((item) => item.owned) },
    {
      group: 'CINDER defaults',
      items: items.filter((item) => !item.owned && item.sample),
    },
    {
      group: 'Community',
      items: items.filter((item) => !item.owned && !item.sample),
    },
  ]
    .filter((group) => group.items.length)
    .map((group) => ({
      group: group.group,
      items: group.items.map((item) => ({
        value: value(item),
        label: item.name,
      })),
    }));
}
