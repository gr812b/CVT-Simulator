import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { previewRamp, type RampEditorValue } from '@utils/rampEditor';
import styles from './RampPreview.module.scss';

export const RampPreview = ({ config }: { config: RampEditorValue }) => {
  const data = useMemo(() => previewRamp(config), [config]);
  const option = useMemo<EChartsOption>(() => ({
    backgroundColor: 'transparent',
    grid: { left: 60, right: 30, top: 30, bottom: 50 },
    xAxis: { type: 'value', name: 'Position (m)', nameLocation: 'middle', nameGap: 30 },
    yAxis: { type: 'value', name: 'Height (m)', nameLocation: 'middle', nameGap: 45 },
    tooltip: { trigger: 'axis' },
    series: [{ type: 'line', data: data.x.map((x, index) => [x, data.y[index]]), smooth: true, showSymbol: false, lineStyle: { width: 4 } }],
  }), [data]);
  return <div className={styles.previewContainer}><ReactECharts option={option} style={{ height: '100%', width: '100%' }} /></div>;
};
