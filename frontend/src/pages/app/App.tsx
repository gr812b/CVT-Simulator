import { Routes, Route } from 'react-router-dom';
import { Home } from '@pages/home/Home';
import { Dashboard } from '@pages/dashboard/Dashboard';
import { Input } from '@pages/input/Input';
import { Playback } from '@pages/playback/Playback';
import { Demo } from '@pages/demo/Demo';

export const App = () => {
    return (
        <Routes>
            <Route path='/' element={<Home/>} />
            <Route path='/dashboard' element={<Dashboard/>} />
            <Route path='/input' element={<Input/>} />
            <Route path='/playback' element={<Playback/>} />
            <Route path='/demo' element={<Demo/>} />
            <Route path='*' element={<div>404 - Not found</div>} />
        </Routes>
    )
}