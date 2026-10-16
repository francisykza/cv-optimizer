# Job Hunter

Buscador y filtrador inverso de empleo para CV-Optimizer: busca ofertas en varios portales, descarta
gratis (0 tokens) las que no encajan con tus **Reglas de Oro** y un juez IA (Groq, free tier) puntúa
las que quedan: encaje 0-100, señales a favor y en contra con su cita literal, y stack real frente a
inflado.
Funciona en tu equipo, con SQLite, sin servicios de pago. Diseño completo en [SPEC.md](SPEC.md).

**Estado:** completo (SPEC 0.4.0): motor determinista, juez IA, API local, vista "Buscador" con el botón
"Enviar al Optimizador", acceso directo de un doble clic y seguimiento de candidaturas.

## Instalación

Python 3.12 o superior. Desde la carpeta `hunter/`:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ../backend -e ".[scrape,dev]"
.venv/Scripts/python -m hunter init
```

`init` crea la carpeta de datos (base de datos, perfil, logs y candidaturas), un `.env` con el token local
y activa las reglas de [`rules.example.json`](rules.example.json). En Windows la carpeta de datos es
`%LOCALAPPDATA%\CV-Optimizer\hunter`: fuera del repositorio y de OneDrive (en otros sistemas,
`hunter/data/`; se cambia con `HUNTER_DATA_DIR`). Edita su `profile.md` con tus habilidades reales: el
pre-score las usa para ordenar las ofertas y el juez lo lee entero.

Para el juez, pon tu clave de Groq en `hunter/.env` (`GROQ_API_KEY=...`, plantilla en
[`.env.example`](.env.example)). Sin clave, todo funciona hasta la guillotina.

El extra `scrape` instala `python-jobspy` (LinkedIn, Indeed y Google Jobs). Sin él, esas fuentes
aparecen como error y el resto (Remotive, Arbeitnow, RSS) sigue funcionando.

## Uso

```bash
python -m hunter run                         # busca, filtra y juzga
python -m hunter run --mode ingest_only      # sin juez (0 tokens)
python -m hunter run --mode judge_only       # solo la cola pendiente del juez
python -m hunter jobs --stage judged         # ranking (desde judge.min_score_to_show)
python -m hunter show 1a2b3c4d               # veredicto completo de una oferta
python -m hunter rejudge 1a2b3c4d            # volver a juzgarla sin caché
python -m hunter jobs --stage discarded      # descartadas y por qué regla
python -m hunter sources                     # estado de cada fuente (circuit breaker)
```

Cada run muestra un informe por fuente. Si un portal bloquea, esa fuente queda marcada y las demás siguen;
tras 3 fallos seguidos se pausa unas horas (el doble en cada reapertura, máximo 48 h).

### El juez y los tokens

- La misma oferta nunca se paga dos veces: el veredicto se guarda por texto de la oferta + perfil +
  versión del prompt. Cambiar `profile.md` o las prioridades sí invalida la caché.
- Antes de cada llamada se estima su coste y se espera si no cabe en el límite por minuto (que se
  ajusta con las cabeceras de Groq). Si se agota la cuota diaria o `HUNTER_DAILY_TOKEN_BUDGET`, el
  juez para limpio y lo pendiente se retoma en el siguiente run.
- Cada señal lleva una cita literal de la oferta; si la cita no aparece en el texto se marca como
  "sin cita verificable". Si el modelo no devuelve JSON válido ni tras una reparación, la oferta queda
  en `judge_failed` (`run --retry-failed` la devuelve a la cola).

## Abrirlo con un doble clic

Crea una vez el acceso directo **Buscador de empleo** en el escritorio:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\crear_acceso_directo.ps1
```

Cada doble clic (`python -m hunter open`, sin ventana de consola):

1. Arranca la API local si no está encendida.
2. Si la última búsqueda tiene más de 12 horas (`HUNTER_AUTORUN_HOURS`), lanza otra. Mientras, ves las
   ofertas que ya tenías; la vista enseña "La IA está puntuando 5 de 14" y avisa de las nuevas sin mover
   la lista.
