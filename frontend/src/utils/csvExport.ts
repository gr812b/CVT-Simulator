import type { ReportTable } from '@api/client';

function escapeCsv(value: string | number | null): string {
  const text = value === null ? '' : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Export exactly the CINDER report-table columns; no legacy nested-output flattening. */
export function downloadReportTableCsv(table: ReportTable, filePrefix = 'cinder_simulation_report'): void {
  const header = table.columns.map((column) => `${column.key} [${column.canonicalUnit}]`);
  const rows = Array.from({ length: table.rowCount }, (_, row) => table.columns.map((column) => column.values[row] ?? null));
  const csv = [header, ...rows].map((row) => row.map(escapeCsv).join(',')).join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${filePrefix}_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
