import '@mantine/core/styles.css';
import '@styles/_base.scss';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { App } from '@pages/app/App';
import { AuthProvider } from '@contexts/AuthContext';
import { theme, cssVariablesResolver } from '@styles/theme';
const root = document.getElementById('root');
if (root === null) throw new Error('Root element not found.');
createRoot(root).render(
  <StrictMode>
    <MantineProvider
      theme={theme}
      cssVariablesResolver={cssVariablesResolver}
      forceColorScheme="dark"
    >
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </MantineProvider>
  </StrictMode>,
);
