import { Routes, Route } from 'react-router-dom';
import { Home } from '@pages/home/Home';
import { ParamInput } from '@pages/paramInput/ParamInput';
import { Playback } from '@pages/playback/Playback';

export const App = () => {
    return (
        <Routes>
            <Route path='/' element={<Home/>} />
            <Route path='/input' element={<ParamInput/>} />
            <Route path='/playback' element={<Playback/>} />
            <Route path='*' element={<div>404 - Not found</div>} />
        </Routes>
    )
}