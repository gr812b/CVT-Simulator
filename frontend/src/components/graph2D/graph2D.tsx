import { useMemo } from "react";
import ReactECharts from "echarts-for-react";

type Props = {
  /** The CSV content as a string (must include header row with 'time' and 'speed') */
  csvText: string;
  /** Optional title shown above the chart */
  title?: string;
  /** Chart height (px). Default 360 */
  height?: number;
};

/** Minimal CSV parser for simple, comma-separated files (no quoted commas).
 * For full CSV features, swap this with PapaParse or d3-dsv easily.
 */
function parseCsvSimple(csv: string): string[][] {
  return csv
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => line.split(",").map((c) => c.trim()));
}

function isParsableDate(v: string): boolean {
  const t = Date.parse(v);
  return Number.isFinite(t);
}
function isNumeric(v: string): boolean {
  return v !== "" && Number.isFinite(Number(v));
}

export function Graph2D({ csvText, title, height = 360 }: Props) {
  const { source, xType } = useMemo(() => {
    const rows = parseCsvSimple(csvText);
    if (rows.length < 2) return { source: [], xType: "category" as const };

    // header lookup (case-insensitive)
    const header = rows[0].map((h) => h.toLowerCase());
    const timeIdx = header.indexOf("time");
    const speedIdx = header.indexOf("car_velocity");
    if (timeIdx === -1 || speedIdx === -1) {
      console.warn("CSV must include 'time' and 'car_velocity' columns in the header.");
      return { source: [], xType: "category" as const };
    }

    const body = rows.slice(1);
    const rawPairs = body
      .map((r) => [r[timeIdx], r[speedIdx]] as [string, string])
      .filter(([t, s]) => t != null && s != null && t !== "" && s !== "");

    // Decide x-axis type
    const dateLikeCount = rawPairs.reduce((acc, [t]) => acc + (isParsableDate(t) ? 1 : 0), 0);
    const numericCount   = rawPairs.reduce((acc, [t]) => acc + (isNumeric(t) ? 1 : 0), 0);

    let xType: "time" | "value" | "category" = "category";
    if (dateLikeCount >= Math.max(1, Math.floor(rawPairs.length * 0.8))) {
      xType = "time";
    } else if (numericCount === rawPairs.length) {
      xType = "value";
    } else {
      xType = "category";
    }

    // ECharts dataset source: include header row for named encodings
    // Keep time column as-is; ECharts parses dates when xAxis.type === 'time'
    const source: (string | number)[][] = [["time", "car_velocity"]];
    for (const [tRaw, sRaw] of rawPairs) {
      const s = Number(sRaw);
      if (!Number.isFinite(s)) continue;

      if (xType === "value") {
        // numeric x
        const x = Number(tRaw);
        if (Number.isFinite(x)) source.push([x, s]);
      } else {
        // time or category — keep as string
        source.push([tRaw, s]);
      }
    }

    return { source, xType };
  }, [csvText]);

  const option = useMemo(() => {
    return {
      title: title ? { text: title, left: "center" } : undefined,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
      },
      toolbox: {
        feature: {
          dataZoom: { yAxisIndex: "none" },
          restore: {},
          saveAsImage: {},
        },
        right: 12,
      },
      dataset: { source },
      grid: { left: 48, right: 20, top: title ? 48 : 18, bottom: 48 },
      xAxis: {
        type: (xType as "time" | "value" | "category") ?? "category",
        name: xType === "value" ? "Time" : undefined,
        boundaryGap: xType === "category", // keep gaps for category; others are continuous
        axisLabel: { hideOverlap: true },
      },
      yAxis: {
        type: "value",
        name: "Speed",
        axisLabel: { hideOverlap: true },
        splitLine: { show: true },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: 0 },
        { type: "slider", xAxisIndex: 0 },
      ],
      series: [
        {
          type: "line",
          name: "Car Velocity",
          smooth: true,
          showSymbol: false,
          // map columns by name via 'encode'
          encode: { x: "time", y: "car_velocity", tooltip: ["time", "car_velocity"] },
        },
      ],
    };
  }, [source, title, xType]);

  return (
    <ReactECharts
      option={option}
      style={{ width: "100%", height }}
      notMerge
      lazyUpdate
    />
  );
}
