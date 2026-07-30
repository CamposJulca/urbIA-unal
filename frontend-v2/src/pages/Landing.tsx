import { Link } from 'react-router-dom';
import { Activity, Cpu, Network, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import urbiaLogoLight from '@/assets/logos/urbia-logo-light.svg';

/**
 * Landing publica de UrbIA. Tres secciones:
 *  1. Hero con gradiente primary, logo grande y dos CTAs.
 *  2. Tres pilares arquitectonicos (Telemetria, SDN, Edge).
 *  3. Bloque doctoral con autoria.
 */

type Pillar = {
  icon: JSX.Element;
  title: string;
  description: string;
  link: string;
  status: 'datos reales' | 'datos historicos' | 'visualizacion conceptual';
};

// La telemetria AMI esta implementada de punta a punta, pero su badge
// no puede decir "datos reales" mientras la ingesta MQTT este detenida:
// lo que se sirve es el ultimo periodo capturado. 'datos historicos'
// cubre ese estado intermedio sin degradarlo a "conceptual", que seria
// injusto con el modulo que si funciona.
const STATUS_VARIANT: Record<Pillar['status'], 'success' | 'warning' | 'accent'> = {
  'datos reales': 'success',
  'datos historicos': 'warning',
  'visualizacion conceptual': 'accent',
};

const PILLARS: readonly Pillar[] = [
  {
    icon: <Activity className="h-6 w-6" aria-hidden="true" />,
    title: 'Telemetria AMI',
    description:
      'Diez medidores sinteticos en cinco zonas publicaron metricas DLMS-JSON al broker MQTT del cluster. La ingesta esta detenida: el backend conserva el ultimo periodo capturado y lo expone por REST.',
    link: '/telemetria',
    status: 'datos historicos',
  },
  {
    icon: <Network className="h-6 w-6" aria-hidden="true" />,
    title: 'Red Definida por Software',
    description:
      'Diseno de la topologia de control con Ryu sobre Mininet para gestion adaptativa del trafico entre los nodos del cluster. Sin implementar.',
    link: '/sdn',
    status: 'visualizacion conceptual',
  },
  {
    icon: <Cpu className="h-6 w-6" aria-hidden="true" />,
    title: 'Computacion Edge',
    description:
      'Monitor GSP en nodos edge (Raspberry Pi 5) con deteccion espectral de anomalias sobre el grafo AMI. Nucleo doctoral, sin implementar.',
    link: '/edge',
    status: 'visualizacion conceptual',
  },
];

export default function Landing(): JSX.Element {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden bg-gradient-to-br from-primary-dark via-primary to-primary-light text-white">
        <div className="absolute inset-0 opacity-[0.08] [background-image:radial-gradient(circle_at_1px_1px,white_1px,transparent_0)] [background-size:24px_24px]" />
        <div className="relative mx-auto max-w-7xl px-6 py-24 md:py-28">
          <img src={urbiaLogoLight} alt="UrbIA" className="h-20 w-auto md:h-24" />
          <h1 className="mt-8 max-w-3xl text-4xl font-bold leading-tight tracking-tight md:text-5xl">
            Sistema modular IoT-SDN-Edge para gestion energetica urbana
          </h1>
          <p className="mt-4 max-w-2xl text-lg text-white/80 md:text-xl">
            Arquitectura para el monitoreo distribuido de redes AMI con deteccion espectral
            de anomalias mediante procesamiento de senales sobre grafos. Investigacion
            doctoral en curso: la capa de telemetria esta implementada; las capas SDN y edge
            estan en diseno.
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <Button asChild size="lg" variant="accent">
              <Link to="/telemetria">
                Ver telemetria
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline-white">
              <Link to="/acerca">Sobre el proyecto</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Pilares */}
      <section className="py-24">
        <div className="mx-auto max-w-7xl px-6">
          <div className="text-center">
            <p className="text-sm font-semibold uppercase tracking-wider text-primary">
              Arquitectura
            </p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-ink md:text-4xl">
              Tres pilares arquitectonicos
            </h2>
            <p className="mx-auto mt-3 max-w-2xl text-ink-muted">
              UrbIA integra una capa de telemetria ya implementada con dos capas de
              coordinacion todavia en diseno, definidas en el nucleo doctoral.
            </p>
          </div>

          <div className="mt-12 grid grid-cols-1 gap-6 md:grid-cols-3">
            {PILLARS.map((p) => (
              <Card key={p.title} className="flex flex-col transition-shadow hover:shadow-elev">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-primary">
                      {p.icon}
                    </div>
                    <Badge variant={STATUS_VARIANT[p.status]}>
                      {p.status}
                    </Badge>
                  </div>
                  <CardTitle className="mt-3">{p.title}</CardTitle>
                  <CardDescription>{p.description}</CardDescription>
                </CardHeader>
                <CardContent className="flex-1" />
                <CardFooter>
                  <Button asChild variant="link" className="px-0">
                    <Link to={p.link}>
                      Abrir modulo
                      <ArrowRight className="h-4 w-4" aria-hidden="true" />
                    </Link>
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Bloque doctoral */}
      <section className="bg-neutral-50 py-16">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <p className="text-sm font-semibold uppercase tracking-wider text-primary">
            Proyecto doctoral
          </p>
          <h3 className="mt-2 text-xl font-semibold text-ink">
            Tesis del Doctorado en Ingenieria · UNAL Manizales
          </h3>
          <p className="mt-4 text-neutral-600">
            UrbIA es la tesis doctoral de <strong>Cristhiam Daniel Campos Julca</strong>,
            dirigida por <strong>G. A. Osorio Londono</strong> con co-asesoria de{' '}
            <strong>L. A. Aristizabal Quintero</strong>, en la Universidad Nacional de
            Colombia, sede Manizales. Extiende el trabajo experimental de J. S. Giraldo
            Duque (MSc 2026) incorporando el aparato matematico de coordinacion con
            autorregulacion basado en GSP y Reinforcement Learning.
          </p>
        </div>
      </section>
    </>
  );
}
