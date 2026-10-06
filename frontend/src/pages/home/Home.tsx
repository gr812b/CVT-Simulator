import { Brand } from '@components/appShell/Brand';
import { useAuth } from '@contexts/AuthContext';
import { lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import {
  Anchor,
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
  IconBrandDiscord,
  IconBrandGithub,
  IconFileText,
  IconMail,
  IconPlayerPlay,
} from '@tabler/icons-react';
import { PublicHeader } from '@components/appShell/PublicHeader';
import { PROJECT_CONTACT, PROJECT_LINKS } from '../../config/projectLinks';
import styles from './Home.module.scss';

const HomeCvtPreview = lazy(() => import('./HomeCvtPreview'));
const external = { target: '_blank', rel: 'noopener noreferrer' } as const;

const steps = [
  {
    number: '01',
    title: 'Use your own vehicle and CVT',
    text: 'Enter your vehicle, engine, belt and CVT dimensions, or start from the McMaster defaults. Save the parts you want to reuse.',
  },
  {
    number: '02',
    title: 'Choose a tune and load case',
    text: 'Adjust the springs, flyweights and helix, then choose a saved road or build one with climbs, descents and whoops.',
  },
  {
    number: '03',
    title: 'Look inside the result',
    text: 'Replay the motion with force vectors, inspect speed, ratio, torque and belt slip, and download the data for your own analysis.',
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
              <Text className={styles.eyebrow}>
                Rubber V-belt CVT simulation
              </Text>
              <Title id="home-title" className={styles.title}>
                Understand
                <br />
                every <span>shift.</span>
              </Title>
              <Text size="lg" c="dimmed" maw={490}>
                Simulate your vehicle and CVT with different tunes and road
                loads. Replay the motion and inspect the forces, torque and belt
                slip using the model described in the paper.
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
                <span className={styles.modelLabel}>McMaster 2025 CVT</span>
                <span>Drag or use arrow keys to rotate</span>
              </figcaption>
            </figure>
          </section>
          <section className={styles.workflow} aria-labelledby="workflow-title">
            <Group justify="space-between" align="end" mb="xl">
              <div>
                <Text className={styles.eyebrow} mb="sm">
                  Using CINDER
                </Text>
                <Title id="workflow-title" order={2}>
                  Set up a run, then explore what happened.
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
              <Text className={styles.eyebrow}>The formulation</Text>
              <Title id="research-title" order={2}>
                The model behind the simulation.
              </Title>
              <Text c="dimmed" maw={570}>
                The paper derives the coupled motion of the pulleys, belt and
                clamping mechanisms, and explains the assumptions and numerical
                checks. CINDER implements that formulation; this website gives
                you a way to set up simulations and inspect their results.
              </Text>
              <Group mt="sm">
                <Button
                  component="a"
                  href={PROJECT_LINKS.paper}
                  {...external}
                  variant="default"
                  leftSection={<IconFileText size={18} />}
                >
                  Read the paper
                </Button>
                <Button
                  component="a"
                  href={PROJECT_LINKS.github}
                  {...external}
                  variant="subtle"
                  leftSection={<IconBrandGithub size={18} />}
                >
                  View on GitHub
                </Button>
              </Group>
            </Stack>
            <Stack
              component="aside"
              gap="md"
              className={styles.author}
              aria-labelledby="author-title"
            >
              <Title id="author-title" order={2} size="h3">
                About this project
              </Title>
              <Text c="dimmed">
                This website is still a work in progress, and most of the
                interface was built with AI, so there are almost certainly some
                bugs. The CVT model itself is the part I’ve spent much more time
                on, and the full derivation, assumptions, and checks are in the
                paper.
              </Text>
              <Text c="dimmed">
                Experimental validation is still to come, so if you have access
                to a CVT dyno, test data, or anything else that could be useful,
                definitely hit me up below.
              </Text>
              <Text c="dimmed">
                Hopefully this makes the model a little easier to explore and
                CVTs a little less of a black box. Everything is free to use,
                and the source is on GitHub.
              </Text>
              <Text c="dimmed">
                If you have questions, find something broken, want to talk about
                the paper, or just have thoughts on the project, reach out.
              </Text>
              <Text size="sm">– Kai</Text>
              <Group gap="lg" aria-label="Contact Kai">
                <Anchor href={`mailto:${PROJECT_CONTACT.email}`} size="sm">
                  <Group gap="xs" component="span">
                    <IconMail size={17} aria-hidden="true" />
                    <span>{PROJECT_CONTACT.email}</span>
                  </Group>
                </Anchor>
                <Group gap="xs">
                  <IconBrandDiscord size={17} aria-hidden="true" />
                  <Text size="sm">Discord: {PROJECT_CONTACT.discord}</Text>
                </Group>
              </Group>
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
            <Anchor href={PROJECT_LINKS.paper} {...external} size="sm">
              Paper
            </Anchor>
            <Anchor href={PROJECT_LINKS.github} {...external} size="sm">
              GitHub
            </Anchor>
            <Anchor href={PROJECT_LINKS.license} {...external} size="sm">
              Source license
            </Anchor>
            <Anchor component={Link} to="/demo" size="sm">
              Try the demo
            </Anchor>
            <Anchor href={PROJECT_LINKS.package} {...external} size="sm">
              PyPI package
            </Anchor>
          </Group>
        </Group>
      </Container>
    </div>
  );
};
