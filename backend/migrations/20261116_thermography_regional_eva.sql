-- Somente banco local; faça backup antes de remover o EVA geral antigo.
BEGIN;
DO $$ BEGIN
 IF to_regclass('public.vw_termografia_zonas') IS NULL THEN
  RAISE EXCEPTION 'Aplique primeiro 20261115_thermography_regional_zones.sql; nenhuma alteração de EVA foi aplicada';
 END IF;
 IF (SELECT count(*) FROM public.grupo_medida WHERE lower(trim(nome))='termografia') <> 1 THEN
  RAISE EXCEPTION 'É necessário exatamente um grupo termografia';
 END IF;
END $$;
LOCK TABLE public.medida IN SHARE ROW EXCLUSIVE MODE;
INSERT INTO public.medida(nome,id_grupo_medida)
SELECT n.nome,g.id_grupo_medida FROM public.grupo_medida g
CROSS JOIN unnest(ARRAY[
 'EVA_CANELA_DIREITA_FRENTE',
 'EVA_CANELA_DIREITA_VERSO',
 'EVA_CANELA_ESQUERDA_FRENTE',
 'EVA_CANELA_ESQUERDA_VERSO',
 'EVA_COXA_DIREITA_FRENTE',
 'EVA_COXA_DIREITA_VERSO',
 'EVA_COXA_ESQUERDA_FRENTE',
 'EVA_COXA_ESQUERDA_VERSO',
 'EVA_JOELHO_DIREITA_FRENTE',
 'EVA_JOELHO_DIREITA_VERSO',
 'EVA_JOELHO_ESQUERDA_FRENTE',
 'EVA_JOELHO_ESQUERDA_VERSO',
 'EVA_PE_DIREITA_FRENTE',
 'EVA_PE_DIREITA_VERSO',
 'EVA_PE_ESQUERDA_FRENTE',
 'EVA_PE_ESQUERDA_VERSO'
]) n(nome)
WHERE lower(trim(g.nome))='termografia'
AND NOT EXISTS (SELECT 1 FROM public.medida m WHERE m.id_grupo_medida=g.id_grupo_medida AND m.nome=n.nome);
CREATE OR REPLACE VIEW public.vw_termografia_eva_regional AS
SELECT v.id_atleta,v.data AS data_coleta,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_CANELA_DIREITA_FRENTE') AS eva_canela_direita_frente,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_CANELA_DIREITA_VERSO') AS eva_canela_direita_verso,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_CANELA_ESQUERDA_FRENTE') AS eva_canela_esquerda_frente,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_CANELA_ESQUERDA_VERSO') AS eva_canela_esquerda_verso,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_COXA_DIREITA_FRENTE') AS eva_coxa_direita_frente,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_COXA_DIREITA_VERSO') AS eva_coxa_direita_verso,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_COXA_ESQUERDA_FRENTE') AS eva_coxa_esquerda_frente,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_COXA_ESQUERDA_VERSO') AS eva_coxa_esquerda_verso,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_JOELHO_DIREITA_FRENTE') AS eva_joelho_direita_frente,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_JOELHO_DIREITA_VERSO') AS eva_joelho_direita_verso,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_JOELHO_ESQUERDA_FRENTE') AS eva_joelho_esquerda_frente,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_JOELHO_ESQUERDA_VERSO') AS eva_joelho_esquerda_verso,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_PE_DIREITA_FRENTE') AS eva_pe_direita_frente,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_PE_DIREITA_VERSO') AS eva_pe_direita_verso,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_PE_ESQUERDA_FRENTE') AS eva_pe_esquerda_frente,
 MAX(v.valor) FILTER (WHERE m.nome = 'EVA_PE_ESQUERDA_VERSO') AS eva_pe_esquerda_verso
FROM public.medida_valor v JOIN public.medida m USING(id_medida)
JOIN public.grupo_medida g USING(id_grupo_medida)
WHERE lower(trim(g.nome))='termografia' AND m.nome IN (
 'EVA_CANELA_DIREITA_FRENTE',
 'EVA_CANELA_DIREITA_VERSO',
 'EVA_CANELA_ESQUERDA_FRENTE',
 'EVA_CANELA_ESQUERDA_VERSO',
 'EVA_COXA_DIREITA_FRENTE',
 'EVA_COXA_DIREITA_VERSO',
 'EVA_COXA_ESQUERDA_FRENTE',
 'EVA_COXA_ESQUERDA_VERSO',
 'EVA_JOELHO_DIREITA_FRENTE',
 'EVA_JOELHO_DIREITA_VERSO',
 'EVA_JOELHO_ESQUERDA_FRENTE',
 'EVA_JOELHO_ESQUERDA_VERSO',
 'EVA_PE_DIREITA_FRENTE',
 'EVA_PE_DIREITA_VERSO',
 'EVA_PE_ESQUERDA_FRENTE',
 'EVA_PE_ESQUERDA_VERSO'
)
GROUP BY v.id_atleta,v.data;
CREATE OR REPLACE VIEW public.vw_medida_termografia AS
SELECT a.id_atleta,a.nome AS jogador,a.posicao,a.grupo,v.data AS data_coleta,
 MAX(v.valor) FILTER (WHERE upper(trim(m.nome))='MASSA') AS massa,
 MAX(v.valor) FILTER (WHERE m.nome IN (
 'EVA_CANELA_DIREITA_FRENTE',
 'EVA_CANELA_DIREITA_VERSO',
 'EVA_CANELA_ESQUERDA_FRENTE',
 'EVA_CANELA_ESQUERDA_VERSO',
 'EVA_COXA_DIREITA_FRENTE',
 'EVA_COXA_DIREITA_VERSO',
 'EVA_COXA_ESQUERDA_FRENTE',
 'EVA_COXA_ESQUERDA_VERSO',
 'EVA_JOELHO_DIREITA_FRENTE',
 'EVA_JOELHO_DIREITA_VERSO',
 'EVA_JOELHO_ESQUERDA_FRENTE',
 'EVA_JOELHO_ESQUERDA_VERSO',
 'EVA_PE_DIREITA_FRENTE',
 'EVA_PE_DIREITA_VERSO',
 'EVA_PE_ESQUERDA_FRENTE',
 'EVA_PE_ESQUERDA_VERSO'
 )) AS eva_dor,
 MAX(v.valor) FILTER (WHERE upper(trim(m.nome))='SOMA_FRENTE') AS frente,
 MAX(v.valor) FILTER (WHERE upper(trim(m.nome))='SOMA_VERSO') AS verso,
 MAX(v.valor_texto) FILTER (WHERE upper(trim(m.nome))='OBSERVACOES') AS observacoes
FROM public.medida_valor v JOIN public.atleta a USING(id_atleta)
JOIN public.medida m USING(id_medida) JOIN public.grupo_medida g USING(id_grupo_medida)
WHERE lower(trim(g.nome))='termografia'
GROUP BY a.id_atleta,a.nome,a.posicao,a.grupo,v.data;
DELETE FROM public.medida_valor v USING public.medida m,public.grupo_medida g
WHERE v.id_medida=m.id_medida AND m.id_grupo_medida=g.id_grupo_medida
AND lower(trim(g.nome))='termografia' AND upper(trim(m.nome))='EVA_DOR';
DELETE FROM public.medida m USING public.grupo_medida g
WHERE m.id_grupo_medida=g.id_grupo_medida AND lower(trim(g.nome))='termografia'
AND upper(trim(m.nome))='EVA_DOR';
COMMIT;
