import type { LibraryObjectSummary } from '@api/client';
import styles from './SimulationsTable.module.scss';

interface SimulationsTableProps {
  vehicleAssemblies: LibraryObjectSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  isLoading: boolean;
  error: string | null;
}

export const SimulationsTable = ({
  vehicleAssemblies,
  selectedId,
  onSelect,
  isLoading,
  error,
}: SimulationsTableProps) => {
  const message = error ?? (isLoading ? 'Loading seeded Baja baselines…' : 'No released vehicle assemblies are available.');

  return (
    <div className={styles.tableContainer}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Vehicle baseline</th>
            <th>Source</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {vehicleAssemblies.length === 0 ? (
            <tr className={styles.emptyRow}>
              <td colSpan={3}>{message}</td>
            </tr>
          ) : (
            <>
              <tr className={styles.sectionHeader}>
                <td colSpan={3}>Released Library Baselines</td>
              </tr>
              {vehicleAssemblies.map((assembly) => {
                const classes = [
                  styles.defaultRow,
                  selectedId === assembly.id ? styles.selected : '',
                ].filter(Boolean).join(' ');
                return (
                  <tr key={assembly.id} className={classes} onClick={() => onSelect(assembly.id)}>
                    <td>{assembly.name}{assembly.isDefault ? ' · Default' : ''}</td>
                    <td>{assembly.sourceLabel ?? assembly.catalogStatus}</td>
                    <td>{assembly.description ?? 'Released database vehicle assembly.'}</td>
                  </tr>
                );
              })}
            </>
          )}
        </tbody>
      </table>
    </div>
  );
};
