# CLAUDE.md — Contexto persistente del proyecto UrbIA-UNAL

> Este archivo es leído automáticamente por Claude Code al iniciar una sesión en este repositorio. Define el contexto, las reglas y las convenciones del proyecto. No lo elimines ni lo modifiques sin coordinarlo con el autor.

---

## 1. Identidad del proyecto

### 1.1 Qué es UrbIA

Tesis doctoral del **Doctorado en Ingeniería** de la **Universidad Nacional de Colombia, sede Manizales**.

UrbIA es una arquitectura modular IoT–SDN–Edge para la gestión energética urbana, con énfasis en infraestructura de medición avanzada (AMI). El proyecto extiende el trabajo experimental de J. S. Giraldo Duque (MSc, abril 2026) incorporando el aparato matemático de coordinación con autorregulación basado en Graph Signal Processing (GSP) y Reinforcement Learning (RL) desarrollado por L. A. Aristizábal Quintero (PhD, 2022).

### 1.2 Personas

| Rol | Persona |
|---|---|
| Autor | Cristhiam Daniel Campos Julca (`ccamposj@unal.edu.co`) |
| Director | G. A. Osorio Londoño |
| Co-asesora | L. A. Aristizábal Quintero |
| Antecedente experimental | J. S. Giraldo Duque (tesis MSc 2026) |
| Grupo de investigación | PCI — Percepción y Control Inteligente, UNAL Manizales |

### 1.3 Repositorio

- GitHub: `github.com/CamposJulca/urbIA-unal`
- Licencia: Apache-2.0
- Visibilidad: pública
- Branch principal: `main`

---

## 2. Las tres capas de UrbIA

UrbIA es **simultáneamente** tres cosas. Cualquier código que se escriba debe respetar las tres:

### 2.1 Capa de contribución doctoral
Aporte científico al estado del arte: monitor distribuido basado en GSP aplicado al dominio AMI urbana, con detección espectral de anomalías y QoS adaptativo regulado por RL. Este es el núcleo defendible ante el jurado.

### 2.2 Capa de arquitectura del sistema
Modelo de referencia modular IoT–SDN–Edge organizado en capas (presentación, aplicación, dominio/persistencia, edge/fog, SDN, plataforma IoT, simulación), alineado con marcos normativos internacionales vigentes. Este es el aporte de ingeniería.

### 2.3 Capa de producto de software
Aplicación funcional que recorre el ciclo completo de software: análisis → diseño → implementación → pruebas → prototipado. Alcance hasta prototipo demostrable, **no hasta producción**. La producción será responsabilidad del cliente o del despliegue en nube post-doctorado.

**Regla:** cuando trabajes en cualquier archivo, identifica mentalmente a cuál de estas tres capas pertenece. Si mezcla capas, refactoriza.

---

## 3. Líneas de contribución (núcleo doctoral)

UrbIA aborda tres líneas del trabajo futuro de Giraldo, integradas con el aparato de Aristizábal:

1. **Distribución del monitor multicapa** (línea futura de Aristizábal): bajar el monitor GSP del datacenter al nodo de borde.
2. **QoS adaptativo basado en clase de tráfico** (línea de Giraldo + Difuminador de Aristizábal).
3. **Detección de anomalías por análisis espectral del grafo** (Capítulo 3 de Aristizábal aplicado a AMI).

**Fuera del núcleo (trabajo futuro):** Coordinación P2P de pasarelas, despliegue urbano masivo real, integración SCADA, Federated Learning.

---

## 4. Cluster Neusi y rol de cada máquina

UrbIA corre sobre el cluster del datacenter Neusi (UNAL Manizales).

### 4.1 Máquinas y roles

