import type { Graph2DProps } from "@components/graph2D/graph2D";
import type { RunResponse } from "./api";
import { graphCategories } from "@types";

// Graph data without runtime dependencies like replayController
export type GraphData = Omit<Graph2DProps, 'replayController'>;

export type CategorizedGraphData = {
    title: string;
    graphs: GraphData[];
};

// Cache for built graphs to maintain referential stability
let cachedCategorizedGraphs: CategorizedGraphData[] | null = null;
let cachedData: RunResponse['data'] | null = null;

export function buildCategorizedGraphs(run: RunResponse): CategorizedGraphData[] {
    const data = run.data;

    // Return cached graphs if data hasn't changed (referential equality)
    if (cachedCategorizedGraphs && cachedData === data) {
        return cachedCategorizedGraphs;
    }

    // Build categorized graphs
    const categorizedGraphs = graphCategories.map((category) => ({
        title: category.title,
        graphs: category.graphs.map((config) => ({
            xData: data.map(config.xAccessor),
            yData: data.map((point) => config.yAccessor.map((accessor) => accessor(point))),
            ...config,
        })),
    }));

    // Update cache
    cachedData = data;
    cachedCategorizedGraphs = categorizedGraphs;

    return categorizedGraphs;
}

// Flatten for backward compatibility
export function buildGraphs(run: RunResponse): GraphData[] {
    return buildCategorizedGraphs(run).flatMap(category => category.graphs);
}