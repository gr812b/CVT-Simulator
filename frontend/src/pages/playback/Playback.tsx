import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import { Graph2D } from '@components/graph2D/graph2D';
import { Scene3DViewer } from '@components/scene3DViewer/Scene3DViewer';
import { Playbar } from '@components/playbar/Playbar';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationRun } from '@contexts/SimulationRunContext';
import { ReportReplayController } from '@utils/reportReplay';
import { downloadReportTableCsv } from '@utils/csvExport';
import { reportAxisTimes } from '@utils/reportTable';
import { buildReportGraphs } from './reportGraphs';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import Download from '@assets/icons/arrow_down_circle.svg?react';
import PlayOutline from '@assets/icons/play_outline.svg?react';

const PlaybackContent = ({ run }: { run: NonNullable<ReturnType<typeof useSimulationRun>['completedRun']> }) => {
  const navigate = useNavigate(); const table = run.result.reportTable; const timeValues = useMemo(() => reportAxisTimes(table), [table]); const replayController = useMemo(() => new ReportReplayController(timeValues), [timeValues]); const replayRef = useRef(replayController); const categories = useMemo(() => buildReportGraphs(table), [table]);
  useEffect(() => { replayRef.current = replayController; return () => replayController.dispose(); }, [replayController]);
  const pauseNavigate = useCallback((path: string) => { replayRef.current.pause(); navigate(path); }, [navigate]);
  return <div className={styles.playback}><div className={styles.buttonsContainer}><div className={styles.leftButtons}><Button text="Home" icon={Home} className={styles.navigateButton} onClick={() => pauseNavigate('/')} /><Button text="Tune Setup" icon={Edit} className={styles.navigateButton} onClick={() => pauseNavigate('/input')} /></div><div className={styles.rightButtons}><Button text="Download CSV" icon={Download} className={styles.navigateButton} onClick={() => downloadReportTableCsv(table, 'playback_data')} /></div></div><div className={styles.displayGrid}><div className={styles.sceneContainer}><Scene3DViewer replayController={replayController} table={table} document={run.inputDocumentSnapshot} /></div>{categories.map((category) => <div key={category.title} className={styles.graphCategory}><h2 className={styles.categoryTitle}>{category.title}</h2><div className={styles.categoryGraphs}>{category.graphs.map((graph) => <Graph2D key={graph.config.title} {...graph} replayController={replayController} />)}</div></div>)}</div><div className={styles.playbarContainer}><Playbar replayController={replayController} times={timeValues} /></div></div>;
};
export const Playback = () => {
  const navigate = useNavigate(); const { completedRun, restoreCompletedRun, rerunCompletedRun } = useSimulationRun(); const { isLoading, loadingMessage, setLoading } = useLoading(); const [restoreError, setRestoreError] = useState<string | null>(null);
  useEffect(() => { if (completedRun !== null) return; setLoading(true, 'Restoring completed simulation...'); void restoreCompletedRun().then((run) => { if (run === null) setRestoreError('No completed database-backed run is available in this browser session.'); }).catch((error) => setRestoreError(error instanceof Error ? error.message : String(error))).finally(() => setLoading(false)); }, [completedRun, restoreCompletedRun, setLoading]);
  const handleRegenerate = useCallback(async () => { setLoading(true, 'Regenerating full result from frozen input...'); try { await rerunCompletedRun(); setRestoreError(null); } catch (error) { setRestoreError(error instanceof Error ? error.message : String(error)); } finally { setLoading(false); } }, [rerunCompletedRun, setLoading]);
  if (completedRun === null) return <div className={styles.playback}><LoadingOverlay isVisible={isLoading} message={loadingMessage} /><div className={styles.emptyState}><h1>Playback unavailable</h1><p>{restoreError ?? 'Looking for a completed simulation run...'}</p><button type="button" onClick={() => navigate('/input')}>Back to run setup</button><button type="button" onClick={() => void handleRegenerate()}><PlayOutline /> Regenerate result</button></div></div>;
  return <PlaybackContent run={completedRun} />;
};
