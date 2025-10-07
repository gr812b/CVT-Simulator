import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Page } from '@components/graph2D/page';
import { useSimulation } from '@hooks/useSimulation';
import { extractAllGraphData } from '@utils/simulationDataExtractors';

export const Playback = () => {
    const navigate = useNavigate();
    const { simulationResult, isSimulationReady } = useSimulation();

    // Redirect to input page if no simulation data is available
    useEffect(() => {
        if (!isSimulationReady) {
            console.warn('No simulation data available. Redirecting to input page.');
            navigate('/input');
        }
    }, [isSimulationReady, navigate]);

    // Don't render anything if no simulation data
    if (!isSimulationReady || !simulationResult) {
        return null;
    }

    // Extract data for graphing
    const graphDataSets = extractAllGraphData(simulationResult);
    
    // Log some useful information
    console.log('Simulation Result:', simulationResult);
    console.log('Number of data points:', simulationResult.data.length);
    console.log('Graph datasets:', graphDataSets);
    
    // Get simulation summary statistics
    const totalTime = simulationResult.data[simulationResult.data.length - 1]?.time || 0;
    const finalVelocity = simulationResult.data[simulationResult.data.length - 1]?.state.car_velocity || 0;
    const finalPosition = simulationResult.data[simulationResult.data.length - 1]?.state.car_position || 0;

    return (
        <div>
            <h1>Simulation Results</h1>
            
            {/* Summary Statistics */}
            <div style={{ 
                background: '#f3f4f6', 
                padding: '1rem', 
                margin: '1rem 0', 
                borderRadius: '8px' 
            }}>
                <h3>Summary</h3>
                <p><strong>Total Simulation Time:</strong> {totalTime.toFixed(2)} seconds</p>
                <p><strong>Final Velocity:</strong> {finalVelocity.toFixed(2)} m/s</p>
                <p><strong>Final Position:</strong> {finalPosition.toFixed(2)} m</p>
                <p><strong>Data Points:</strong> {simulationResult.data.length}</p>
            </div>

            {/* Available Datasets for Graphing */}
            <div style={{ 
                background: '#e5e7eb', 
                padding: '1rem', 
                margin: '1rem 0', 
                borderRadius: '8px' 
            }}>
                <h3>Available Graph Datasets</h3>
                <ul>
                    {graphDataSets.map((dataset, index) => (
                        <li key={index}>
                            <strong>{dataset.label}</strong> - {dataset.data.length} points
                        </li>
                    ))}
                </ul>
                <p><em>You can pass these datasets to your graph components!</em></p>
            </div>

            {/* Your existing graph component - you can now pass simulation data to it */}
            <Page />
            
            {/* Example: Raw data preview (you can remove this) */}
            <details style={{ marginTop: '2rem' }}>
                <summary>Raw Data Preview (First 5 points)</summary>
                <pre style={{ 
                    background: '#1f2937', 
                    color: '#f9fafb', 
                    padding: '1rem', 
                    borderRadius: '4px', 
                    overflow: 'auto' 
                }}>
                    {JSON.stringify(simulationResult.data.slice(0, 5), null, 2)}
                </pre>
            </details>
        </div>
    );
};