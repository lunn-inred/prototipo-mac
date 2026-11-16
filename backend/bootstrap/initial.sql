-- Base de instalação: somente estrutura e catálogo técnico; sem dados pessoais.
--
-- PostgreSQL database dump
--


-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--



--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: atleta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.atleta (
    id_atleta integer NOT NULL,
    nome text,
    apelido text,
    nome_alternativo text,
    posicao text,
    grupo text,
    data_nascimento timestamp without time zone,
    status text DEFAULT 'ativo'::text NOT NULL,
    CONSTRAINT atleta_status_check CHECK ((status = ANY (ARRAY['ativo'::text, 'inativo'::text])))
);


--
-- Name: atleta_id_atleta_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.atleta_id_atleta_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: atleta_id_atleta_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.atleta_id_atleta_seq OWNED BY public.atleta.id_atleta;


--
-- Name: grupo_medida; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grupo_medida (
    id_grupo_medida integer NOT NULL,
    nome text
);


--
-- Name: grupo_medida_id_grupo_medida_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.grupo_medida_id_grupo_medida_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: grupo_medida_id_grupo_medida_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.grupo_medida_id_grupo_medida_seq OWNED BY public.grupo_medida.id_grupo_medida;


--
-- Name: medida; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medida (
    id_medida integer NOT NULL,
    id_grupo_medida integer,
    nome text
);


--
-- Name: medida_id_medida_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.medida_id_medida_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: medida_id_medida_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.medida_id_medida_seq OWNED BY public.medida.id_medida;


--
-- Name: medida_valor; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medida_valor (
    id_medida_valor integer NOT NULL,
    id_atleta integer,
    id_partida integer,
    id_medida integer,
    valor double precision,
    valor_texto text,
    data timestamp without time zone
);


--
-- Name: medida_valor_id_medida_valor_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.medida_valor_id_medida_valor_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: medida_valor_id_medida_valor_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.medida_valor_id_medida_valor_seq OWNED BY public.medida_valor.id_medida_valor;


--
-- Name: partida; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.partida (
    id_partida integer NOT NULL,
    data timestamp without time zone,
    duracao double precision,
    equipe text,
    adversario text
);


--
-- Name: partida_id_partida_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.partida_id_partida_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: partida_id_partida_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.partida_id_partida_seq OWNED BY public.partida.id_partida;


--
-- Name: usuario; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usuario (
    id_usuario integer NOT NULL,
    nome text,
    senha text,
    funcao text
);


--
-- Name: usuario_id_usuario_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.usuario_id_usuario_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: usuario_id_usuario_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.usuario_id_usuario_seq OWNED BY public.usuario.id_usuario;


--
-- Name: vw_medida_termografia; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_medida_termografia AS
 SELECT a.id_atleta,
    a.nome AS jogador,
    a.posicao,
    a.grupo,
    v.data AS data_coleta,
    max(v.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'MASSA'::text)) AS massa,
    max(v.valor) FILTER (WHERE (m.nome = ANY (ARRAY['EVA_CANELA_DIREITA_FRENTE'::text, 'EVA_CANELA_DIREITA_VERSO'::text, 'EVA_CANELA_ESQUERDA_FRENTE'::text, 'EVA_CANELA_ESQUERDA_VERSO'::text, 'EVA_COXA_DIREITA_FRENTE'::text, 'EVA_COXA_DIREITA_VERSO'::text, 'EVA_COXA_ESQUERDA_FRENTE'::text, 'EVA_COXA_ESQUERDA_VERSO'::text, 'EVA_JOELHO_DIREITA_FRENTE'::text, 'EVA_JOELHO_DIREITA_VERSO'::text, 'EVA_JOELHO_ESQUERDA_FRENTE'::text, 'EVA_JOELHO_ESQUERDA_VERSO'::text, 'EVA_PE_DIREITA_FRENTE'::text, 'EVA_PE_DIREITA_VERSO'::text, 'EVA_PE_ESQUERDA_FRENTE'::text, 'EVA_PE_ESQUERDA_VERSO'::text]))) AS eva_dor,
    max(v.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'SOMA_FRENTE'::text)) AS frente,
    max(v.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'SOMA_VERSO'::text)) AS verso,
    max(v.valor_texto) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'OBSERVACOES'::text)) AS observacoes
   FROM (((public.medida_valor v
     JOIN public.atleta a USING (id_atleta))
     JOIN public.medida m USING (id_medida))
     JOIN public.grupo_medida g USING (id_grupo_medida))
  WHERE (lower(TRIM(BOTH FROM g.nome)) = 'termografia'::text)
  GROUP BY a.id_atleta, a.nome, a.posicao, a.grupo, v.data;


