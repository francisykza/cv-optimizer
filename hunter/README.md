# Job Hunter

Buscador y filtrador inverso de empleo para CV-Optimizer: busca ofertas en varios portales, descarta
gratis (0 tokens) las que no encajan con tus **Reglas de Oro** y un juez IA (Groq, free tier) puntúa
las que quedan: encaje 0-100, señales a favor y en contra con su cita literal, y stack real frente a
inflado.
Funciona en tu equipo, con SQLite, sin servicios de pago. Diseño completo en [SPEC.md](SPEC.md).

**Estado:** Fases 1 (motor determinista) y 2 (juez IA). La vista "Buscador" con el botón
"Enviar al Optimizador" (Fase 3) está por llegar.

## Instalación

Python 3.12 o superior. Desde la carpeta `hunter/`:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ../backend -e ".[scrape,dev]"
.venv/Scripts/python -m hunter init
```

`init` crea `data/` (base de datos, perfil y logs, fuera del repositorio), un `.env` con el token local
y activa las reglas de [`rules.example.json`](rules.example.json). Edita `data/profile.md` con tus
habilidades reales: el pre-score las usa para ordenar las ofertas.

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
  versión del prompt. Cambiar `data/profile.md` o las prioridades sí invalida la caché.
- Antes de cada llamada se estima su coste y se espera si no cabe en el límite por minuto (que se
  ajusta con las cabeceras de Groq). Si se agota la cuota diaria o `HUNTER_DAILY_TOKEN_BUDGET`, el
  juez para limpio y lo pendiente se retoma en el siguiente run.
- Cada señal lleva una cita literal de la oferta; si la cita no aparece en el texto se marca como
  "sin cita verificable". Si el modelo no devuelve JSON válido ni tras una reparación, la oferta queda
  en `judge_failed` (`run --retry-failed` la devuelve a la cola).

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