| Nodo | IP | Hostname | CPU | RAM | Rol UrbIA |
|---|---|---|---|---|---|
| .100 | 192.168.0.100 | innova-produccion | Ryzen 5 5600GT | 14 GB | Observabilidad pública (Grafana ngrok) + entrenamiento RL |
| .101 | 192.168.0.101 | innova-desarrollo | Ryzen 5 5600GT | 15 GB | MQTT broker + ThingsBoard. Sostiene proyectos cliente. **NO desarrollar aquí.** |
| **.102** | **192.168.0.102** | **innova-pruebas** | **Ryzen 7 5700G** | **15 GB** | **CEREBRO. Esta es la máquina donde corre todo el código nuevo.** Backend, frontend, simulador, monitor GSP, bases de datos activas, Jupyter, Mininet/Ryu. |
| .103 | 192.168.0.103 | simulador1 | AMD A6-5200 | 3.3 GB | Gateway IoT + generador de tráfico hostil (cuando se recupere de problema térmico) |
| .104 | 192.168.0.104 | camposjulca | i5-2450M | 11 GB | Datos + NAS WD 10 TB (NFS). Backups, datasets, modelos, snapshots |
| .105 | 192.168.0.105 | manjaro-daniel | i5-8250U | 19 GB | Auditoría de seguridad (Kali) + Prometheus + Wireshark |
| .106 | (futura) | RPi5 edge | ARM | 8 GB | Edge gateway con monitor GSP distribuido — núcleo PhD |

### 4.2 Reglas operativas del cluster

- **.100 está libre durante el doctorado** porque la producción real se hará en el servidor del cliente o en nube post-doctorado.
- **.101 NO se toca para desarrollo nuevo.** Sostiene MQTT broker UrbIA (`urbia-mqtt`) y proyectos cliente productivos (Finagro, Serviparamo, Joz, etc.).
- **.102 es la máquina de trabajo principal.** Tiene la mejor CPU, red 10 Gbps, y está limpia.
- **.104 NO corre aplicaciones**. Solo I/O al NAS. Los servicios stateful viven en .102, pero los respaldos se mandan a .104 vía NFS.
- **.105 audita .102.** Pentesting, captura de tráfico, métricas Prometheus. No participa en el flujo de datos productivo.

---

## 5. Stack tecnológico

### 5.1 Lenguajes y frameworks

| Componente | Tecnología | Razón |
|---|---|---|
| Backend | **FastAPI** (Python 3.12) | Async, ligero, type-safe, ideal para tiempo real |
| Frontend | **Streamlit** (Python) | Velocidad de iteración para una persona; migrar a React si se justifica |
| Base relacional | **PostgreSQL 16** | JSON nativo, extensiones científicas, robustez |
| Base documental | **MongoDB 7** | Telemetría cruda y eventos |
| Cache/cola | **Redis 7** | Suficiente, simple |
| Mensajería IoT | **Mosquitto MQTT** | Estándar de facto, broker ya operativo en .101 |
| Monitor GSP | **Python + PyGSP + NetworkX** | Prototipado rápido; optimizar con NumPy/Numba si es necesario |
| Controlador SDN | **Ryu** (Python) | Aristizábal lo usa, Giraldo lo usa, transición natural |
| Simulación SDN | **Mininet** | Estándar académico |
| Orquestación | **docker-compose** | Adecuado para 6 máquinas; k8s sería overkill |
| CI/CD | **GitHub Actions** (luego Gitea Actions cuando se instale Gitea en .102) | Inicio simple |
| Observabilidad | **Prometheus + Grafana** | Liviano, ya en pendientes Neusi |
| Testing Python | **pytest** | Estándar |
| Testing Frontend | **Playwright** o **pytest + streamlit-testing** | Por decidir cuando llegue el momento |

### 5.2 Decisiones arquitectónicas registradas

Las decisiones se documentan en `docs/decisions/ADR-NNN-titulo.md`. Existentes:

- ADR-001: Monorepo
- ADR-002: Stack tecnológico
- (siguientes a medida que se tomen)

Ningún cambio de stack se hace sin un ADR nuevo.

---

## 6. Estructura del repositorio

