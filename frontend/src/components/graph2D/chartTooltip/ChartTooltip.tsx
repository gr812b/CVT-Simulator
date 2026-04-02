import { forwardRef } from 'react';
import styles from './ChartTooltip.module.scss';

export interface TooltipLine {
  color: string;
  label: string;
  value: string;
}

interface ChartTooltipProps {
  className?: string;
}

/**
 * Styled tooltip shell. Positioning and content are controlled externally —
 * either via ref (imperative/DOM path in CursorOverlay) or by ECharts directly.
 */
export const ChartTooltip = forwardRef<HTMLDivElement, ChartTooltipProps>(
  ({ className }, ref) => (
    <div ref={ref} className={`${styles.chartTooltip}${className ? ` ${className}` : ''}`} />
  )
);

ChartTooltip.displayName = 'ChartTooltip';

/**
 * Builds the inner HTML string for imperative tooltip updates (e.g. CursorOverlay).
 * Matches the structure rendered by the ECharts formatter in chartOptions.ts.
 */
export function buildTooltipHTML(headerText: string, lines: TooltipLine[]): string {
  const lineHtml = lines
    .map(
      ({ color, label, value }) =>
        `<div style="display:flex;align-items:center;gap:6px;">
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0;"></span>
          <span>${label}: ${value}</span>
        </div>`
    )
    .join('');

  return `<div>${headerText}</div>${lineHtml}`;
}