3. Abre la web publicada (`HUNTER_WEB_URL`) en el Buscador, **ya conectada**: lleva un código de un solo
   uso que caduca a los 2 minutos, así que no hace falta copiar el token.

La API se apaga sola 30 minutos después de cerrar el Buscador (`HUNTER_IDLE_MINUTES`); también tienes el
botón "Apagar ahora". Para quitar el acceso directo, el mismo script con `-Quitar`.

## La vista Buscador

Pestañas: ranking ("Para ti"), **Candidaturas**, pendientes del juez, descartadas con su motivo y Reglas de
Oro con "Ver qué cambiaría" antes de guardar.

"Enviar al Optimizador" lleva la oferta completa al paso 2 del Optimizador, con su enlace ("Abrir la
oferta original"). Si solo tenemos un extracto, intenta leer la oferta entera; si no puede, te avisa para
que la pegues tú.

Sin el acceso directo: `.venv/Scripts/python -m hunter serve` (escucha solo en `http://127.0.0.1:8001`,
Ctrl+C para pararla) y entra en la web con `?hunter=1`; ahí puedes pegar el `HUNTER_TOKEN` de tu `.env`.
En local, `frontend/.env.local` con `VITE_HUNTER_ENABLED=true` y `npm run dev`.

## Candidaturas

Al terminar de optimizar, **Siguiente paso** te lleva a la oferta ("Abrir la oferta en linkedin.com") y
apunta la candidatura con **"Me he inscrito con este CV"**. Se guarda la compatibilidad del CV que envías
(con lo que hayas añadido), la de antes, la nota del Buscador, una copia de la oferta (los portales la borran
al cerrarla) y el CV exacto que enviaste. "Ya me he inscrito" en una ficha del Buscador también la apunta, y
las que no pasaron por aquí se añaden a mano.

En la pestaña Candidaturas cambias el estado (Enviada → En proceso → Entrevista → Oferta, Rechazada, Sin
respuesta, Retirada) y queda la fecha de cada cambio; añades notas; y ves el resumen: cuántas, esta semana,
compatibilidad media, cuántas te han respondido y si responden más cuando el CV encaja más. Las que llevan
3 semanas sin noticias se señalan. "Exportar a Excel" descarga un CSV que Excel abre directamente.

Si te inscribes con la API apagada, la candidatura espera en el navegador y se guarda sola en cuanto
vuelva. Todo vive en la carpeta de datos de tu equipo, sin copia en la nube: el CSV es tu copia de
seguridad.

## Búsquedas automáticas

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1          # 08:30 y 18:30
powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -Manana 09:00 -Tarde 19:00
powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -Quitar
```

Crea dos tareas en el Programador de tareas de Windows para tu usuario (sin ventana, sin guardar tu
contraseña). Solo se ejecutan con tu sesión iniciada. Es opcional: el acceso directo ya busca solo al
abrirlo si hace falta.

### Cambiar las Reglas de Oro

```bash
python -m hunter rules export reglas.json    # editas reglas.json
python -m hunter simulate reglas.json        # qué cambiaría (no guarda nada)
python -m hunter rules import reglas.json    # activa y re-evalúa la última semana
```

La guillotina es explicable: cada descarte guarda la regla y el fragmento que lo provocó. Ante la duda
(sin fecha, sin ciudad, sin años exigidos) la oferta **pasa**: perder una buena oferta es peor que gastar
unos tokens después.

## Tests

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/ruff check hunter tests
```

Los tests no usan la red: las fuentes y el LLM son falsos o leen `tests/fixtures/`. El golden set
(`tests/golden/offers.json`) comprueba que la guillotina no descarta ninguna oferta buena. Para
probar el juez de verdad contra Groq (gasta tokens):

```bash
HUNTER_LIVE=1 .venv/Scripts/python -m pytest -m live -s
HUNTER_LIVE=1 HUNTER_LIVE_MODEL=openai/gpt-oss-20b .venv/Scripts/python -m pytest -m live -s
```