```
urbia/
├── README.md
├── LICENSE                              # Apache-2.0
├── .gitignore
├── .env.example                         # template, sin secretos
├── CLAUDE.md                            # este archivo
├── docker-compose.yml                   # stack local en .102
├── docker-compose.prod.yml              # futuro (nube)
│
├── docs/                                # documentación
│   ├── api.md
│   ├── architecture.md
│   ├── decisions/                       # ADRs
│   └── thesis/                          # documento LaTeX del anteproyecto
│
├── services/                            # componentes ejecutables
│   ├── backend/                         # FastAPI
│   ├── frontend/                        # Streamlit
│   ├── simulator-ami/                   # simulador AMI nuevo
│   ├── sdn-controller/                  # Ryu modificado
│   ├── monitor-gsp/                     # núcleo doctoral
│   │   ├── src/
│   │   │   ├── graph/                   # construcción del grafo AMI
│   │   │   ├── gft/                     # Graph Fourier Transform
│   │   │   ├── wavelet/                 # wavelet multiescala
│   │   │   ├── detector/                # detección espectral
│   │   │   └── difuminador/             # filtro τ adaptativo
│   ├── adversarial/                     # generador de tráfico hostil (.103)
│   └── mqtt-bridge/                     # adaptador MQTT ↔ backend
│
├── libs/                                # código compartido
│   ├── urbia-ami-protocol/              # mensajes AMI (DLMS-JSON)
│   ├── urbia-graph/                     # utilidades de grafos
│   └── urbia-rl/                        # agente RL del Afinador
│
├── notebooks/                           # exploración Jupyter
│   ├── 01_grafo_ami_basico.ipynb
│   ├── 02_gft_caracterizacion.ipynb
│   └── 03_anomalias_espectrales.ipynb
│
├── experiments/                         # experimentos reproducibles
│   ├── baseline-giraldo/
│   ├── monitor-comparativa/
│   └── qos-adaptativo/
│
├── infra/                               # infraestructura como código
│   ├── ansible/
│   ├── networking/
│   └── observability/
│
├── data/                                # datos pequeños (los grandes en NAS)
│   ├── topologies/
│   └── synthetic/
│
└── scripts/                             # utilidades operativas
```

**Regla:** cada `services/<nombre>/` tiene siempre como mínimo: `Dockerfile`, `pyproject.toml` (o equivalente), `src/`, `tests/`, `README.md`, `SCHEMA.md` (si maneja schemas de datos).

---

## 7. Reglas de comunicación con el autor

### 7.1 Idioma y tono

- **Idioma:** español. El autor habla español de Colombia. Variantes neutras del español son aceptables.
- **Tono:** directo, sin halagos vacíos. Si una idea es mala, decirlo. Si una decisión tiene riesgos, advertirlos. Si algo no se sabe, decirlo en lugar de inventar.
- **Sin emojis** salvo cuando el autor los use primero.
- **Sin "claro", "perfecto", "excelente pregunta"** al inicio de respuestas. Empezar por la sustancia.

### 7.2 Antes de actuar

- Antes de implementar algo no trivial, **proponer un plan corto** y esperar confirmación.
- Antes de borrar archivos, modificar configuración del sistema, o tocar otras máquinas: **preguntar primero**.
- Cuando hay ambigüedad, **preguntar antes que asumir**.

### 7.3 Cuando hay error

- Leer el error completo antes de proponer solución.
- No silenciar errores con `try/except` vacíos.
- Pedirle al autor que pegue la salida completa, no fragmentos.

### 7.4 Cuando hay desacuerdo

- Si el autor pide algo que técnicamente parece mala idea, decirlo claro y explicar por qué. Después, si el autor insiste con argumentos, ejecutar.
- Si el autor pide algo que rompe seguridad, ética o estabilidad del cluster: no ejecutar y explicar por qué.

---

## 8. Reglas de código

### 8.1 Python

- **Type hints obligatorios** en funciones públicas y métodos.
- **Docstrings estilo Google** en funciones complejas.
- **Logging estructurado** con el módulo `logging`. NO `print` para logging.
- **Configuración** desde variables de entorno con `pydantic-settings`.
- **Excepciones específicas**, no `except:` ni `except Exception:` vacío.
- **Async/await** para I/O en backend (FastAPI). Sync solo en scripts y simuladores.
- **Funciones cortas**: si supera 30 líneas, refactor.
- **Línea máxima 100 caracteres**. Formateador: `ruff format`.
- **Linter**: `ruff check`.
- **Type checker**: `mypy --strict` para módulos del monitor GSP.

### 8.2 Tests

- **Tests primero, código después** cuando sea posible.
- **Coverage mínima 80%** en `services/`.
- **Coverage mínima 90%** en `libs/urbia-graph/` y `services/monitor-gsp/` (núcleo doctoral).
- **Nombres descriptivos**: `test_<funcion>_<escenario>_<resultado_esperado>`.
- **Tests no dependen de orden** ni de estado externo.
- **Tests no requieren red en CI** salvo los marcados con `@pytest.mark.integration`.

### 8.3 Schemas y contratos

- **Schemas de datos en archivos versionados**, NO hardcoded.
- Schemas de mensajes MQTT: `services/<servicio>/SCHEMA.md` + modelos Pydantic.
- Schemas de DB: `services/backend/migrations/NNN_descripcion.sql`.
- API REST: documentada con OpenAPI (FastAPI lo genera automáticamente).

