import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { Home } from '@pages/home/Home';

const Dashboard = lazy(() => import('@pages/dashboard/Dashboard').then(({ Dashboard: Page }) => ({ default: Page })));
const Demo = lazy(() => import('@pages/demo/Demo').then(({ Demo: Page }) => ({ default: Page })));
const Input = lazy(() => import('@pages/input/Input').then(({ Input: Page }) => ({ default: Page })));
const Playback = lazy(() => import('@pages/playback/Playback').then(({ Playback: Page }) => ({ default: Page })));
const GeometryStudy = lazy(() => import('@pages/geometry/GeometryStudy').then(({ GeometryStudy: Page }) => ({ default: Page })));

/**
 * Keep the landing route light. Secondary pages load only after navigation, so
 * the Three.js/ECharts playback dependencies are excluded from the home bundle.
 */
export const App = () => (
  <Suspense fallback={null}>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/demo" element={<Demo />} />
      <Route path="/input" element={<Input />} />
      <Route path="/playback" element={<Playback />} />
      <Route path="/geometry" element={<GeometryStudy />} />
      <Route path="*" element={<div>404 - Not found</div>} />
    </Routes>
  </Suspense>
);
