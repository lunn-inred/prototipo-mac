-- Contagens de pixels por região e zona; executar somente no banco local.
BEGIN;
DO $$
BEGIN
 IF (SELECT count(*) FROM public.grupo_medida WHERE lower(trim(nome)) = 'termografia') <> 1 THEN
  RAISE EXCEPTION 'É necessário exatamente um grupo termografia';
 END IF;
END $$;
LOCK TABLE public.medida IN SHARE ROW EXCLUSIVE MODE;
INSERT INTO public.medida (nome, id_grupo_medida)
SELECT n.nome, g.id_grupo_medida
FROM public.grupo_medida g CROSS JOIN unnest(ARRAY[
 'CANELA_DIREITA_FRENTE_ZONA_FRIA',
 'CANELA_DIREITA_FRENTE_ZONA_NEUTRA',
 'CANELA_DIREITA_FRENTE_ZONA_QUENTE',
 'CANELA_DIREITA_VERSO_ZONA_FRIA',
 'CANELA_DIREITA_VERSO_ZONA_NEUTRA',
 'CANELA_DIREITA_VERSO_ZONA_QUENTE',
 'CANELA_ESQUERDA_FRENTE_ZONA_FRIA',
 'CANELA_ESQUERDA_FRENTE_ZONA_NEUTRA',
 'CANELA_ESQUERDA_FRENTE_ZONA_QUENTE',
 'CANELA_ESQUERDA_VERSO_ZONA_FRIA',
 'CANELA_ESQUERDA_VERSO_ZONA_NEUTRA',
 'CANELA_ESQUERDA_VERSO_ZONA_QUENTE',
 'COXA_DIREITA_FRENTE_ZONA_FRIA',
 'COXA_DIREITA_FRENTE_ZONA_NEUTRA',
 'COXA_DIREITA_FRENTE_ZONA_QUENTE',
 'COXA_DIREITA_VERSO_ZONA_FRIA',
 'COXA_DIREITA_VERSO_ZONA_NEUTRA',
 'COXA_DIREITA_VERSO_ZONA_QUENTE',
 'COXA_ESQUERDA_FRENTE_ZONA_FRIA',
 'COXA_ESQUERDA_FRENTE_ZONA_NEUTRA',
 'COXA_ESQUERDA_FRENTE_ZONA_QUENTE',
 'COXA_ESQUERDA_VERSO_ZONA_FRIA',
 'COXA_ESQUERDA_VERSO_ZONA_NEUTRA',
 'COXA_ESQUERDA_VERSO_ZONA_QUENTE',
 'JOELHO_DIREITA_FRENTE_ZONA_FRIA',
 'JOELHO_DIREITA_FRENTE_ZONA_NEUTRA',
 'JOELHO_DIREITA_FRENTE_ZONA_QUENTE',
 'JOELHO_DIREITA_VERSO_ZONA_FRIA',
 'JOELHO_DIREITA_VERSO_ZONA_NEUTRA',
 'JOELHO_DIREITA_VERSO_ZONA_QUENTE',
 'JOELHO_ESQUERDA_FRENTE_ZONA_FRIA',
 'JOELHO_ESQUERDA_FRENTE_ZONA_NEUTRA',
 'JOELHO_ESQUERDA_FRENTE_ZONA_QUENTE',
 'JOELHO_ESQUERDA_VERSO_ZONA_FRIA',
 'JOELHO_ESQUERDA_VERSO_ZONA_NEUTRA',
 'JOELHO_ESQUERDA_VERSO_ZONA_QUENTE',
 'PE_DIREITA_FRENTE_ZONA_FRIA',
 'PE_DIREITA_FRENTE_ZONA_NEUTRA',
 'PE_DIREITA_FRENTE_ZONA_QUENTE',
 'PE_DIREITA_VERSO_ZONA_FRIA',
 'PE_DIREITA_VERSO_ZONA_NEUTRA',
 'PE_DIREITA_VERSO_ZONA_QUENTE',
 'PE_ESQUERDA_FRENTE_ZONA_FRIA',
 'PE_ESQUERDA_FRENTE_ZONA_NEUTRA',
 'PE_ESQUERDA_FRENTE_ZONA_QUENTE',
 'PE_ESQUERDA_VERSO_ZONA_FRIA',
 'PE_ESQUERDA_VERSO_ZONA_NEUTRA',
 'PE_ESQUERDA_VERSO_ZONA_QUENTE'
]) AS n(nome)
WHERE lower(trim(g.nome)) = 'termografia'
AND NOT EXISTS (SELECT 1 FROM public.medida m WHERE m.id_grupo_medida = g.id_grupo_medida AND upper(trim(m.nome)) = n.nome);