### 8.4 Configuración y secretos

- **NUNCA hardcodear** credenciales, API keys, tokens, IPs sensibles.
- Variables sensibles en `.env` (no commiteado).
- `.env.example` mantiene el template con placeholders.
- Antes de cualquier `git add`, verificar `git status` para no colar `.env`.

---

## 9. Reglas de Git

### 9.1 Commits

Formato: `tipo(scope): descripción breve`

Tipos válidos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `style`, `ci`.

Ejemplos:
- `feat(simulator-ami): publicación MQTT de telemetría AMI`
- `fix(backend): leak de conexiones a PostgreSQL`
- `docs(thesis): actualización del capítulo 3 con observaciones de Aristizábal`
- `refactor(monitor-gsp): separación entre GFT y wavelet multiescala`

### 9.2 Branches

- `main` siempre desplegable y estable.
- Ramas feature: `feature/<descripcion-corta>`.
- Ramas fix: `fix/<descripcion-corta>`.
- Ramas experimentales: `experiment/<descripcion>`.

### 9.3 Pull Requests

Aún no obligatorios (autor único). Cuando llegue colaboración:
- PR descripción explica qué cambia y por qué.
- Tests pasan en CI antes de merge.
- Squash merge a `main`.

### 9.4 Cosas que NUNCA se commitean

- `.env`
- `data-volumes/`
- `__pycache__/`, `*.pyc`
- `.venv/`, `venv/`
- `node_modules/`
- Modelos entrenados (`*.pt`, `*.pth`, `*.onnx`)
- Datasets pesados (van al NAS de .104)
- Logs (`*.log`)
- Outputs experimentales (`experiments/*/results/`)

Si Claude Code propone agregar alguno de estos al repo, rechazar.

### 9.5 Autoría de commits

Los commits hechos en este repositorio NO deben incluir la línea
`Co-Authored-By: Claude` ni atribuciones similares a agentes de IA.
La autoría intelectual y la responsabilidad del código son del autor
humano del proyecto. La asistencia de herramientas de IA se declara
en el `README.md` raíz y en la sección de metodología de la tesis,
pero no en el historial de git.

---

## 10. Reglas operativas del cluster

### 10.1 Qué se puede hacer en .102

- Crear, modificar, eliminar archivos en `~/urbIA-unal/`.
- Construir y levantar contenedores Docker del proyecto.
- Instalar paquetes Python en venvs locales.
- Crear bases de datos, schemas, tablas dentro de los contenedores UrbIA.
- Modificar configuración local de servicios UrbIA.

### 10.2 Qué NO se puede hacer sin avisar al autor

- Modificar `/etc/docker/daemon.json` u otra configuración del sistema.
- Detener o reiniciar contenedores que no sean de UrbIA (especialmente `minio_pruebas`).
- Reiniciar el daemon de Docker.
- Instalar paquetes con `apt` o `snap`.
- Modificar archivos fuera de `~/urbIA-unal/`.
- Tocar firewalld, iptables, systemd.

### 10.3 Qué NO se hace bajo ninguna circunstancia

- Conectarse por SSH a otras máquinas del cluster (.100, .101, .103, .104, .105) y modificar algo allí.
- Borrar `data-volumes/` sin confirmación explícita.
- Hacer `docker system prune` en otras máquinas.
- Forzar push (`git push --force`) sin permiso.
- Borrar branches remotos.
- Modificar `CLAUDE.md` (este archivo) sin coordinación.

### 10.4 Coordinación con servicios productivos

.101 sostiene proyectos cliente productivos (Finagro, Serviparamo, Joz, BarranquIA, ICR, Coofisam — vía contenedores Docker). Cualquier cosa que pueda afectar la red interna o el broker MQTT de .101 se conversa antes.

---

## 11. Estado actual del proyecto

### 11.1 Lo hecho

- Infraestructura del cluster Neusi documentada y saneada.
- Plan de trabajo del 28 de abril 2026 escrito.
- Decisiones de fondo cerradas: monorepo, stack tecnológico, GitHub público, Apache-2.0.
- Repositorio `urbIA-unal` creado en GitHub y clonado en .102.
- SSH key de .102 → GitHub configurada.
- Plan de implementación de la semana 1 escrito (E1-E5).

