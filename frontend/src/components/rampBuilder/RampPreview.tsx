import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption, CallbackDataParams } from 'echarts/types/dist/shared';
import type { components } from '@types';
import { previewRamp, type RampPreviewResponse } from '@utils/api';
import styles from './RampPreview.module.scss';

type PiecewiseRampConfig = components['schemas']['PiecewiseRampConfigModel'];

interface RampPreviewProps {
    config: PiecewiseRampConfig;
}

const LINE_THICKNESS = 4;
const GRID = { left: 60, right: 40, top: 40, bottom: 60 } as const;

export const RampPreview = ({ config }: RampPreviewProps) => {
    const [previewData, setPreviewData] = useState<RampPreviewResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [containerWidth, setContainerWidth] = useState(800);
    const [containerHeight, setContainerHeight] = useState(400);
    const roRef = useRef<ResizeObserver | null>(null);

    // Callback ref: React calls this with the DOM node as soon as it is
    // attached, regardless of which render branch produced it.  This is more
    // reliable than useEffect+useRef because useEffect only runs after the
    // *first* render, which may be a loading/empty branch with no measurable
    // width yet.
    const sentinelRef = useCallback((el: HTMLDivElement | null) => {
        // Clean up any previous observer
        roRef.current?.disconnect();
        roRef.current = null;

        if (!el) return;

        const measure = (width: number) => {
            if (width > 0) setContainerWidth(width);
        };

        const ro = new ResizeObserver(entries => {
            measure(entries[0]?.contentRect.width ?? 0);
        });
        ro.observe(el);
        roRef.current = ro;

        // Read immediately in case ResizeObserver doesn't fire synchronously
        measure(el.getBoundingClientRect().width);
    }, []);

    // Recalculate containerHeight whenever the data or width changes,
    // keeping this side-effect out of useMemo to avoid setState-during-render.
    useEffect(() => {
        if (!previewData) return;

        const plotWidthPx = containerWidth - GRID.left - GRID.right;
        const xMax = Math.max(...previewData.x);
        const yMin = Math.min(...previewData.y);
        const ppm = plotWidthPx / xMax;
        const plotHeightPx = Math.abs(yMin) * ppm;
        setContainerHeight(plotHeightPx + GRID.top + GRID.bottom);
    }, [previewData, containerWidth]);

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
                const data = await previewRamp(config);
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
        PRIMARY: getColor('--primary', '#bb0808'),
        TOOLTIP_BG: getColor('--tooltip-bg', '#2a2a2a'),
    };

    const chartOptions: EChartsOption = useMemo(() => {
        // Greatest X value and lowest Y value in the data, used to set axis limits and scaling
        const xMax = previewData ? Math.max(...previewData.x) : 1;
        const yMin = previewData ? Math.min(...previewData.y) : -1;


        return {
            backgroundColor: COLORS.BACKGROUND,
            textStyle: { color: COLORS.TEXT },
            grid: {
                left: 60,
                right: 40,
                top: 40,
                bottom: 60,
                containLabel: false,
            },
            xAxis: {
                type: 'value',
                name: 'Position (m)',
                nameLocation: 'middle',
                nameGap: 30,
                nameTextStyle: { color: COLORS.TEXT },
                axisLine: { lineStyle: { color: COLORS.GRID } },
                axisTick: { lineStyle: { color: COLORS.GRID } },
                axisLabel: { color: COLORS.TEXT, formatter: (val: number) => val.toFixed(3) },
                splitLine: { lineStyle: { color: COLORS.GRID } },
                min: 0,
                max: xMax,
                scale: false,
            },
            yAxis: {
                type: 'value',
                name: 'Height (m)',
                nameLocation: 'middle',
                nameGap: 50,
                nameTextStyle: { color: COLORS.TEXT },
                axisLine: { lineStyle: { color: COLORS.GRID } },
                axisTick: { lineStyle: { color: COLORS.GRID } },
                axisLabel: { color: COLORS.TEXT, formatter: (val: number) => val.toFixed(3) },
                splitLine: { 
                    show: true,
                    lineStyle: { color: COLORS.GRID }
                },
                min: yMin,
                max: 0,
                scale: false,
            },
        series: [
            {
                type: 'line',
                data: previewData?.x.map((x, i) => [x, previewData.y[i]]) || [],
                smooth: true,
                lineStyle: {
                    color: COLORS.PRIMARY,
                    width: LINE_THICKNESS,
                },
                itemStyle: {
                    color: COLORS.PRIMARY,
                },
                showSymbol: false,
            },
            {
                // Bottom axis (y = yMin, from x=0 to x=xMax)
                type: 'line',
                data: [[-0.005*xMax, yMin], [xMax, yMin]],
                lineStyle: { color: COLORS.PRIMARY, width: LINE_THICKNESS },
                itemStyle: { color: COLORS.PRIMARY },
                showSymbol: false,
                silent: true,
                tooltip: { show: false },
            },
            {
                // Left axis (x = 0, from y=0 to y=yMin)
                type: 'line',
                data: [[0, 0], [0, yMin + 0.005*yMin]],
                lineStyle: { color: COLORS.PRIMARY, width: LINE_THICKNESS },
                itemStyle: { color: COLORS.PRIMARY },
                showSymbol: false,
                silent: true,
                tooltip: { show: false },
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
    }, [previewData, COLORS]);

    if (error) {
        return (
            <div className={styles.previewContainer}>
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
                <div className={styles.loading}>Loading preview...</div>
            </div>
        );
    }

    if (!previewData) {
        return (
            <div className={styles.previewContainer}>
                <div className={styles.empty}>Add segments to see preview</div>
            </div>
        );
    }

    const renderContent = () => {
        if (error) {
            return (
                <div className={styles.error}>
                    <p>Error generating preview:</p>
                    <p>{error}</p>
                </div>
            );
        }
        if (isLoading) {
            return <div className={styles.loading}>Loading preview...</div>;
        }
        if (!previewData) {
            return <div className={styles.empty}>Add segments to see preview</div>;
        }
        return (
            <div className={styles.chartContainer}>
                <ReactECharts
                    option={chartOptions}
                    style={{ height: `${containerHeight}px`, width: '100%' }}
                />
            </div>
        );
    };

    // sentinelRef is placed on a zero-height div that is always rendered,
    // so width measurement works in every state (loading, empty, error, data).
    return (
        <div className={styles.previewContainer}>
            <div ref={sentinelRef} style={{ width: '100%', height: 0 }} />
            {renderContent()}
        </div>
    );
};
