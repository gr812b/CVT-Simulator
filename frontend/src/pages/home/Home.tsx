import { Brand } from '@components/appShell/Brand';
import { useAuth } from '@contexts/AuthContext';
import { lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import {
  Anchor,
  Badge,
  Button,
  Center,
  Container,
  Group,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import {
  IconArrowRight,
  IconBrandGithub,
  IconFileText,
  IconPlayerPlay,
} from '@tabler/icons-react';
import { PublicHeader } from '@components/appShell/PublicHeader';
import styles from './Home.module.scss';

const HomeCvtPreview = lazy(() => import('./HomeCvtPreview'));
const GITHUB_URL = 'https://github.com/gr812b/CVT-Simulator';
const PAPER_URL = `${GITHUB_URL}/blob/develop/docs/CVT_Module_Formulation/CVT_Module_Formulation.pdf`;
const external = { target: '_blank', rel: 'noopener noreferrer' } as const;

const steps = [
  {
    number: '01',
    title: 'Build your setup',
    text: 'Bring together a vehicle, CVT, belt and engine. Start with public examples, then make them your own.',
  },
  {
    number: '02',
    title: 'Give it a road',
    text: 'Choose a road grade or create a reusable load case with hills and whoops. Review the complete setup before you run.',
  },
  {
    number: '03',
    title: 'Follow the motion',
    text: 'Replay the CVT alongside plots of speed, ratio, torque and belt behaviour. Keep the inputs with the result, and export the data.',
  },
];

export const Home = () => {
  const { session } = useAuth();
  return (
    <div className={styles.home}>
      <Container size="xl">
        <PublicHeader />
        <main>
          <section className={styles.hero} aria-labelledby="home-title">
            <Stack gap="xl" className={styles.heroCopy}>
              <Text className={styles.eyebrow}>CVT dynamics, made visible</Text>
              <Title id="home-title" className={styles.title}>
                Understand
                <br />
                every <span>shift.</span>
              </Title>
              <Text size="lg" c="dimmed" maw={490}>
                Explore how a belt CVT responds to the vehicle, the engine and
                the road. Build a setup, run the model, and see the motion
                behind the numbers.
              </Text>
              <Group gap="sm">
                <Button
                  component={Link}
                  to="/demo"
                  size="md"
                  leftSection={<IconPlayerPlay size={18} />}
                >
                  Explore the demo
                </Button>
                <Button
                  component={Link}
                  to={session ? '/input' : '/register'}
                  size="md"
                  variant="default"
                  rightSection={<IconArrowRight size={18} />}
                >
                  {session ? 'Build a setup' : 'Create a free account'}
                </Button>
              </Group>
              <Text size="sm" c="dimmed">
                The recorded demo is ready to explore. No account needed.
              </Text>
            </Stack>
            <figure className={styles.modelFigure}>
              <div className={styles.model}>
                <Suspense
                  fallback={
                    <Center h="100%">
                      <Loader size="sm" aria-label="Loading 3D preview" />
                    </Center>
                  }
                >
                  <HomeCvtPreview />
                </Suspense>
              </div>
              <figcaption>
                <span className={styles.modelLabel}>
                  A belt. Two pulleys. A changing ratio.
                </span>
                <span>Default CVT · drag or use arrow keys to rotate</span>
              </figcaption>
            </figure>
          </section>
          <section className={styles.workflow} aria-labelledby="workflow-title">
            <Group justify="space-between" align="end" mb="xl">
              <div>
                <Text className={styles.eyebrow} mb="sm">
                  From setup to insight
                </Text>
                <Title id="workflow-title" order={2}>
                  Make the whole drivetrain part of the question.
                </Title>
              </div>
              <Anchor component={Link} to="/catalog">
                Explore the public library →
              </Anchor>
            </Group>
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
              {steps.map((step) => (
                <Paper
                  key={step.number}
                  withBorder
                  p="xl"
                  className={styles.step}
                >
                  <Text className={styles.stepNumber}>{step.number}</Text>
                  <Title order={3} size="h4" mt="lg" mb="sm">
                    {step.title}
                  </Title>
                  <Text c="dimmed">{step.text}</Text>
                </Paper>
              ))}
            </SimpleGrid>
            <Text c="dimmed" size="sm" mt="lg">
              Saved configurations and runs are public on free accounts, so
              examples are easy to explore and reuse.
            </Text>
          </section>
          <section className={styles.research} aria-labelledby="research-title">
            <Stack gap="md">
              <Text className={styles.eyebrow}>Built around the model</Text>
              <Title id="research-title" order={2}>
                Read the reasoning.
                <br />
                Explore the implementation.
              </Title>
              <Text c="dimmed" maw={570}>
                CINDER brings belt CVT geometry, actuation and drivetrain
                dynamics into one simulation workflow. The accompanying
                formulation paper explains the model and its assumptions; the
                repository lets you follow the implementation.
              </Text>
              <Group mt="sm">
                <Button
                  component="a"
                  href={PAPER_URL}
                  {...external}
                  variant="default"
                  leftSection={<IconFileText size={18} />}
                >
                  Read the paper
                </Button>
                <Button
                  component="a"
                  href={GITHUB_URL}
                  {...external}
                  variant="subtle"
                  leftSection={<IconBrandGithub size={18} />}
                >
                  View on GitHub
                </Button>
              </Group>
            </Stack>
            <Stack gap="lg" className={styles.author}>
              <Badge variant="light" w="fit-content">
                An evolving engineering tool
              </Badge>
              <Text size="xl" fw={600}>
                Created by Kai Arseneau
              </Text>
              <Text c="dimmed">
                Rooted in Baja SAE drivetrain design. Built to make CVT
                behaviour easier to investigate, discuss and understand.
              </Text>
              <Text size="sm" c="dimmed">
                Use the model with its documented assumptions. Questions, ideas
                and bug reports are welcome on GitHub.
              </Text>
            </Stack>
          </section>
        </main>
        <Group
          component="footer"
          justify="space-between"
          className={styles.footer}
        >
          <Group gap="md">
            <Brand />
            <Text size="sm" c="dimmed">
              By Kai Arseneau
            </Text>
          </Group>
          <Group gap="lg">
            <Anchor href={PAPER_URL} {...external} size="sm">
              Paper
            </Anchor>
            <Anchor href={GITHUB_URL} {...external} size="sm">
              GitHub
            </Anchor>
            <Anchor component={Link} to="/demo" size="sm">
              Try the demo
            </Anchor>
            <Anchor
              href="https://pypi.org/project/cinder-cvt/"
              {...external}
              size="sm"
            >
              PyPI package
            </Anchor>
          </Group>
        </Group>
      </Container>
    </div>
  );
};
