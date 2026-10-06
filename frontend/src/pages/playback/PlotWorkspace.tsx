import { PlotInfo } from '@components/plotInfo/PlotInfo';
import { REPORT_PLOT_HELP } from './reportPlotHelp';
import { useMemo, useRef, useState } from 'react';
import { Modal } from '@components/modal/Modal';
import { Group, MultiSelect, Paper, Stack, Tabs, Text } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Graph2D, type GraphViewState } from '@components/graph2D/graph2D';
import { compactChartLayout } from '@components/graph2D/compactChartLayout';
import { IconRestore } from '@tabler/icons-react';
import {
  DEFAULT_PLOTS,
  usePlotPreferences,
} from '../../features/playback/preferences';
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
  const [preferences, setPreferences] = usePlotPreferences();
  const { choices } = preferences;
  const tab = tabs.some((item) => item.id === preferences.tab)
    ? preferences.tab
    : 'overview';
  const [resetKey, setResetKey] = useState(0);
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
  const selected = (choices[tab] ?? current.defaults).filter((title) =>
    graphs.some((g) => g.config.title === title),
  );
  const shown = graphs.filter((g) => selected.includes(g.config.title!));
  const draw = (graph: (typeof graphs)[number], large = false) => (
    <Graph2D
      {...graph}
      config={{ ...graph.config, title: undefined, height: large ? 560 : 310 }}
      chartOptions={compactChartLayout(
        graph.config.yAxis.unit ?? graph.config.yAxis.name,
      )}
      replayController={controller}
      viewState={
        states.current.get(graph.config.title!) ?? {
          zoom: [],
          selected: preferences.series[graph.config.title!] ?? {},
        }
      }
      onViewStateChange={(state) => {
        const title = graph.config.title!;
        states.current.set(title, state);
        if (
          JSON.stringify(preferences.series[title] ?? {}) !==
          JSON.stringify(state.selected)
        ) {
          setPreferences((current) => ({
            ...current,
            series: { ...current.series, [title]: state.selected },
          }));
        }
      }}
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
              setPreferences((current) => ({ ...current, tab: value }));
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
        <Group justify="space-between">
          <Text size="sm" fw={500} id="plot-picker-label">
            Plots
          </Text>
          <Button
            size="compact-xs"
            variant="subtle"
            leftSection={<IconRestore size={13} />}
            onClick={() => {
              states.current.clear();
              setPreferences(DEFAULT_PLOTS);
              setExpanded(null);
              setResetKey((value) => value + 1);
            }}
          >
            Reset plots
          </Button>
        </Group>
        <MultiSelect<string>
          aria-labelledby="plot-picker-label"
          description="Choose up to four. Click a plot to move playback to that point."
          data={graphs.map((g) => g.config.title!)}
          value={selected}
          maxValues={4}
          searchable
          onChange={(value) =>
            setPreferences((current) => ({
              ...current,
              choices: { ...current.choices, [tab]: value },
            }))
          }
        />
        <div className={styles.plotGrid} key={resetKey}>
          {shown.map((graph) => (
            <Paper withBorder p="xs" key={graph.config.title!}>
              <Group justify="space-between" align="start" wrap="nowrap">
                <Group gap={5} wrap="nowrap">
                  <Text size="sm" fw={600}>{graph.config.title}</Text>
                  <PlotInfo title={graph.config.title!} description={REPORT_PLOT_HELP[graph.config.title!] ?? 'A recorded report quantity. Follow the plotted axis units and series labels.'}/>
                </Group>
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
        title={<Group gap={5}>{expanded}<PlotInfo title={expanded ?? 'Plot'} description={REPORT_PLOT_HELP[expanded ?? ''] ?? 'A recorded report quantity.'}/></Group>}
        size="min(1200px, 96vw)"
      >
        {enlarged && draw(enlarged, true)}
      </Modal>
    </Paper>
  );
}
