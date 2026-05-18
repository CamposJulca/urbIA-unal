import type { ReactNode } from 'react';
import { Header } from './Header';
import { Footer } from './Footer';

/**
 * Layout raiz: Header sticky de 64px + main flexible + Footer.
 * El main usa padding-top 0 porque el Header es sticky, no fixed.
 */
export function AppLayout({ children }: { children: ReactNode }): JSX.Element {
  return (
    <div className="flex min-h-screen flex-col bg-bg text-ink">
      <Header />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}
