# Notebooks UrbIA

Exploración Jupyter del aparato matemático del monitor GSP (Graph Signal
Processing) antes de productivizarlo en `services/monitor-gsp/`.

Este directorio mantiene un entorno Python **aislado del backend**: las
dependencias de los notebooks viven en `requirements.txt` aquí mismo,
no en el `pyproject.toml` de ningún servicio.

## Inventario

| Notebook | Contenido | Entregable |
|---|---|---|
| `01_gsp_hello_world.ipynb` | Grafo de juguete (10 nodos), GFT, detector espectral simple | E6 |
| `02_grafo_ami_150.ipynb` | Grafo AMI de los 150 medidores reales: construcción, criterio de vecindad, espectro por zona y Difuminador | paso 7 |

`figures/` guarda los PNG exportados por los notebooks, para incluirlos
directamente en el documento LaTeX del anteproyecto sin recortarlos de la
salida. Los nombres siguen `NN_figM_descripcion.png`.

## Instalación local del kernel (.102)

```bash
cd ~/urbIA-unal/notebooks
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`02_grafo_ami_150.ipynb` importa además el módulo del monitor, que no está en
`requirements.txt` porque vive en el repositorio y se instala editable:

```bash
pip install -e ../services/monitor-gsp
```

No hace falta el extra `[db]`: el núcleo `urbia_monitor_gsp.graph` sólo depende
de numpy, y el notebook lee la topología del JSON versionado en vez de
consultar PostgreSQL.

## Reejecución no interactiva

Los notebooks se commitean **con sus salidas**, porque son material de
capítulo y deben leerse en GitHub sin correrlos. Para regenerarlas:

```bash
cd ~/urbIA-unal/notebooks
.venv/bin/jupyter nbconvert --to notebook --execute --inplace 02_grafo_ami_150.ipynb
```

## Levantar JupyterLab en .102

El token vive en `notebooks/.env` (NO commiteado). Plantilla en
`.env.example`.

```bash
cd ~/urbIA-unal/notebooks
source .venv/bin/activate
set -a; source .env; set +a
jupyter lab \
  --ip=0.0.0.0 \
  --port=8888 \
  --no-browser \
  --ServerApp.token="$JUPYTER_TOKEN" \
  --ServerApp.root_dir="$PWD"
```

## Acceder vía SSH tunnel desde Manjaro (.105 o local)

En la máquina cliente:

```bash
ssh -L 8888:localhost:8888 pruebas@192.168.0.102
```

Luego abrir en el navegador local:
`http://localhost:8888/?token=<JUPYTER_TOKEN>`

## Datos

`data/synthetic_meters_v1.json` — topología de juguete. NO refleja la
red eléctrica real; sirve para validar visualmente que el aparato GSP
detecta anomalías estructurales sobre un grafo arbitrario.

## Por qué un entorno separado

- El backend FastAPI tiene un perfil de dependencias acotado a
  producción (asyncio, pydantic, mqtt, etc.). Los notebooks pueden
  permitirse traer matplotlib, scipy, pandas sin contaminar el contenedor.
- Cuando un experimento del notebook se valide, se refactoriza a un
  módulo bajo `services/monitor-gsp/` con tests y type checking
  estricto. Los notebooks NO son la unidad de producción.
