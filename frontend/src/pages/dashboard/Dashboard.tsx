import styles from './Dashboard.module.scss';
import bajaLogo from '@assets/baja_logo.png';
import { Button } from '@components/button/Button';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { SimulationsTable } from '@components/simulationsTable/SimulationsTable';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulations } from '@hooks/useSimulations';
import PlayOutline from '@assets/icons/play_outline.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import TrashCan from '@assets/icons/trash_can.svg?react';
import Plus from '@assets/icons/plus.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';

export const Dashboard = () => {
  const { isLoading, loadingMessage } = useLoading();
  const {
    groupedSimulations,
    selectedId,
    fileInputRef,
    hasSelection,
    canDelete,
    selectSimulation,
    handleRun,
    handleEdit,
    handleDelete,
    handleExport,
    handleImport,
    handleNew,
    handleFileChange,
  } = useSimulations();

  return (
    <div className={styles.dashboard}>
      <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
      <div className={styles.header}>
        <img className={styles.logo} src={bajaLogo} alt="Baja Logo" />
        <h1 className={styles.title}>CVT Simulator</h1>
      </div>
      <SimulationsTable
        groupedSimulations={groupedSimulations}
        selectedId={selectedId}
        onSelect={selectSimulation}
      />
      <div className={styles.buttonsContainer}>
        <Button
          text={'Run'}
          icon={PlayOutline}
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
  );
};
