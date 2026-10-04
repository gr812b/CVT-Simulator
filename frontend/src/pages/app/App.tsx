import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { AuthPage } from '@pages/auth/AuthPage';
import { AccountSettings } from '@pages/auth/AccountSettings';
import { ApplicationShell } from '@components/appShell/ApplicationShell';
import { Center, Loader } from '@mantine/core';
import { Home } from '@pages/home/Home';

const Dashboard = lazy(() =>
  import('@pages/dashboard/Dashboard').then(({ Dashboard: Page }) => ({
    default: Page,
  })),
);
const Demo = lazy(() =>
  import('@pages/demo/Demo').then(({ Demo: Page }) => ({ default: Page })),
);
const Input = lazy(() =>
  import('@pages/input/Input').then(({ Input: Page }) => ({ default: Page })),
);
const Playback = lazy(() =>
  import('@pages/playback/Playback').then(({ Playback: Page }) => ({
    default: Page,
  })),
);
const GeometryStudy = lazy(() =>
  import('@pages/geometry/GeometryStudy').then(({ GeometryStudy: Page }) => ({
    default: Page,
  })),
);
const Validation = lazy(() =>
  import('@pages/validation/Validation').then(({ Validation: Page }) => ({
    default: Page,
  })),
);
const ValidationResults = lazy(() =>
  import('@pages/validationResults/ValidationResults').then(
    ({ ValidationResults: Page }) => ({
      default: Page,
    }),
  ),
);
const PrimaryDesign = lazy(() =>
  import('@pages/primaryDesign/PrimaryDesign').then(
    ({ PrimaryDesign: Page }) => ({
      default: Page,
    }),
  ),
);
const Library = lazy(() =>
  import('../../features/physicalLibrary/LibraryPage').then(
    ({ LibraryPage }) => ({ default: LibraryPage }),
  ),
);
const PhysicalEditor = lazy(() =>
  import('../../features/physicalLibrary/PhysicalEditor').then(
    ({ PhysicalEditorPage }) => ({ default: PhysicalEditorPage }),
  ),
);
const RunPage = lazy(() =>
  import('../../features/experiments/RunPage').then(({ RunPage: Page }) => ({
    default: Page,
  })),
);
const RunHistory = lazy(() =>
  import('../../features/results/RunHistory').then(({ RunHistory }) => ({
    default: RunHistory,
  })),
);
const PublicLibrary = lazy(() =>
  import('../../features/publicLibrary/PublicLibrary').then(
    ({ PublicLibrary }) => ({ default: PublicLibrary }),
  ),
);
const Publication = lazy(() =>
  import('../../features/publicLibrary/PublicationPage').then(
    ({ PublicationPage }) => ({ default: PublicationPage }),
  ),
);

const LoadCases = lazy(() =>
  import('../../features/experiments/LoadCaseLibrary').then(
    ({ LoadCaseLibrary }) => ({ default: LoadCaseLibrary }),
  ),
);
const PublicExperiment = lazy(() =>
  import('../../features/publicLibrary/PublicExperiment').then(
    ({ PublicExperiment }) => ({ default: PublicExperiment }),
  ),
);
const PublicRun = lazy(() =>
  import('../../features/publicLibrary/PublicRuns').then(({ PublicRun }) => ({
    default: PublicRun,
  })),
);
const PublicPlayback = lazy(() =>
  import('../../features/publicLibrary/PublicRuns').then(
    ({ PublicPlayback }) => ({ default: PublicPlayback }),
  ),
);

/**
 * Keep the landing route light. Secondary pages load only after navigation, so
 * the Three.js/ECharts playback dependencies are excluded from the home bundle.
 */
export const App = () => (
  <Suspense
    fallback={
      <Center mih="60vh">
        <Loader aria-label="Loading page" />
      </Center>
    }
  >
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/demo" element={<Demo />} />
      <Route path="/catalog" element={<PublicLibrary />} />
      <Route
        path="/catalog/load-cases/:objectId"
        element={<PublicExperiment />}
      />
      <Route path="/catalog/tunes/:objectId" element={<PublicExperiment />} />
      <Route path="/catalog/runs/:runId" element={<PublicRun />} />
      <Route
        path="/catalog/runs/:runId/playback"
        element={<PublicPlayback />}
      />
      <Route path="/catalog/:publicationId" element={<Publication />} />
      <Route path="/login" element={<AuthPage key="login" mode="login" />} />
      <Route
        path="/register"
        element={<AuthPage key="register" mode="register" />}
      />
      <Route
        path="/forgot-password"
        element={<AuthPage key="forgot" mode="forgot" />}
      />
      <Route
        path="/reset-password"
        element={<AuthPage key="reset" mode="reset" />}
      />
      <Route element={<ApplicationShell />}>
        <Route path="/account" element={<AccountSettings />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/library" element={<Library />} />
        <Route path="/library/:kind" element={<Library />} />
        <Route path="/library/:kind/:objectId" element={<PhysicalEditor />} />
        <Route path="/load-cases" element={<LoadCases />} />
        <Route path="/input" element={<Input />} />
        <Route path="/runs/:runId" element={<RunPage />} />
        <Route path="/runs" element={<RunHistory />} />
        <Route path="/playback" element={<Playback />} />
        <Route path="/geometry" element={<GeometryStudy />} />
        <Route path="/validation" element={<Validation />} />
        <Route path="/validation/runs/:runId" element={<ValidationResults />} />
        <Route path="/primary-design" element={<PrimaryDesign />} />
      </Route>
      <Route path="*" element={<div>404 - Not found</div>} />
    </Routes>
  </Suspense>
);
