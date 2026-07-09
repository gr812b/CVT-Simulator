import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './Dashboard.module.scss';
import { Button } from '@components/button/Button';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { SimulationsTable } from '@components/simulationsTable/SimulationsTable';
import { useLoading } from '@contexts/LoadingContext';
import { useRunSimulation } from '@hooks/useRunSimulation';
import {
  buildLibraryRunSelection,
  getDefaultRunSetup,
  type DefaultRunSetup,
} from '@api/client';
import PlayOutline from '@assets/icons/play_outline.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import Home from '@assets/icons/home.svg?react';

/**
 * Product dashboard: pick a released vehicle baseline and run it through the
 * database-backed library endpoint. The old raw CINDER preset workflow is
 * intentionally not part of the normal UI anymore.
 */
export const Dashboard = () => {
  const navigate = useNavigate();
  const { isLoading, loadingMessage } = useLoading();
  const { runLibrarySetup } = useRunSimulation();
  const [setup, setSetup] = useState<DefaultRunSetup | null>(null);
  const [selectedVehicleAssemblyId, setSelectedVehicleAssemblyId] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [isLoadingSetup, setIsLoadingSetup] = useState(true);

  const selectedVehicleAssembly = useMemo(
    () => setup?.vehicleAssemblies.find((assembly) => assembly.id === selectedVehicleAssemblyId) ?? setup?.selectedVehicleAssembly ?? null,
    [selectedVehicleAssemblyId, setup],
  );

  const refreshSetup = useCallback(async () => {
    setIsLoadingSetup(true);
    setListError(null);
    try {
      const next = await getDefaultRunSetup();
      setSetup(next);
      setSelectedVehicleAssemblyId((current) => current && next.vehicleAssemblies.some((assembly) => assembly.id === current)
        ? current
        : next.selectedVehicleAssembly.id);
    } catch (error) {
      setListError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsLoadingSetup(false);
    }
  }, []);

  useEffect(() => { void refreshSetup(); }, [refreshSetup]);

  const handleRun = useCallback(async () => {
    if (setup === null || selectedVehicleAssembly === null) return;
    const selection = buildLibraryRunSelection(setup, { vehicleAssemblyId: selectedVehicleAssembly.id });
    await runLibrarySetup(selection);
  }, [runLibrarySetup, selectedVehicleAssembly, setup]);

  return (
    <div className={styles.dashboard}>
      <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
      <div className={styles.topBar}>
        <Button text="Home" icon={Home} className={styles.navButton} onClick={() => navigate('/')} />
        <div className={styles.headerCopy}>
          <h1>CVT Run Library</h1>
          <p>Run the seeded Baja baseline with the current default tune, load case, and execution preset.</p>
        </div>
      </div>
      <SimulationsTable
        vehicleAssemblies={setup?.vehicleAssemblies ?? []}
        selectedId={selectedVehicleAssembly?.id ?? null}
        onSelect={setSelectedVehicleAssemblyId}
        isLoading={isLoadingSetup}
        error={listError}
      />
      <div className={styles.buttonsContainer}>
        <Button text="Run" icon={PlayOutline} className={styles.button} disabled={selectedVehicleAssembly === null} onClick={() => void handleRun()} />
        <Button text="Tune / Load Setup" icon={Edit} className={styles.button} onClick={() => navigate('/input')} />
      </div>
    </div>
  );
};