-- View separada preserva o contrato da view histórica existente.
CREATE OR REPLACE VIEW public.vw_termografia_zonas AS
SELECT mv.id_atleta, mv.data AS data_coleta,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_DIREITA_FRENTE_ZONA_FRIA') AS canela_direita_frente_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_DIREITA_FRENTE_ZONA_NEUTRA') AS canela_direita_frente_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_DIREITA_FRENTE_ZONA_QUENTE') AS canela_direita_frente_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_DIREITA_VERSO_ZONA_FRIA') AS canela_direita_verso_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_DIREITA_VERSO_ZONA_NEUTRA') AS canela_direita_verso_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_DIREITA_VERSO_ZONA_QUENTE') AS canela_direita_verso_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_ESQUERDA_FRENTE_ZONA_FRIA') AS canela_esquerda_frente_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_ESQUERDA_FRENTE_ZONA_NEUTRA') AS canela_esquerda_frente_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_ESQUERDA_FRENTE_ZONA_QUENTE') AS canela_esquerda_frente_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_ESQUERDA_VERSO_ZONA_FRIA') AS canela_esquerda_verso_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_ESQUERDA_VERSO_ZONA_NEUTRA') AS canela_esquerda_verso_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'CANELA_ESQUERDA_VERSO_ZONA_QUENTE') AS canela_esquerda_verso_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_DIREITA_FRENTE_ZONA_FRIA') AS coxa_direita_frente_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_DIREITA_FRENTE_ZONA_NEUTRA') AS coxa_direita_frente_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_DIREITA_FRENTE_ZONA_QUENTE') AS coxa_direita_frente_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_DIREITA_VERSO_ZONA_FRIA') AS coxa_direita_verso_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_DIREITA_VERSO_ZONA_NEUTRA') AS coxa_direita_verso_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_DIREITA_VERSO_ZONA_QUENTE') AS coxa_direita_verso_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_ESQUERDA_FRENTE_ZONA_FRIA') AS coxa_esquerda_frente_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_ESQUERDA_FRENTE_ZONA_NEUTRA') AS coxa_esquerda_frente_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_ESQUERDA_FRENTE_ZONA_QUENTE') AS coxa_esquerda_frente_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_ESQUERDA_VERSO_ZONA_FRIA') AS coxa_esquerda_verso_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_ESQUERDA_VERSO_ZONA_NEUTRA') AS coxa_esquerda_verso_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'COXA_ESQUERDA_VERSO_ZONA_QUENTE') AS coxa_esquerda_verso_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_DIREITA_FRENTE_ZONA_FRIA') AS joelho_direita_frente_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_DIREITA_FRENTE_ZONA_NEUTRA') AS joelho_direita_frente_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_DIREITA_FRENTE_ZONA_QUENTE') AS joelho_direita_frente_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_DIREITA_VERSO_ZONA_FRIA') AS joelho_direita_verso_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_DIREITA_VERSO_ZONA_NEUTRA') AS joelho_direita_verso_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_DIREITA_VERSO_ZONA_QUENTE') AS joelho_direita_verso_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_ESQUERDA_FRENTE_ZONA_FRIA') AS joelho_esquerda_frente_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_ESQUERDA_FRENTE_ZONA_NEUTRA') AS joelho_esquerda_frente_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_ESQUERDA_FRENTE_ZONA_QUENTE') AS joelho_esquerda_frente_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_ESQUERDA_VERSO_ZONA_FRIA') AS joelho_esquerda_verso_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_ESQUERDA_VERSO_ZONA_NEUTRA') AS joelho_esquerda_verso_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'JOELHO_ESQUERDA_VERSO_ZONA_QUENTE') AS joelho_esquerda_verso_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_DIREITA_FRENTE_ZONA_FRIA') AS pe_direita_frente_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_DIREITA_FRENTE_ZONA_NEUTRA') AS pe_direita_frente_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_DIREITA_FRENTE_ZONA_QUENTE') AS pe_direita_frente_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_DIREITA_VERSO_ZONA_FRIA') AS pe_direita_verso_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_DIREITA_VERSO_ZONA_NEUTRA') AS pe_direita_verso_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_DIREITA_VERSO_ZONA_QUENTE') AS pe_direita_verso_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_ESQUERDA_FRENTE_ZONA_FRIA') AS pe_esquerda_frente_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_ESQUERDA_FRENTE_ZONA_NEUTRA') AS pe_esquerda_frente_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_ESQUERDA_FRENTE_ZONA_QUENTE') AS pe_esquerda_frente_zona_quente,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_ESQUERDA_VERSO_ZONA_FRIA') AS pe_esquerda_verso_zona_fria,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_ESQUERDA_VERSO_ZONA_NEUTRA') AS pe_esquerda_verso_zona_neutra,
 MAX(mv.valor) FILTER (WHERE upper(trim(m.nome)) = 'PE_ESQUERDA_VERSO_ZONA_QUENTE') AS pe_esquerda_verso_zona_quente
FROM public.medida_valor mv
JOIN public.medida m USING (id_medida)
JOIN public.grupo_medida g USING (id_grupo_medida)
WHERE lower(trim(g.nome)) = 'termografia'
GROUP BY mv.id_atleta, mv.data;
COMMIT;
