import type { PresetSummary } from '@api/client';
import styles from './SimulationsTable.module.scss';

interface SimulationsTableProps {
  presets: PresetSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  isLoading: boolean;
  error: string | null;
}

export const SimulationsTable = ({
  presets,
  selectedId,
  onSelect,
  isLoading,
  error,
}: SimulationsTableProps) => {
  const message = error ?? (isLoading ? 'Loading CINDER presets…' : 'No CINDER presets are available.');

  return (
    <div className={styles.tableContainer}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Name</th>
            <th>Source</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {presets.length === 0 ? (
            <tr className={styles.emptyRow}>
              <td colSpan={3}>{message}</td>
            </tr>
          ) : (
            <>
              <tr className={styles.sectionHeader}>
                <td colSpan={3}>Default Configurations</td>
              </tr>
              {presets.map((preset) => {
                const classes = [
                  styles.defaultRow,
                  selectedId === preset.id ? styles.selected : '',
                ].filter(Boolean).join(' ');
                return (
                  <tr key={preset.id} className={classes} onClick={() => onSelect(preset.id)}>
                    <td>{preset.name}</td>
                    <td>CINDER preset</td>
                    <td>{preset.description}</td>
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
