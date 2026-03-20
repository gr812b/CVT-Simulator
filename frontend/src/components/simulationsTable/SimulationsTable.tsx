import type { SavedSimulation } from '@utils/localStorage';
import type { GroupedSimulations } from '@hooks/useSimulations';
import styles from './SimulationsTable.module.scss';

interface SimulationsTableProps {
  groupedSimulations: GroupedSimulations;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
};

interface SimulationRowProps {
  simulation: SavedSimulation;
  isSelected: boolean;
  onClick: () => void;
  variant?: 'default' | 'recentRun';
}

const SimulationRow = ({ simulation, isSelected, onClick, variant }: SimulationRowProps) => {
  const rowClasses = [
    isSelected && styles.selected,
    variant === 'default' && styles.defaultRow,
    variant === 'recentRun' && styles.recentRunRow,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <tr className={rowClasses} onClick={onClick}>
      <td>{simulation.name}</td>
      <td>{formatDate(simulation.createdAt)}</td>
      <td>{formatDate(simulation.updatedAt)}</td>
    </tr>
  );
};

interface SectionProps {
  title: string;
  simulations: SavedSimulation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  variant?: 'default' | 'recentRun';
}

const TableSection = ({ title, simulations, selectedId, onSelect, variant }: SectionProps) => {
  if (simulations.length === 0) return null;

  return (
    <>
      <tr className={styles.sectionHeader}>
        <td colSpan={3}>{title}</td>
      </tr>
      {simulations.map((sim) => (
        <SimulationRow
          key={sim.id}
          simulation={sim}
          isSelected={selectedId === sim.id}
          onClick={() => onSelect(sim.id)}
          variant={variant}
        />
      ))}
    </>
  );
};

export const SimulationsTable = ({
  groupedSimulations,
  selectedId,
  onSelect,
}: SimulationsTableProps) => {
  const { defaults, saved, recentRuns } = groupedSimulations;
  const isEmpty = defaults.length === 0 && saved.length === 0 && recentRuns.length === 0;

  return (
    <div className={styles.tableContainer}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Name</th>
            <th>Created</th>
            <th>Last Modified</th>
          </tr>
        </thead>
        <tbody>
          {isEmpty ? (
            <tr className={styles.emptyRow}>
              <td colSpan={3}>No Saved Parameter Sets...</td>
            </tr>
          ) : (
            <>
              <TableSection
                title="Default Configurations"
                simulations={defaults}
                selectedId={selectedId}
                onSelect={onSelect}
                variant="default"
              />
              <TableSection
                title="Saved Parameter Sets"
                simulations={saved}
                selectedId={selectedId}
                onSelect={onSelect}
              />
              <TableSection
                title="Recent Runs"
                simulations={recentRuns}
                selectedId={selectedId}
                onSelect={onSelect}
                variant="recentRun"
              />
            </>
          )}
        </tbody>
      </table>
    </div>
  );
};
