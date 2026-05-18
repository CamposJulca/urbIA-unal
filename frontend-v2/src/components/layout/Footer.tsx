import { Link } from 'react-router-dom';
import unalLogo from '@/assets/logos/unal-logo-text.svg';
import innovaLogo from '@/assets/logos/innova-logo-text.svg';
import neusiLogo from '@/assets/logos/neusi-logo-text.svg';

/**
 * Footer institucional con tres columnas: descripcion del proyecto,
 * logos institucionales y enlaces utiles. Borde superior con tinte
 * primary-light para reafirmar la identidad UNAL.
 */
export function Footer(): JSX.Element {
  return (
    <footer className="mt-16 bg-neutral-900 text-neutral-300 border-t-2 border-primary-light">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-10 px-8 py-12 md:grid-cols-3">
        <div>
          <p className="font-display text-lg font-semibold text-white">UrbIA</p>
          <p className="mt-2 text-sm leading-relaxed text-neutral-400">
            Sistema modular IoT-SDN-Edge para gestion energetica urbana.
            Tesis doctoral en Ingenieria, Universidad Nacional de Colombia,
            sede Manizales.
          </p>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
            Institucional
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-6">
            <img src={unalLogo} alt="UNAL Manizales" className="h-8 w-auto opacity-90 brightness-[1.4]" />
            <img src={innovaLogo} alt="Innova" className="h-8 w-auto opacity-90 brightness-[1.4]" />
            <img src={neusiLogo} alt="Neusi" className="h-8 w-auto opacity-90 brightness-[1.4]" />
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
            Enlaces
          </p>
          <ul className="mt-4 space-y-2 text-sm">
            <li>
              <a
                href="https://github.com/CamposJulca/urbIA-unal"
                target="_blank"
                rel="noreferrer noopener"
                className="text-neutral-300 hover:text-white"
              >
                Repositorio GitHub
              </a>
            </li>
            <li>
              <a
                href="https://www.apache.org/licenses/LICENSE-2.0"
                target="_blank"
                rel="noreferrer noopener"
                className="text-neutral-300 hover:text-white"
              >
                Licencia Apache-2.0
              </a>
            </li>
            <li>
              <Link to="/acerca" className="text-neutral-300 hover:text-white">
                Contacto academico
              </Link>
            </li>
          </ul>
        </div>
      </div>

      <div className="border-t border-neutral-800">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-8 py-4 text-xs text-neutral-500 sm:flex-row">
          <span>© {new Date().getFullYear()} Cristhiam Daniel Campos Julca · UNAL Manizales</span>
          <span>Grupo PCI — Percepcion y Control Inteligente</span>
        </div>
      </div>
    </footer>
  );
}
