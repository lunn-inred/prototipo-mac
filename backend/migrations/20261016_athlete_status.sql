-- Status pertence ao cadastro, não ao conjunto de medições do atleta.
-- Não apaga atletas nem modifica as medições existentes.
ALTER TABLE public.atleta
    ADD COLUMN status text NOT NULL DEFAULT 'ativo'
    CONSTRAINT atleta_status_check CHECK (status IN ('ativo', 'inativo'));
