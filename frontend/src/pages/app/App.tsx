import { Routes, Route } from 'react-router-dom';

export const App = () => {
    return (
        <Routes>
            <Route path='/' element={} />
            <Route path='/input' element={} />
            <Route path='/playback' element={} />
            <Route path='*' element={<div>404 - Not found</div>} />
        </Routes>
    )
}