import { Routes, Route } from 'react-router-dom';
import { Dashboard } from '@pages/dashboard/Dashboard';
import { Input } from '@pages/input/Input';
import { Playback } from '@pages/playback/Playback';

export const App = () => {
    return (
        <Routes>
            <Route path='/' element={<Dashboard/>} />
            <Route path='/input' element={<Input/>} />
            <Route path='/playback' element={<Playback/>} />
            <Route path='*' element={<div>404 - Not found</div>} />
        </Routes>
    )
}