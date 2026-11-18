-- Preferência por atleta; o UUID identifica a análise nos arquivos da timeline.
CREATE TABLE IF NOT EXISTS public.termografia_basal (
    id_atleta integer PRIMARY KEY REFERENCES public.atleta(id_atleta),
    analysis_id uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
