import { useState, useEffect, useRef } from 'react';
import styles from './Dashboard.module.scss'
import bajaLogo from '@assets/baja_logo.png'
import { Button } from '@components/button/Button';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { useNavigate } from 'react-router-dom';
import { useParameter } from '@contexts/ParameterContext';
import { useLoading } from '@contexts/LoadingContext';
import { useRunSimulation } from '@hooks/useRunSimulation';
import { 
  getAllSimulations, 
  deleteSimulation,
  exportSimulation,
  importSimulation,
  getRecentRuns,
  isRecentRun,
  setLoadedSimulationId,
  clearSessionParameters,
  type SavedSimulation 
} from '@utils/localStorage';
import { getDefaultSimulations, isDefaultSimulation } from '@constants/defaultSimulations';
import Play from '@assets/icons/play.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import TrashCan from '@assets/icons/trash_can.svg?react';
import Plus from '@assets/icons/plus.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';

export const Dashboard = () => {
  const navigate = useNavigate();
  const { setMultipleParameters } = useParameter();
  const { isLoading, loadingMessage } = useLoading();
  const { runSimulation } = useRunSimulation();
  const [simulations, setSimulations] = useState<SavedSimulation[]>([]);
  const [selectedSimulation, setSelectedSimulation] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load parameter sets on mount
  useEffect(() => {
    loadSimulations();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadSimulations = () => {
    const userSimulations = getAllSimulations();
    const defaultSimulations = getDefaultSimulations();
    const recentRuns = getRecentRuns();
    // Combine: defaults first, then user simulations, then recent runs
    const allSimulations = [...defaultSimulations, ...userSimulations, ...recentRuns];
    setSimulations(allSimulations);
    // Clear selection if the selected parameter set no longer exists
    if (selectedSimulation && !allSimulations.find(s => s.id === selectedSimulation)) {
      setSelectedSimulation(null);
    }
  };

  const handleRun = async () => {
    if (!selectedSimulation) return;

    const simulation = simulations.find(s => s.id === selectedSimulation);
    if (!simulation) return;

    await runSimulation(simulation.parameters);
  };

  const handleEdit = () => {
    if (!selectedSimulation) return;

    const simulation = simulations.find(s => s.id === selectedSimulation);
    if (!simulation) return;

    // Load the parameter set into the global state
    setMultipleParameters(simulation.parameters);
    
    // Set which simulation was loaded (for comparison in Input page)
    setLoadedSimulationId(selectedSimulation);
    
    // Navigate to input page
    navigate('/input');
  };

  const handleDelete = () => {
    if (!selectedSimulation) return;

    const simulation = simulations.find(s => s.id === selectedSimulation);
    if (!simulation) return;

    // Prevent deletion of default simulations and recent runs
    if (isDefaultSimulation(selectedSimulation)) {
      alert('Default parameter sets cannot be deleted.');
      return;
    }

    if (isRecentRun(selectedSimulation)) {
      alert('Recent runs cannot be deleted. They will automatically be removed as new runs are added.');
      return;
    }

    if (confirm(`Are you sure you want to delete the parameter set "${simulation.name}"?`)) {
      deleteSimulation(selectedSimulation);
      loadSimulations();
    }
  };

  const handleRowClick = (id: string) => {
    setSelectedSimulation(id === selectedSimulation ? null : id);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  const handleExport = () => {
    if (!selectedSimulation) return;

    const simulation = simulations.find(s => s.id === selectedSimulation);
    if (!simulation) return;

    exportSimulation(simulation);
  };

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const handleNew = () => {
    clearSessionParameters();
    setLoadedSimulationId(null);
    navigate('/input');
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      await importSimulation(file);
      loadSimulations();
      // Reset the input so the same file can be imported again
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error) {
      console.error('Import failed:', error);
      alert('Failed to import parameter set. Please check the file format.');
    }
  };
  
  const hasSelection = !!selectedSimulation;
  const isDefaultSelected = selectedSimulation ? isDefaultSimulation(selectedSimulation) : false;
  const isRecentRunSelected = selectedSimulation ? isRecentRun(selectedSimulation) : false;
  const canDelete = hasSelection && !isDefaultSelected && !isRecentRunSelected;

  // Group simulations by section for rendering
  const defaultSims = simulations.filter(s => isDefaultSimulation(s.id));
  const savedSims = simulations.filter(s => !isDefaultSimulation(s.id) && !isRecentRun(s.id));
  const recentRunSims = simulations.filter(s => isRecentRun(s.id));
  
  return (
    <div className={styles.dashboard}>
      <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
      <div className={styles.header}>
        <img className={styles.logo} src={bajaLogo} alt="Baja Logo" />
        <h1 className={styles.title}>CVT Simulator</h1>
      </div>
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
            {simulations.length === 0 ? (
              <tr className={styles.emptyRow}>
                <td colSpan={3}>No Saved Parameter Sets...</td>
              </tr>
            ) : (
              <>
                {/* Default Configurations Section */}
                {defaultSims.length > 0 && (
                  <>
                    <tr className={styles.sectionHeader}>
                      <td colSpan={3}>Default Configurations</td>
                    </tr>
                    {defaultSims.map((sim) => (
                      <tr
                        key={sim.id}
                        className={`${
                          selectedSimulation === sim.id ? styles.selected : ''
                        } ${styles.defaultRow}`}
                        onClick={() => handleRowClick(sim.id)}
                      >
                        <td>{sim.name}</td>
                        <td>{formatDate(sim.createdAt)}</td>
                        <td>{formatDate(sim.updatedAt)}</td>
                      </tr>
                    ))}
                  </>
                )}

                {/* Saved Simulations Section */}
                {savedSims.length > 0 && (
                  <>
                    <tr className={styles.sectionHeader}>
                      <td colSpan={3}>Saved Parameter Sets</td>
                    </tr>
                    {savedSims.map((sim) => (
                      <tr
                        key={sim.id}
                        className={selectedSimulation === sim.id ? styles.selected : ''}
                        onClick={() => handleRowClick(sim.id)}
                      >
                        <td>{sim.name}</td>
                        <td>{formatDate(sim.createdAt)}</td>
                        <td>{formatDate(sim.updatedAt)}</td>
                      </tr>
                    ))}
                  </>
                )}

                {/* Recent Runs Section */}
                {recentRunSims.length > 0 && (
                  <>
                    <tr className={styles.sectionHeader}>
                      <td colSpan={3}>Recent Runs</td>
                    </tr>
                    {recentRunSims.map((sim) => (
                      <tr
                        key={sim.id}
                        className={`${
                          selectedSimulation === sim.id ? styles.selected : ''
                        } ${styles.recentRunRow}`}
                        onClick={() => handleRowClick(sim.id)}
                      >
                        <td>{sim.name}</td>
                        <td>{formatDate(sim.createdAt)}</td>
                        <td>{formatDate(sim.updatedAt)}</td>
                      </tr>
                    ))}
                  </>
                )}
              </>
            )}
          </tbody>
        </table>
      </div>
      <div className={styles.buttonsContainer}>
        <Button
          text={'Run'}
          icon={Play}
          className={styles.button}
          disabled={!hasSelection}
          onClick={handleRun}
        />
        <Button
          text={'Edit'}
          icon={Edit}
          className={styles.button}
          disabled={!hasSelection}
          onClick={handleEdit}
        />
        <Button
          text={'Delete'}
          icon={TrashCan}
          className={styles.button}
          disabled={!canDelete}
          onClick={handleDelete}
        />
        <Button
          text={'Export'}
          icon={ArrowUpCircle}
          className={styles.button}
          disabled={!hasSelection}
          onClick={handleExport}
        />
        <Button
          text={'Import'}
          icon={ArrowDownCircle}
          className={styles.button}
          onClick={handleImport}
        />
        <Button
          text={'New'}
          icon={Plus}
          className={styles.button}
          onClick={handleNew}
        />
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/json,.json"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
    </div>
  )
}
