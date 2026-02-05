import { useEffect, useState, useRef } from 'react';
import { runSolvers } from '@utils/api';
import type { SolversResponse } from '@utils/api';
import { useParameter } from '@contexts/ParameterContext';
import { mapParametersToApiBody } from '@utils/parameterMapping';
import styles from './SolverResults.module.scss';

export const SolverResults = () => {
    const { parameters } = useParameter();
    const [solverData, setSolverData] = useState<SolversResponse | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const currentRequestRef = useRef(0);

    useEffect(() => {
        const abortController = new AbortController();
        const requestId = ++currentRequestRef.current;

        const fetchSolvers = async () => {
            setIsLoading(true);
            setError(null);
            
            try {
                const apiBody = mapParametersToApiBody(parameters);
                const result = await runSolvers(apiBody, abortController.signal);
                
                // Only update state if this is still the current request
                if (requestId === currentRequestRef.current) {
                    setSolverData(result);
                }
            } catch (err) {
                // Don't show error if request was aborted or superseded
                if (requestId === currentRequestRef.current) {
                    console.error('Failed to fetch solver results:', err);
                    setError('Failed to load solver results');
                }
            } finally {
                if (requestId === currentRequestRef.current) {
                    setIsLoading(false);
                }
            }
        };

        fetchSolvers();

        // Cancel the request when parameters change or component unmounts
        return () => {
            abortController.abort();
        };
    }, [parameters]);

    const convertToRPM = (radPerSec: number | null | undefined): string => {
        if (radPerSec == null) return 'N/A';
        const rpm = (radPerSec * 60) / (2 * Math.PI);
        return `${rpm.toFixed(0)} RPM`;
    };

    if (isLoading) {
        return (
            <div className={styles.solverResults}>
                <h3>CVT Pre-Analysis</h3>
                <div className={styles.loading}>Loading...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={styles.solverResults}>
                <h3>CVT Analysis</h3>
                <div className={styles.error}>{error}</div>
            </div>
        );
    }

    if (!solverData) {
        return null;
    }

    return (
        <div className={styles.solverResults}>
            <h3>CVT Analysis</h3>
            <div className={styles.resultItem}>
                <div className={styles.label}>Engagement Point:</div>
                <div className={styles.value}>
                    {solverData.primary_engagement.success
                        ? convertToRPM(solverData.primary_engagement.value)
                        : 'Not found'}
                </div>
                <div className={styles.description}>
                    {solverData.primary_engagement.description}
                </div>
            </div>
            <div className={styles.resultItem}>
                <div className={styles.label}>Shift Initiation:</div>
                <div className={styles.value}>
                    {solverData.shift_initiation.success
                        ? convertToRPM(solverData.shift_initiation.value)
                        : 'Not found'}
                </div>
                <div className={styles.description}>
                    {solverData.shift_initiation.description}
                </div>
            </div>
        </div>
    );
};
