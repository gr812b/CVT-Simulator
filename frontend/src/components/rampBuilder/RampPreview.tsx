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

    const sentinelRef = useCallback((el: HTMLDivElement | null) => {
        roRef.current?.disconnect();
        roRef.current = null;

        if (!el) return;

        const measure = (width: number, height: number) => {
            if (width > 0) setContainerWidth(width);
            if (height > 0) setContainerHeight(height);
        };

        const ro = new ResizeObserver(entries => {
            const { width, height } = entries[0]?.contentRect ?? {};
            measure(width ?? 0, height ?? 0);
        });
        ro.observe(el);
        roRef.current = ro;

        const { width, height } = el.getBoundingClientRect();
        measure(width, height);
    }, []);

    // Compute axis limits that preserve the data's aspect ratio within the full container.
    // Supports ramps with positive or negative heights by deriving bounds from data.
    const { axisXMin, axisXMax, axisYMin, axisYMax } = useMemo(() => {
        if (!previewData) {
            return { axisXMin: 0, axisXMax: 1, axisYMin: -1, axisYMax: 0 };
        }

        const dataXMin = Math.min(...previewData.x);
        const dataXMax = Math.max(...previewData.x);
        const dataYMinRaw = Math.min(...previewData.y);
        const dataYMaxRaw = Math.max(...previewData.y);

        // Keep zero visible for easier interpretation of ramp offsets.
        const dataYMin = Math.min(dataYMinRaw, 0);
        const dataYMax = Math.max(dataYMaxRaw, 0);

        const plotWidth = Math.max(1, containerWidth - GRID.left - GRID.right);
        const plotHeight = Math.max(1, containerHeight - GRID.top - GRID.bottom);

        const xSpan = Math.max(1e-9, dataXMax - dataXMin);
        const ySpan = Math.max(1e-9, dataYMax - dataYMin);

        // Pixels per meter if each dimension were to fill the plot area exactly.
        const ppmX = plotWidth / xSpan;
        const ppmY = plotHeight / ySpan;

        // Use the tighter scale so the data fully fits, then expand the other axis.
        const ppm = Math.min(ppmX, ppmY);

        return {
            axisXMin: dataXMin,
            axisXMax: dataXMin + (plotWidth / ppm),
            axisYMin: dataYMin,
            axisYMax: dataYMin + (plotHeight / ppm),
        };
    }, [previewData, containerWidth, containerHeight]);

    const configString = useMemo(() => JSON.stringify(config), [config]);

    useEffect(() => {
        if (!config || !config.segments || config.segments.length === 0) {
            setPreviewData(null);
            return;
        }

        const timeoutId = setTimeout(async () => {
            setIsLoading(true);
            setError(null);

            try {
                const data = await previewRamp(config);
                setPreviewData(data);
            } catch (err) {
                alert('Failed to generate preview: ' + (err instanceof Error ? err.message : 'Unknown error'));
                setError(err instanceof Error ? err.message : 'Failed to generate preview');
                setPreviewData(null);
            } finally {
                setIsLoading(false);
            }
        }, 500);

        return () => clearTimeout(timeoutId);
    }, [configString, config]);

    const COLORS = useMemo(() => {
        const getColor = (property: string, fallback: string): string => {
            if (typeof window !== 'undefined') {
                const value = getComputedStyle(document.documentElement).getPropertyValue(property).trim();
                return value || fallback;
            }
            return fallback;
        };

        return {
            BACKGROUND: getColor('--background', '#222222'),
            TEXT: getColor('--text-color', '#ffffff'),
            GRID: getColor('--grid-color', '#404040'),
            PRIMARY: getColor('--primary', '#bb0808'),
            TOOLTIP_BG: getColor('--tooltip-bg', '#2a2a2a'),
        };
    }, []);

    const chartOptions: EChartsOption = useMemo(() => {
        return {
            backgroundColor: COLORS.BACKGROUND,
            textStyle: { color: COLORS.TEXT },
            grid: {
                left: GRID.left,
                right: GRID.right,
                top: GRID.top,
                bottom: GRID.bottom,
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
                axisLabel: { color: COLORS.TEXT, formatter: (val: number) => Math.round(val * 10000) / 10000 },
                splitLine: { lineStyle: { color: COLORS.GRID } },
                min: axisXMin,
                max: axisXMax,
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
                axisLabel: { color: COLORS.TEXT, formatter: (val: number) => Math.round(val * 10000) / 10000 },
                splitLine: {
                    show: true,
                    lineStyle: { color: COLORS.GRID }
                },
                min: axisYMin,
                max: axisYMax,
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
    }, [previewData, axisXMin, axisXMax, axisYMin, axisYMax, COLORS]);

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
            <ReactECharts
                option={chartOptions}
                style={{ height: '100%', width: '100%' }}
            />
        );
    };

    return (
        <div ref={sentinelRef} className={styles.previewContainer}>
            {renderContent()}
        </div>
    );
};