### 11.2 Lo siguiente (semana 1)

Ver `PLAN_IMPLEMENTACION_SEMANA_1.md` (si existe) o el plan equivalente. Resumen:

| Entregable | Qué | Estado |
|---|---|---|
| E1 | Stack base PostgreSQL + MongoDB + Redis + Adminer | Pendiente |
| E2 | Conectividad MQTT .102 → .101 | Pendiente |
| E3 | Simulador AMI mínimo (10 medidores, schema DLMS-JSON) | Pendiente |
| E4 | Backend FastAPI que consume MQTT y persiste a PostgreSQL | Pendiente |
| E5 | Frontend Streamlit con telemetría real | Pendiente |

### 11.3 Lo que NO está hecho todavía

- Monitor GSP (núcleo doctoral) — semana 2+.
- Controlador SDN modificado — semana 3+.
- Generador de tráfico hostil — semana 3+.
- Bring-up de la RPi5 (.106) — cuando llegue el hardware.
- Documento del anteproyecto en LaTeX — en paralelo al desarrollo.
- Experimentos comparativos — semana 4+.

### 11.4 Deuda técnica conocida

- **MQTT broker .101 en modo anónimo** (`allow_anonymous=true`). Aceptable
  mientras la red sea el cluster cerrado Neusi; **no es aceptable para
  producción**. A resolver antes de la defensa doctoral: habilitar
  autenticación con `passwd_file` + ACLs por topic. No urgente.
  Ver bloque MQTT de `.env.example` para más contexto.

---

## 12. Definición de "hecho"

Un entregable se considera completo cuando:

1. **El código está escrito y comiteado.**
2. **Los tests pasan** (`pytest` con coverage mínima).
3. **Funciona end-to-end** en el cluster con `docker compose up`.
4. **Está documentado** (al menos `README.md` del servicio).
5. **Está en GitHub** (`git push` exitoso a `origin/main`).
6. **El autor lo verificó** visualmente o por API.

Si falta cualquiera de los seis, NO está hecho.

---

## 13. Cosas específicas del autor

- Trabaja desde Bogotá (`AsusCJ`, ZSH como shell).
- Conexión a .101 vía ngrok (`4.tcp.ngrok.io -p 16657`).
- Conexión a .102 desde dentro de .101: `ssh pruebas@192.168.0.102`.
- Editor preferido: VSCode (con vscode-server en .102).
- Usa Claude Code en .102 (`/home/pruebas/.local/bin/claude`).
- Usa ChatGPT y Codex en su máquina local para tareas mecánicas.
- Tiene memoria de trabajo en español sobre el proyecto.
- Tiene Memory de Claude que recuerda detalles del proyecto entre sesiones.
- Trabaja también en el documento del anteproyecto en LaTeX (Overleaf).

---

## 14. Cómo Claude Code debe arrancar una sesión

Al iniciar una sesión nueva en este repo:

1. Leer este archivo (`CLAUDE.md`) — automático.
2. Leer `README.md` raíz si existe.
3. Verificar el estado de Git (`git status`, `git log -3`).
4. Verificar estado de Docker si aplica (`docker compose ps`).
5. Saludar brevemente y preguntar qué se va a trabajar.
6. **NO empezar a generar código** sin pregunta o instrucción.

---

## 15. Glosario rápido

| Término | Significado |
|---|---|
| AMI | Advanced Metering Infrastructure |
| GSP | Graph Signal Processing |
| GFT | Graph Fourier Transform |
| RL | Reinforcement Learning |
| SDN | Software-Defined Networking |
| QoS | Quality of Service |
| PCI | Percepción y Control Inteligente (grupo UNAL) |
| Difuminador | Componente de Aristizábal que filtra tráfico con GSP |
| Afinador | Componente de Aristizábal que ajusta τ con RL |
| Adaptador | Componente de Aristizábal que ejecuta políticas SDN |
| τ (tau) | Parámetro de difusión del filtro GSP |

---

## 16. Cuándo actualizar este archivo

Este archivo se actualiza cuando:
- Cambia un componente del stack (ADR nuevo).
- Cambia el rol asignado a una máquina del cluster.
- Cambia una regla de trabajo.
- Se completa una fase importante del proyecto.

NO se actualiza por cada commit ni por cambios menores.

---

*Última actualización: mayo 2026 — versión 1.0*
*Autor: Cristhiam Daniel Campos Julca*