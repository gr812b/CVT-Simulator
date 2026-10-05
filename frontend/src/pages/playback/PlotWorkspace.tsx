import { useMemo, useRef, useState } from 'react';
import {
  Group,
  Modal,
  MultiSelect,
  Paper,
  Stack,
  Tabs,
  Text,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Graph2D, type GraphViewState } from '@components/graph2D/graph2D';
import { CHART_COLORS } from '@components/graph2D/chartOptions';
import type { ReportReplayController } from '@utils/reportReplay';
import type { GraphCategory } from './reportGraphs';
import styles from './Playback.module.scss';

const tabs = [
  {
    id: 'overview',
    label: 'Overview',
    groups: ['Kinematics', 'CVT Ratio', 'External Load'],
    defaults: [
      'Vehicle speed',
      'Vehicle acceleration',
      'CVT ratio',
      'Shift curve',
    ],
  },
  {
    id: 'primary',
    label: 'Primary',
    groups: ['Primary Pulley', 'CVT Ratio'],
    defaults: [
      'Primary axial force balance',
      'Primary flyweight forces',
      'Primary torque balance',
    ],
  },
  {
    id: 'secondary',
    label: 'Secondary',
    groups: ['Secondary Pulley'],
    defaults: [
      'Secondary axial force balance',
      'Secondary helix forces',
      'Secondary torque balance',
    ],
  },
  {
    id: 'engine',
    label: 'Engine',
    groups: ['Engine', 'Primary Pulley', 'Secondary Pulley', 'CVT Ratio'],
    defaults: ['Engine speed', 'Engine power'],
  },
  {
    id: 'belt',
    label: 'Belt & slip',
    groups: ['Belt Tension', 'Slip Model', 'Simulation Mode'],
    defaults: ['Belt tensions', 'Relative belt speed'],
  },
];

/** Only selected plots are mounted; zoom and legend choices survive tab changes. */
export function PlotWorkspace({
  categories,
  controller,
}: {
  categories: GraphCategory[];
  controller: ReportReplayController;
}) {
  const [tab, setTab] = useState('overview');
  const [choices, setChoices] = useState<Record<string, string[]>>({});
  const states = useRef(new Map<string, GraphViewState>());
  const [expanded, setExpanded] = useState<string | null>(null);
  const current = tabs.find((t) => t.id === tab)!;
  const graphs = useMemo(
    () =>
      categories
        .filter((c) => current.groups.includes(c.title))
        .flatMap((c) => c.graphs),
    [categories, current],
  );
  const selected =
    choices[tab] ??
    current.defaults.filter((title) =>
      graphs.some((g) => g.config.title! === title),
    );
  const shown = graphs.filter((g) => selected.includes(g.config.title!));
  const draw = (graph: (typeof graphs)[number], large = false) => (
    <Graph2D
      {...graph}
      config={{ ...graph.config, title: undefined, height: large ? 560 : 310 }}
      chartOptions={{
        legend: {
          type: 'scroll',
          top: 12,
          left: 10,
          right: 120,
          textStyle: { color: CHART_COLORS.TEXT },
        },
        grid: { top: 55, left: 45, right: 15, bottom: 40, containLabel: true },
      }}
      replayController={controller}
      viewState={states.current.get(graph.config.title!)}
      onViewStateChange={(state) =>
        states.current.set(graph.config.title!, state)
      }
    />
  );
  const enlarged = graphs.find((g) => g.config.title! === expanded);
  return (
    <Paper withBorder p="md" className={styles.analysisPanel}>
      <Stack gap="md">
        <Tabs
          value={tab}
          onChange={(value) => {
            if (value) {
              setTab(value);
              setExpanded(null);
            }
          }}
        >
          <Tabs.List>
            {tabs.map((t) => (
              <Tabs.Tab key={t.id} value={t.id}>
                {t.label}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>
        <MultiSelect<string>
          label="Plots"
          description="Choose up to four. Click a plot to move playback to that point."
          data={graphs.map((g) => g.config.title!)}
          value={selected}
          maxValues={4}
          searchable
          onChange={(value) => setChoices({ ...choices, [tab]: value })}
        />
        <div className={styles.plotGrid}>
          {shown.map((graph) => (
            <Paper withBorder p="xs" key={graph.config.title!}>
              <Group justify="space-between" align="start" wrap="nowrap">
                <Text size="sm" fw={600}>
                  {graph.config.title}
                </Text>
                <Button
                  size="compact-xs"
                  variant="subtle"
                  onClick={() => setExpanded(graph.config.title!)}
                >
                  Expand plot
                </Button>
              </Group>
              {expanded === graph.config.title! ? (
                <Text c="dimmed" mih={310}>
                  Open in expanded view.
                </Text>
              ) : (
                draw(graph)
              )}
            </Paper>
          ))}
        </div>
        {!shown.length && <Text c="dimmed">Choose a plot above.</Text>}
      </Stack>
      <Modal
        opened={!!enlarged}
        onClose={() => setExpanded(null)}
        title={expanded}
        size="min(1200px, 96vw)"
      >
        {enlarged && draw(enlarged, true)}
      </Modal>
    </Paper>
  );
}
