import type { Graph2DProps } from "@components/graph2D/types";
import type { RunResponse } from "./api";
import { graphConfigs } from "@types";

export function buildGraphs(run: RunResponse): Graph2DProps[] {
    const data = run.data;

    return graphConfigs.map((config) => ({
        xData: data.map(config.xAccessor),
        yData: data.map(config.yAccessor),
        ...config,
    }));
}