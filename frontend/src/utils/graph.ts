import type { Graph2DProps } from "@components/graph2D/graph2D";
import type { RunResponse } from "./api";
import { graphConfigs } from "@types";

// Cache for built graphs to maintain referential stability
let cachedGraphs: Graph2DProps[] | null = null;
let cachedData: RunResponse['data'] | null = null;

export function buildGraphs(run: RunResponse): Graph2DProps[] {
    const data = run.data;

    // Return cached graphs if data hasn't changed (referential equality)
    if (cachedGraphs && cachedData === data) {
        return cachedGraphs;
    }

    // Build new graphs
    const graphs = graphConfigs.map((config) => ({
        xData: data.map(config.xAccessor),
        yData: data.map((point) => config.yAccessor.map((accessor) => accessor(point))),
        ...config,
    }));

    // Update cache
    cachedData = data;
    cachedGraphs = graphs;

    return graphs;
}