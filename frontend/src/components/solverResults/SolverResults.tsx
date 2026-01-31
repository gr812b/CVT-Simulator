import { useEffect, useState } from 'react';
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

    useEffect(() => {
        const fetchSolvers = async () => {
            setIsLoading(true);
            setError(null);
            
            try {
                const apiBody = mapParametersToApiBody(parameters);
                const result = await runSolvers(apiBody);
                setSolverData(result);
            } catch (err) {
                console.error('Failed to fetch solver results:', err);
                setError('Failed to load solver results');
            } finally {
                setIsLoading(false);
            }
        };

        fetchSolvers();
    }, [parameters]);

    const convertToRPM = (radPerSec: number | null | undefined): string => {
        if (radPerSec == null) return 'N/A';
        const rpm = (radPerSec * 60) / (2 * Math.PI);
        return `${rpm.toFixed(0)} RPM`;
    };

    if (isLoading) {
        return (
            <div className={styles.solverResults}>
                <h3>CVT Analysis</h3>
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
