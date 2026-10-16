-- El ranking pasa a ordenarse por la nota del juez, con el pre-score solo como desempate
-- (ver judge/schema.py: rank_score). Recalcula las ofertas ya juzgadas.
UPDATE jobs
SET rank_score = (
  SELECT json_extract(v.verdict_json, '$.match_score') FROM verdicts v
  WHERE v.cache_key = jobs.verdict_key AND v.status = 'ok'
) + prescore / 1000.0
WHERE stage = 'judged' AND verdict_key IS NOT NULL;