--
-- Name: vw_medidas_atletas_completa; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_medidas_atletas_completa AS
 SELECT a.nome AS atleta,
    a.posicao,
    a.grupo,
    mv.data AS data_coleta,
    p.equipe,
    p.adversario,
    gm.nome AS categoria_medida,
    max(
        CASE
            WHEN (m.nome = 'Accel&De-cel Efforts'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS accel_de_cel_efforts,
    max(
        CASE
            WHEN (m.nome = 'Accel&De-cel Efforts Per Minute'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS accel_de_cel_efforts_per_minute,
    max(
        CASE
            WHEN (m.nome = 'CMJ1'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS cmj1,
    max(
        CASE
            WHEN (m.nome = 'CMJ2'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS cmj2,
    max(
        CASE
            WHEN (m.nome = 'CMJ3'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS cmj3,
    max(
        CASE
            WHEN (m.nome = 'Distance (km)'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS distance_km,
    max(
        CASE
            WHEN (m.nome = 'High Speed Distance'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS high_speed_distance,
    max(
        CASE
            WHEN (m.nome = 'High Speed Efforts'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS high_speed_efforts,
    max(
        CASE
            WHEN (m.nome = 'MAIOR_CMJ'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS maior_cmj,
    max(
        CASE
            WHEN (m.nome = 'MAIOR_SJ'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS maior_sj,
    max(
        CASE
            WHEN (m.nome = 'Max Acceleration'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS max_acceleration,
    max(
        CASE
            WHEN (m.nome = 'Max Deceleration'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS max_deceleration,
    max(
        CASE
            WHEN (m.nome = 'Maximum Velocity (km/h)'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS maximum_velocity_km_h,
    max(
        CASE
            WHEN (m.nome = 'Meterage Per Minute'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS meterage_per_minute,
    max(
        CASE
            WHEN (m.nome = 'Player Load Per Minute'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS player_load_per_minute,
    max(
        CASE
            WHEN (m.nome = 'SJ'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj,
    max(
        CASE
            WHEN (m.nome = 'SJ.1'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj_1,
    max(
        CASE
            WHEN (m.nome = 'SJ.2'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj_2,
    max(
        CASE
            WHEN (m.nome = 'SJ1'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj1,
    max(
        CASE
            WHEN (m.nome = 'SJ2'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj2,
    max(
        CASE
            WHEN (m.nome = 'SJ3'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj3,
    max(
        CASE
            WHEN (m.nome = 'Sprint Efforts'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sprint_efforts
   FROM ((((public.medida_valor mv
     JOIN public.atleta a ON ((mv.id_atleta = a.id_atleta)))
     JOIN public.medida m ON ((mv.id_medida = m.id_medida)))
     LEFT JOIN public.grupo_medida gm ON ((m.id_grupo_medida = gm.id_grupo_medida)))
     LEFT JOIN public.partida p ON ((mv.id_partida = p.id_partida)))
  GROUP BY a.id_atleta, a.nome, a.posicao, a.grupo, mv.data, p.equipe, p.adversario, gm.nome;


--
-- Name: vw_medidas_gps; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_medidas_gps AS
 SELECT a.nome AS atleta,
    a.posicao,
    a.grupo,
    mv.data AS data_coleta,
    p.equipe,
    p.adversario,
    max(
        CASE
            WHEN (m.nome = 'Accel&De-cel Efforts'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS accel_de_cel_efforts,
    max(
        CASE
            WHEN (m.nome = 'Accel&De-cel Efforts Per Minute'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS accel_de_cel_efforts_per_minute,
    max(
        CASE
            WHEN (m.nome = 'Distance (km)'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS distance_km,
    max(
        CASE
            WHEN (m.nome = 'High Speed Distance'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS high_speed_distance,
    max(
        CASE
            WHEN (m.nome = 'High Speed Efforts'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS high_speed_efforts,
    max(
        CASE
            WHEN (m.nome = 'Max Acceleration'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS max_acceleration,
    max(
        CASE
            WHEN (m.nome = 'Max Deceleration'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS max_deceleration,
    max(
        CASE
            WHEN (m.nome = 'Maximum Velocity (km/h)'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS maximum_velocity_km_h,
    max(
        CASE
            WHEN (m.nome = 'Meterage Per Minute'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS meterage_per_minute,
    max(
        CASE
            WHEN (m.nome = 'Player Load Per Minute'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS player_load_per_minute,
    max(
        CASE
            WHEN (m.nome = 'Sprint Efforts'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sprint_efforts
   FROM (((public.medida_valor mv
     JOIN public.atleta a ON ((mv.id_atleta = a.id_atleta)))
     JOIN public.medida m ON ((mv.id_medida = m.id_medida)))
     LEFT JOIN public.partida p ON ((mv.id_partida = p.id_partida)))
  WHERE (m.id_grupo_medida = 2)
  GROUP BY a.id_atleta, a.nome, a.posicao, a.grupo, mv.data, p.equipe, p.adversario;


--
-- Name: vw_medidas_saltos; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_medidas_saltos AS
 SELECT a.nome AS atleta,
    a.posicao,
    a.grupo,
    mv.data AS data_coleta,
    max(
        CASE
            WHEN (m.nome = 'CMJ1'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS cmj1,
    max(
        CASE
            WHEN (m.nome = 'CMJ2'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS cmj2,
    max(
        CASE
            WHEN (m.nome = 'CMJ3'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS cmj3,
    max(
        CASE
            WHEN (m.nome = 'MAIOR_CMJ'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS maior_cmj,
    max(
        CASE
            WHEN (m.nome = 'MAIOR_SJ'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS maior_sj,
    max(
        CASE
            WHEN (m.nome = 'SJ'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj,
    max(
        CASE
            WHEN (m.nome = 'SJ.1'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj_1,
    max(
        CASE
            WHEN (m.nome = 'SJ.2'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj_2,
    max(
        CASE
            WHEN (m.nome = 'SJ1'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj1,
    max(
        CASE
            WHEN (m.nome = 'SJ2'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj2,
    max(
        CASE
            WHEN (m.nome = 'SJ3'::text) THEN mv.valor
            ELSE NULL::double precision
        END) AS sj3
   FROM (((public.medida_valor mv
     JOIN public.atleta a ON ((mv.id_atleta = a.id_atleta)))
     JOIN public.medida m ON ((mv.id_medida = m.id_medida)))
     LEFT JOIN public.partida p ON ((mv.id_partida = p.id_partida)))
  WHERE (m.id_grupo_medida = 1)
  GROUP BY a.id_atleta, a.nome, a.posicao, a.grupo, mv.data, p.equipe, p.adversario;


--
-- Name: vw_termografia_eva_regional; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_termografia_eva_regional AS
 SELECT v.id_atleta,
    v.data AS data_coleta,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_CANELA_DIREITA_FRENTE'::text)) AS eva_canela_direita_frente,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_CANELA_DIREITA_VERSO'::text)) AS eva_canela_direita_verso,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_CANELA_ESQUERDA_FRENTE'::text)) AS eva_canela_esquerda_frente,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_CANELA_ESQUERDA_VERSO'::text)) AS eva_canela_esquerda_verso,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_COXA_DIREITA_FRENTE'::text)) AS eva_coxa_direita_frente,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_COXA_DIREITA_VERSO'::text)) AS eva_coxa_direita_verso,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_COXA_ESQUERDA_FRENTE'::text)) AS eva_coxa_esquerda_frente,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_COXA_ESQUERDA_VERSO'::text)) AS eva_coxa_esquerda_verso,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_JOELHO_DIREITA_FRENTE'::text)) AS eva_joelho_direita_frente,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_JOELHO_DIREITA_VERSO'::text)) AS eva_joelho_direita_verso,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_JOELHO_ESQUERDA_FRENTE'::text)) AS eva_joelho_esquerda_frente,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_JOELHO_ESQUERDA_VERSO'::text)) AS eva_joelho_esquerda_verso,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_PE_DIREITA_FRENTE'::text)) AS eva_pe_direita_frente,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_PE_DIREITA_VERSO'::text)) AS eva_pe_direita_verso,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_PE_ESQUERDA_FRENTE'::text)) AS eva_pe_esquerda_frente,
    max(v.valor) FILTER (WHERE (m.nome = 'EVA_PE_ESQUERDA_VERSO'::text)) AS eva_pe_esquerda_verso
   FROM ((public.medida_valor v
     JOIN public.medida m USING (id_medida))
     JOIN public.grupo_medida g USING (id_grupo_medida))
  WHERE ((lower(TRIM(BOTH FROM g.nome)) = 'termografia'::text) AND (m.nome = ANY (ARRAY['EVA_CANELA_DIREITA_FRENTE'::text, 'EVA_CANELA_DIREITA_VERSO'::text, 'EVA_CANELA_ESQUERDA_FRENTE'::text, 'EVA_CANELA_ESQUERDA_VERSO'::text, 'EVA_COXA_DIREITA_FRENTE'::text, 'EVA_COXA_DIREITA_VERSO'::text, 'EVA_COXA_ESQUERDA_FRENTE'::text, 'EVA_COXA_ESQUERDA_VERSO'::text, 'EVA_JOELHO_DIREITA_FRENTE'::text, 'EVA_JOELHO_DIREITA_VERSO'::text, 'EVA_JOELHO_ESQUERDA_FRENTE'::text, 'EVA_JOELHO_ESQUERDA_VERSO'::text, 'EVA_PE_DIREITA_FRENTE'::text, 'EVA_PE_DIREITA_VERSO'::text, 'EVA_PE_ESQUERDA_FRENTE'::text, 'EVA_PE_ESQUERDA_VERSO'::text])))
  GROUP BY v.id_atleta, v.data;


--
-- Name: vw_termografia_zonas; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_termografia_zonas AS
 SELECT mv.id_atleta,
    mv.data AS data_coleta,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_DIREITA_FRENTE_ZONA_FRIA'::text)) AS canela_direita_frente_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_DIREITA_FRENTE_ZONA_NEUTRA'::text)) AS canela_direita_frente_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_DIREITA_FRENTE_ZONA_QUENTE'::text)) AS canela_direita_frente_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_DIREITA_VERSO_ZONA_FRIA'::text)) AS canela_direita_verso_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_DIREITA_VERSO_ZONA_NEUTRA'::text)) AS canela_direita_verso_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_DIREITA_VERSO_ZONA_QUENTE'::text)) AS canela_direita_verso_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_ESQUERDA_FRENTE_ZONA_FRIA'::text)) AS canela_esquerda_frente_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_ESQUERDA_FRENTE_ZONA_NEUTRA'::text)) AS canela_esquerda_frente_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_ESQUERDA_FRENTE_ZONA_QUENTE'::text)) AS canela_esquerda_frente_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_ESQUERDA_VERSO_ZONA_FRIA'::text)) AS canela_esquerda_verso_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_ESQUERDA_VERSO_ZONA_NEUTRA'::text)) AS canela_esquerda_verso_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'CANELA_ESQUERDA_VERSO_ZONA_QUENTE'::text)) AS canela_esquerda_verso_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_DIREITA_FRENTE_ZONA_FRIA'::text)) AS coxa_direita_frente_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_DIREITA_FRENTE_ZONA_NEUTRA'::text)) AS coxa_direita_frente_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_DIREITA_FRENTE_ZONA_QUENTE'::text)) AS coxa_direita_frente_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_DIREITA_VERSO_ZONA_FRIA'::text)) AS coxa_direita_verso_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_DIREITA_VERSO_ZONA_NEUTRA'::text)) AS coxa_direita_verso_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_DIREITA_VERSO_ZONA_QUENTE'::text)) AS coxa_direita_verso_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_ESQUERDA_FRENTE_ZONA_FRIA'::text)) AS coxa_esquerda_frente_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_ESQUERDA_FRENTE_ZONA_NEUTRA'::text)) AS coxa_esquerda_frente_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_ESQUERDA_FRENTE_ZONA_QUENTE'::text)) AS coxa_esquerda_frente_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_ESQUERDA_VERSO_ZONA_FRIA'::text)) AS coxa_esquerda_verso_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_ESQUERDA_VERSO_ZONA_NEUTRA'::text)) AS coxa_esquerda_verso_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'COXA_ESQUERDA_VERSO_ZONA_QUENTE'::text)) AS coxa_esquerda_verso_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_DIREITA_FRENTE_ZONA_FRIA'::text)) AS joelho_direita_frente_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_DIREITA_FRENTE_ZONA_NEUTRA'::text)) AS joelho_direita_frente_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_DIREITA_FRENTE_ZONA_QUENTE'::text)) AS joelho_direita_frente_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_DIREITA_VERSO_ZONA_FRIA'::text)) AS joelho_direita_verso_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_DIREITA_VERSO_ZONA_NEUTRA'::text)) AS joelho_direita_verso_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_DIREITA_VERSO_ZONA_QUENTE'::text)) AS joelho_direita_verso_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_ESQUERDA_FRENTE_ZONA_FRIA'::text)) AS joelho_esquerda_frente_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_ESQUERDA_FRENTE_ZONA_NEUTRA'::text)) AS joelho_esquerda_frente_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_ESQUERDA_FRENTE_ZONA_QUENTE'::text)) AS joelho_esquerda_frente_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_ESQUERDA_VERSO_ZONA_FRIA'::text)) AS joelho_esquerda_verso_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_ESQUERDA_VERSO_ZONA_NEUTRA'::text)) AS joelho_esquerda_verso_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'JOELHO_ESQUERDA_VERSO_ZONA_QUENTE'::text)) AS joelho_esquerda_verso_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_DIREITA_FRENTE_ZONA_FRIA'::text)) AS pe_direita_frente_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_DIREITA_FRENTE_ZONA_NEUTRA'::text)) AS pe_direita_frente_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_DIREITA_FRENTE_ZONA_QUENTE'::text)) AS pe_direita_frente_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_DIREITA_VERSO_ZONA_FRIA'::text)) AS pe_direita_verso_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_DIREITA_VERSO_ZONA_NEUTRA'::text)) AS pe_direita_verso_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_DIREITA_VERSO_ZONA_QUENTE'::text)) AS pe_direita_verso_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_ESQUERDA_FRENTE_ZONA_FRIA'::text)) AS pe_esquerda_frente_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_ESQUERDA_FRENTE_ZONA_NEUTRA'::text)) AS pe_esquerda_frente_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_ESQUERDA_FRENTE_ZONA_QUENTE'::text)) AS pe_esquerda_frente_zona_quente,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_ESQUERDA_VERSO_ZONA_FRIA'::text)) AS pe_esquerda_verso_zona_fria,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_ESQUERDA_VERSO_ZONA_NEUTRA'::text)) AS pe_esquerda_verso_zona_neutra,
    max(mv.valor) FILTER (WHERE (upper(TRIM(BOTH FROM m.nome)) = 'PE_ESQUERDA_VERSO_ZONA_QUENTE'::text)) AS pe_esquerda_verso_zona_quente
   FROM ((public.medida_valor mv
     JOIN public.medida m USING (id_medida))
     JOIN public.grupo_medida g USING (id_grupo_medida))
  WHERE (lower(TRIM(BOTH FROM g.nome)) = 'termografia'::text)
  GROUP BY mv.id_atleta, mv.data;


--
-- Name: atleta id_atleta; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.atleta ALTER COLUMN id_atleta SET DEFAULT nextval('public.atleta_id_atleta_seq'::regclass);


--
-- Name: grupo_medida id_grupo_medida; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupo_medida ALTER COLUMN id_grupo_medida SET DEFAULT nextval('public.grupo_medida_id_grupo_medida_seq'::regclass);


--
-- Name: medida id_medida; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medida ALTER COLUMN id_medida SET DEFAULT nextval('public.medida_id_medida_seq'::regclass);


--
-- Name: medida_valor id_medida_valor; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medida_valor ALTER COLUMN id_medida_valor SET DEFAULT nextval('public.medida_valor_id_medida_valor_seq'::regclass);


--
-- Name: partida id_partida; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.partida ALTER COLUMN id_partida SET DEFAULT nextval('public.partida_id_partida_seq'::regclass);


--
-- Name: usuario id_usuario; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuario ALTER COLUMN id_usuario SET DEFAULT nextval('public.usuario_id_usuario_seq'::regclass);


--
-- Name: atleta atleta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.atleta
    ADD CONSTRAINT atleta_pkey PRIMARY KEY (id_atleta);


--
-- Name: grupo_medida grupo_medida_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupo_medida
    ADD CONSTRAINT grupo_medida_pkey PRIMARY KEY (id_grupo_medida);


--
-- Name: medida medida_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medida
    ADD CONSTRAINT medida_pkey PRIMARY KEY (id_medida);


--
-- Name: medida_valor medida_valor_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medida_valor
    ADD CONSTRAINT medida_valor_pkey PRIMARY KEY (id_medida_valor);


--
-- Name: partida partida_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.partida
    ADD CONSTRAINT partida_pkey PRIMARY KEY (id_partida);


--
-- Name: usuario usuario_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuario
    ADD CONSTRAINT usuario_pkey PRIMARY KEY (id_usuario);


--
-- Name: medida medida_grupo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medida
    ADD CONSTRAINT medida_grupo FOREIGN KEY (id_grupo_medida) REFERENCES public.grupo_medida(id_grupo_medida) DEFERRABLE;


--
-- Name: medida_valor medida_valor_atleta; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medida_valor
    ADD CONSTRAINT medida_valor_atleta FOREIGN KEY (id_atleta) REFERENCES public.atleta(id_atleta) DEFERRABLE;


--
-- Name: medida_valor medida_valor_medida; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medida_valor
    ADD CONSTRAINT medida_valor_medida FOREIGN KEY (id_medida) REFERENCES public.medida(id_medida) DEFERRABLE;


--
-- Name: medida_valor medida_valor_partida; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medida_valor
    ADD CONSTRAINT medida_valor_partida FOREIGN KEY (id_partida) REFERENCES public.partida(id_partida) DEFERRABLE;


--
-- PostgreSQL database dump complete
--


INSERT INTO public.grupo_medida(id_grupo_medida,nome) VALUES(1,'Saltos');
INSERT INTO public.grupo_medida(id_grupo_medida,nome) VALUES(2,'GPS');
INSERT INTO public.grupo_medida(id_grupo_medida,nome) VALUES(3,'Termografia');
SELECT setval(pg_get_serial_sequence('public.grupo_medida','id_grupo_medida'), (SELECT max(id_grupo_medida) FROM public.grupo_medida), true);
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(1,1,'CMJ1');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(2,1,'CMJ2');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(3,1,'CMJ3');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(4,1,'MAIOR_CMJ');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(5,1,'SJ1');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(6,1,'SJ2');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(7,1,'SJ3');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(8,1,'MAIOR_SJ');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(12,2,'Distance (km)');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(13,2,'Meterage Per Minute');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(14,2,'High Speed Distance');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(15,2,'High Speed Efforts');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(16,2,'Sprint Efforts');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(17,2,'Maximum Velocity (km/h)');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(18,2,'Player Load Per Minute');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(19,2,'Accel&De-cel Efforts');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(20,2,'Accel&De-cel Efforts Per Minute');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(21,2,'Max Acceleration');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(22,2,'Max Deceleration');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(23,1,'media_cmj');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(24,1,'Média CMJ');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(25,3,'MASSA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(29,3,'OBSERVACOES');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(30,3,'PERNA_DIREITA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(31,3,'PERNA_DIREITA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(32,3,'PERNA_ESQUERDA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(33,3,'PERNA_ESQUERDA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(34,3,'SOMA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(35,3,'SOMA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(36,3,'EVA_COXA_ESQUERDA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(37,3,'EVA_JOELHO_ESQUERDA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(38,3,'EVA_JOELHO_DIREITA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(39,3,'EVA_CANELA_ESQUERDA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(40,3,'EVA_COXA_DIREITA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(41,3,'EVA_COXA_DIREITA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(42,3,'EVA_CANELA_DIREITA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(43,3,'EVA_CANELA_DIREITA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(44,3,'EVA_JOELHO_DIREITA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(45,3,'EVA_PE_ESQUERDA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(46,3,'EVA_CANELA_ESQUERDA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(47,3,'EVA_PE_DIREITA_VERSO');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(48,3,'EVA_COXA_ESQUERDA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(49,3,'EVA_PE_DIREITA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(50,3,'EVA_PE_ESQUERDA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(51,3,'EVA_JOELHO_ESQUERDA_FRENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(52,3,'CANELA_DIREITA_FRENTE_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(53,3,'CANELA_DIREITA_FRENTE_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(54,3,'CANELA_DIREITA_FRENTE_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(55,3,'CANELA_DIREITA_VERSO_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(56,3,'CANELA_DIREITA_VERSO_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(57,3,'CANELA_DIREITA_VERSO_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(58,3,'CANELA_ESQUERDA_FRENTE_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(59,3,'CANELA_ESQUERDA_FRENTE_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(60,3,'CANELA_ESQUERDA_FRENTE_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(61,3,'CANELA_ESQUERDA_VERSO_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(62,3,'CANELA_ESQUERDA_VERSO_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(63,3,'CANELA_ESQUERDA_VERSO_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(64,3,'COXA_DIREITA_FRENTE_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(65,3,'COXA_DIREITA_FRENTE_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(66,3,'COXA_DIREITA_FRENTE_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(67,3,'COXA_DIREITA_VERSO_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(68,3,'COXA_DIREITA_VERSO_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(69,3,'COXA_DIREITA_VERSO_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(70,3,'COXA_ESQUERDA_FRENTE_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(71,3,'COXA_ESQUERDA_FRENTE_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(72,3,'COXA_ESQUERDA_FRENTE_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(73,3,'COXA_ESQUERDA_VERSO_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(74,3,'COXA_ESQUERDA_VERSO_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(75,3,'COXA_ESQUERDA_VERSO_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(76,3,'JOELHO_DIREITA_FRENTE_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(77,3,'JOELHO_DIREITA_FRENTE_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(78,3,'JOELHO_DIREITA_FRENTE_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(79,3,'JOELHO_DIREITA_VERSO_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(80,3,'JOELHO_DIREITA_VERSO_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(81,3,'JOELHO_DIREITA_VERSO_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(82,3,'JOELHO_ESQUERDA_FRENTE_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(83,3,'JOELHO_ESQUERDA_FRENTE_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(84,3,'JOELHO_ESQUERDA_FRENTE_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(85,3,'JOELHO_ESQUERDA_VERSO_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(86,3,'JOELHO_ESQUERDA_VERSO_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(87,3,'JOELHO_ESQUERDA_VERSO_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(88,3,'PE_DIREITA_FRENTE_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(89,3,'PE_DIREITA_FRENTE_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(90,3,'PE_DIREITA_FRENTE_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(91,3,'PE_DIREITA_VERSO_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(92,3,'PE_DIREITA_VERSO_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(93,3,'PE_DIREITA_VERSO_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(94,3,'PE_ESQUERDA_FRENTE_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(95,3,'PE_ESQUERDA_FRENTE_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(96,3,'PE_ESQUERDA_FRENTE_ZONA_QUENTE');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(97,3,'PE_ESQUERDA_VERSO_ZONA_FRIA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(98,3,'PE_ESQUERDA_VERSO_ZONA_NEUTRA');
INSERT INTO public.medida(id_medida,id_grupo_medida,nome) VALUES(99,3,'PE_ESQUERDA_VERSO_ZONA_QUENTE');
SELECT setval(pg_get_serial_sequence('public.medida','id_medida'), (SELECT max(id_medida) FROM public.medida), true);
