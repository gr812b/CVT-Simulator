import { useEffect, useState, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption, CallbackDataParams } from 'echarts/types/dist/shared';
import type { components } from '@types';
import styles from './RampPreview.module.scss';

type PiecewiseRampConfig = components['schemas']['PiecewiseRampConfigModel'];

interface RampPreviewProps {
    config: PiecewiseRampConfig;
}

interface PreviewData {
    x: number[];
    y: number[];
    slopes: number[];
    x_min: number;
    x_max: number;
}

export const RampPreview = ({ config }: RampPreviewProps) => {
    const [previewData, setPreviewData] = useState<PreviewData | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const configString = useMemo(() => JSON.stringify(config), [config]);

    useEffect(() => {
        console.log('RampPreview config:', config);
        
        if (!config || !config.segments || config.segments.length === 0) {
            console.log('No segments, skipping preview');
            setPreviewData(null);
            return;
        }

        console.log('Fetching preview with', config.segments.length, 'segments');
        
        const timeoutId = setTimeout(async () => {
            setIsLoading(true);
            setError(null);

            try {
                const response = await fetch('http://localhost:8000/ramp/preview', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(config),
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Failed to generate preview');
                }

                const data = await response.json();
                console.log('Preview data received:', data);
                setPreviewData(data);
            } catch (err) {
                console.error('Preview error:', err);
                setError(err instanceof Error ? err.message : 'Failed to generate preview');
                setPreviewData(null);
            } finally {
                setIsLoading(false);
            }
        }, 500); // Debounce for 500ms

        return () => clearTimeout(timeoutId);
    }, [configString, config]);

    // Get colors from CSS variables (matching Graph2D styling)
    const getColor = (property: string, fallback: string): string => {
        if (typeof window !== 'undefined') {
            const value = getComputedStyle(document.documentElement).getPropertyValue(property).trim();
            return value || fallback;
        }
        return fallback;
    };

    const COLORS = {
        BACKGROUND: getColor('--secondary', '#222222'),
        TEXT: getColor('--text-color', '#ffffff'),
        GRID: getColor('--grid-color', '#404040'),
        ACCENT: getColor('--accent', '#bb0808'),
        TOOLTIP_BG: getColor('--tooltip-bg', '#2a2a2a'),
    };

    const chartOptions: EChartsOption = {
        backgroundColor: COLORS.BACKGROUND,
        textStyle: { color: COLORS.TEXT },
        grid: {
            left: 60,
            right: 40,
            top: 40,
            bottom: 60,
        },
        xAxis: {
            type: 'value',
            name: 'Position (m)',
            nameLocation: 'middle',
            nameGap: 30,
            nameTextStyle: { color: COLORS.TEXT },
            axisLine: { lineStyle: { color: COLORS.GRID } },
            axisTick: { lineStyle: { color: COLORS.GRID } },
            axisLabel: { color: COLORS.TEXT },
            splitLine: { lineStyle: { color: COLORS.GRID } },
        },
        yAxis: {
            type: 'value',
            name: 'Height (m)',
            nameLocation: 'middle',
            nameGap: 50,
            nameTextStyle: { color: COLORS.TEXT },
            axisLine: { lineStyle: { color: COLORS.GRID } },
            axisTick: { lineStyle: { color: COLORS.GRID } },
            axisLabel: { color: COLORS.TEXT },
            splitLine: { 
                show: true,
                lineStyle: { color: COLORS.GRID }
            },
        },
        series: [
            {
                type: 'line',
                data: previewData?.x.map((x, i) => [x, previewData.y[i]]) || [],
                smooth: true,
                lineStyle: {
                    color: COLORS.ACCENT,
                    width: 2,
                },
                itemStyle: {
                    color: COLORS.ACCENT,
                },
                showSymbol: false,
            },
        ],
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: COLORS.TOOLTIP_BG,
            borderColor: COLORS.GRID,
            textStyle: { color: COLORS.TEXT },
            formatter: (params: CallbackDataParams | CallbackDataParams[]) => {
                const paramArray = Array.isArray(params) ? params : [params];
                if (paramArray.length === 0) return '';
                
                const point = paramArray[0];
                const dataValues = Array.isArray(point.value) ? point.value : [];
                if (dataValues.length < 2) return '';
                
                const xVal = dataValues[0];
                const yVal = dataValues[1];
                
                if (typeof xVal !== 'number' || typeof yVal !== 'number') return '';
                
                const x = xVal.toFixed(4);
                const y = yVal.toFixed(4);
                const slopeIdx = previewData?.x.findIndex(px => Math.abs(px - xVal) < 0.0001);
                const slope = slopeIdx !== undefined && slopeIdx >= 0 && previewData?.slopes[slopeIdx] 
                    ? previewData.slopes[slopeIdx].toFixed(4) 
                    : 'N/A';
                return `Position: ${x} m<br/>Height: ${y} m<br/>Slope: ${slope}`;
            },
        },
    };

    if (error) {
        return (
            <div className={styles.previewContainer}>
                <h4>Ramp Preview</h4>
                <div className={styles.error}>
                    <p>Error generating preview:</p>
                    <p>{error}</p>
                </div>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className={styles.previewContainer}>
                <h4>Ramp Preview</h4>
                <div className={styles.loading}>Loading preview...</div>
            </div>
        );
    }

    if (!previewData) {
        return (
            <div className={styles.previewContainer}>
                <h4>Ramp Preview</h4>
                <div className={styles.empty}>Add segments to see preview</div>
            </div>
        );
    }

    return (
        <div className={styles.previewContainer}>
            <h4>Ramp Preview</h4>
            <div className={styles.chartContainer}>
                <ReactECharts option={chartOptions} style={{ height: '300px', width: '100%' }} />
            </div>
        </div>
    );
};
