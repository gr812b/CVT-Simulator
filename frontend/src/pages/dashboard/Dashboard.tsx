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
  type SavedSimulation 
} from '@utils/localStorage';
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
    const loaded = getAllSimulations();
    setSimulations(loaded);
    // Clear selection if the selected parameter set no longer exists
    if (selectedSimulation && !loaded.find(s => s.id === selectedSimulation)) {
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
    
    // Navigate to input page
    navigate('/input');
  };

  const handleDelete = () => {
    if (!selectedSimulation) return;

    const simulation = simulations.find(s => s.id === selectedSimulation);
    if (!simulation) return;

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
              simulations.map((sim) => (
                <tr
                  key={sim.id}
                  className={selectedSimulation === sim.id ? styles.selected : ''}
                  onClick={() => handleRowClick(sim.id)}
                >
                  <td>{sim.name}</td>
                  <td>{formatDate(sim.createdAt)}</td>
                  <td>{formatDate(sim.updatedAt)}</td>
                </tr>
              ))
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
          disabled={!hasSelection}
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
          onClick={() => navigate('/input')}
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
