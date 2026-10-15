# Job Hunter

Buscador y filtrador inverso de empleo para CV-Optimizer: busca ofertas en varios portales, descarta
gratis (0 tokens) las que no encajan con tus **Reglas de Oro** y deja el resto listo para el juez IA.
Funciona en tu equipo, con SQLite, sin servicios de pago. Diseño completo en [SPEC.md](SPEC.md).

**Estado:** Fase 1 (motor determinista). El juez IA (Fase 2) y la vista "Buscador" con el botón
"Enviar al Optimizador" (Fase 3) están por llegar.

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

El extra `scrape` instala `python-jobspy` (LinkedIn, Indeed y Google Jobs). Sin él, esas fuentes
aparecen como error y el resto (Remotive, Arbeitnow, RSS) sigue funcionando.

## Uso

```bash
python -m hunter run                         # busca y filtra
python -m hunter run --only indeed remotive  # solo algunas fuentes
python -m hunter jobs                        # pendientes del juez, por pre-score
python -m hunter jobs --stage discarded      # descartadas y por qué regla
python -m hunter sources                     # estado de cada fuente (circuit breaker)
```

Cada run muestra un informe por fuente. Si un portal bloquea, esa fuente queda marcada y las demás siguen;
tras 3 fallos seguidos se pausa unas horas (el doble en cada reapertura, máximo 48 h).

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

Los tests no usan la red: las fuentes son falsas o leen `tests/fixtures/`.
