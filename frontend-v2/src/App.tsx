import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { PageLoader } from '@/components/layout/PageLoader';

// Code splitting por ruta: cada pagina viaja en su propio chunk.
const Landing = lazy(() => import('@/pages/Landing'));
const Telemetry = lazy(() => import('@/pages/Telemetry'));
const SDN = lazy(() => import('@/pages/SDN'));
const Edge = lazy(() => import('@/pages/Edge'));
const About = lazy(() => import('@/pages/About'));

export default function App(): JSX.Element {
  return (
    <AppLayout>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/telemetria" element={<Telemetry />} />
          <Route path="/sdn" element={<SDN />} />
          <Route path="/edge" element={<Edge />} />
          <Route path="/acerca" element={<About />} />
          <Route path="*" element={<Landing />} />
        </Routes>
      </Suspense>
    </AppLayout>
  );
}
