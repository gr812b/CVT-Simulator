import { Route, Routes } from 'react-router-dom';
import { Home } from '@pages/home/Home';
import { Input } from '@pages/input/Input';
import { Playback } from '@pages/playback/Playback';
import { GeometryStudy } from '@pages/geometry/GeometryStudy';
import { Dashboard } from '@pages/dashboard/Dashboard';
import { Demo } from '@pages/demo/Demo';

export const App = () => (
  <Routes>
    <Route path="/" element={<Home />} />
    <Route path="/dashboard" element={<Dashboard />} />
    <Route path="/demo" element={<Demo />} />
    <Route path="/input" element={<Input />} />
    <Route path="/playback" element={<Playback />} />
    <Route path="/geometry" element={<GeometryStudy />} />
    <Route path="*" element={<div>404 - Not found</div>} />
  </Routes>
);
