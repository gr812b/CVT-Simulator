import { useMemo, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import cx from 'classnames';
import styles from './Graph2D.module.scss';
import type { Graph2DProps } from './types';
import { validateData } from './validation';
import { createChartOptions, CHART_COLORS } from './chartOptions';

export function Graph2D({
  xData,
  yData,
  config,
  chartOptions = {},
  className = '',
}: Graph2DProps) {
  // Validate data and generate warnings/errors
  const validation = useMemo(() => validateData(xData, yData), [xData, yData]);
  
  // Generate complete ECharts options
  const echartsOptions = useMemo(() => {
    if (!validation.isValid) {
      // Return minimal options for error state
      return {
        title: {
          text: 'No Data',
          left: 'center',
          textStyle: { color: CHART_COLORS.ERROR },
        },
      };
    }

    return createChartOptions(xData, yData, config, chartOptions);
  }, [xData, yData, config, chartOptions, validation]);

  // Log warnings to console (can be disabled in production)
  useEffect(() => {
    if (validation.warnings.length > 0) {
      console.warn('Graph2D warnings:', validation.warnings);
    }
  }, [validation.warnings]);
  
  const chartHeight = config.height || 400;
  const chartWidth = config.width || '100%';
  
  // If data is invalid, show error state
  if (!validation.isValid) {
    return (
      <div className={cx(styles.graph2dError, className)} style={{ height: chartHeight }}>
        <div className={styles.errorMessage}>
          <h3>Invalid Data</h3>
          <ul>
            {validation.errors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  }
  
  return (
    <div className={cx(styles.graph2d, className)}>
      <div className={styles.chartContainer}>
        <ReactECharts
          option={echartsOptions}
          style={{ width: chartWidth, height: chartHeight }}
          notMerge
          lazyUpdate
        />
      </div>
    </div>
  );
}
