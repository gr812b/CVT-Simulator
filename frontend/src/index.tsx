import '@styles/_base.scss'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Home from './pages/home/Home.tsx'
import { Input } from './pages/input/Input.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home/>} />
        <Route path="/input" element={<Input/>} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
