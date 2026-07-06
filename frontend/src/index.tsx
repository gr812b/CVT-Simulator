import '@styles/_base.scss'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from '@pages/app/App'
import { ThemeProvider } from '@contexts/ThemeContext';
import { ParameterProvider } from '@contexts/ParameterContext';
import { LoadingProvider } from '@contexts/LoadingContext';
import { SimulationCaseProvider } from '@contexts/SimulationCaseContext';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element not found. Make sure there is an element with id="root" in your HTML.');
}

const root = createRoot(rootElement as HTMLElement);

root.render(
  <StrictMode>
    <ThemeProvider>
      <SimulationCaseProvider>
        <ParameterProvider>
        <LoadingProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </LoadingProvider>
        </ParameterProvider>
      </SimulationCaseProvider>
    </ThemeProvider>
  </StrictMode>,
)
