type FlatRow = Record<string, unknown>;

function isObjectRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function flattenValue(value: unknown, path: string, output: FlatRow): void {
    if (Array.isArray(value)) {
        if (value.length === 0) {
            output[path] = '';
            return;
        }

        value.forEach((item, index) => {
            const nextPath = path ? `${path}[${index}]` : `[${index}]`;
            flattenValue(item, nextPath, output);
        });
        return;
    }

    if (isObjectRecord(value)) {
        const entries = Object.entries(value);

        if (!entries.length) {
            output[path] = '';
            return;
        }

        entries.forEach(([key, nestedValue]) => {
            const nextPath = path ? `${path}.${key}` : key;
            flattenValue(nestedValue, nextPath, output);
        });
        return;
    }

    output[path] = value ?? '';
}

function flattenRows(rows: ReadonlyArray<unknown>): FlatRow[] {
    return rows.map((row) => {
        const flattened: FlatRow = {};
        flattenValue(row, '', flattened);
        return flattened;
    });
}

function escapeCsvField(value: unknown): string {
    const str = value == null ? '' : String(value);
    return /[",\n\r]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
}

function toCsv(flattenedRows: ReadonlyArray<FlatRow>): string {
    const headers = Array.from(
        flattenedRows.reduce((keys, row) => {
            Object.keys(row).forEach((key) => keys.add(key));
            return keys;
        }, new Set<string>())
    );

    const csvRows = [
        headers.join(','),
        ...flattenedRows.map((row) => headers.map((header) => escapeCsvField(row[header])).join(',')),
    ];

    return csvRows.join('\r\n');
}

export function downloadFlattenedCsv(rows: ReadonlyArray<unknown>, filePrefix = 'playback_data'): void {
    const flattenedRows = flattenRows(rows);
    const csv = toCsv(flattenedRows);

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

    link.href = url;
    link.download = `${filePrefix}_${timestamp}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
}
