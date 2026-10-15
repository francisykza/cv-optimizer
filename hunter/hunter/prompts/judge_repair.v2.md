Tu respuesta anterior no era un JSON válido con el esquema pedido.
Error encontrado: {{ERROR}}

Devuelve SOLO el objeto JSON, sin texto adicional ni bloques de código, con las claves
"match_score" (entero 0-100), "verdict" ("apply", "maybe" o "skip"), "summary",
"green_flags" y "red_flags" (listas de objetos con "text" y "evidence"), "stack_core",
"stack_inflated", "missing_must_haves" (listas de textos), "seniority_detected"
("intern", "junior", "mid", "senior", "lead" o "unknown") y "seniority_fit"
("under", "fit", "over" o "unknown").
