# Protótipo — MAC Performance

Protótipo em Streamlit para estudar a lógica de visualização e cálculo das
métricas de desempenho do MAC. O projeto possui páginas de monitoramento de
saltos e GPS e utiliza Plotly para a construção dos gráficos.

## Sumário

- [Como executar](#como-executar)
- [Monitoramento de Salto](#monitoramento-de-salto)
  - [Consulta SQL](#consulta-sql)
  - [Gráfico comparativo de alturas médias](#gráfico-comparativo-de-alturas-médias)
  - [Gráfico de evolução do CMJ](#gráfico-de-evolução-do-cmj)
- [Monitoramento de GPS](#monitoramento-de-gps)

## Como executar

Crie e ative um ambiente virtual, instale as dependências e copie o modelo de
configuração:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

No Windows PowerShell, a ativação do ambiente pode ser feita com:

```powershell
.venv\Scripts\Activate.ps1
```


O `.env` contém dados sensíveis e está ignorado pelo Git. O arquivo
`.env.example` contém somente o modelo versionável.

Execute o protótipo com:

```bash
streamlit run app.py
```

O módulo `database.py` centraliza a conexão com o PostgreSQL do Supabase. As
conexões abertas pelo protótipo são configuradas e verificadas como somente
leitura antes de serem disponibilizadas às páginas.

## Monitoramento de Salto

A página `pages/Metricas_de_Salto.py` utiliza dados reais da view
`public.vw_medidas_saltos`. Os dados são carregados por `jump_data.py` e ficam
em cache no Streamlit por cinco minutos.

### Consulta SQL

```sql
SELECT
    id_atleta,
    atleta,
    posicao,
    grupo,
    data_coleta::date AS data_coleta,
    maior_cmj,
    maior_sj
FROM public.vw_medidas_saltos
ORDER BY data_coleta, id_atleta;
```

Os valores de `maior_cmj` e `maior_sj` são medidos em centímetros. Valores
nulos, iguais a zero ou negativos são desconsiderados nos cálculos. Os filtros,
agrupamentos e cálculos descritos abaixo são aplicados em Python depois da
consulta.

### Filtros

#### Atleta

Mantém somente os registros do atleta selecionado. Quando nenhum atleta é
selecionado, são considerados todos os atletas disponíveis para a posição
escolhida.

#### Posição

Mantém somente os registros dos atletas da posição selecionada. A lista de
atletas também é limitada por esse filtro.

#### Período de referência

Considera os últimos 7, 30 ou 90 dias, ou todo o histórico. O início do período
é calculado a partir da data mais recente existente na view, de forma inclusiva:

```text
data inicial = maior data_coleta - (quantidade de dias - 1)
```

### CMJ na última coleta

Exibe o valor de `maior_cmj` na última data de coleta dentro dos filtros ativos.
Se houver mais de um registro nessa data, exibe a média dos valores válidos:

```text
CMJ da data = soma dos valores válidos de maior_cmj na data
              ------------------------------------------------
              quantidade de valores válidos de maior_cmj na data

CMJ na última coleta = CMJ da data válida mais recente
```

### Índice de CMJ na última coleta (±)

Exibe o desvio padrão populacional da série de CMJ por data dentro dos filtros
ativos. Primeiro é calculado o CMJ médio de cada data, conforme a fórmula
anterior. Em seguida:

```text
média da série = soma dos valores de CMJ por data / quantidade de datas

desvio padrão = raiz(
    soma((CMJ da data - média da série)²) / quantidade de datas
)
```

O resultado é apresentado como `± X,X cm`. Com apenas uma data válida, o desvio
padrão é `0,0 cm`.

### SJ na última coleta

Exibe o valor de `maior_sj` na última data de coleta dentro dos filtros ativos.
Se houver mais de um registro nessa data, exibe a média dos valores válidos:

```text
SJ da data = soma dos valores válidos de maior_sj na data
             -----------------------------------------------
             quantidade de valores válidos de maior_sj na data

SJ na última coleta = SJ da data válida mais recente
```

### Índice de SJ na última coleta (±)

Exibe o desvio padrão populacional da série de SJ por data dentro dos filtros
ativos:

```text
média da série = soma dos valores de SJ por data / quantidade de datas

desvio padrão = raiz(
    soma((SJ da data - média da série)²) / quantidade de datas
)
```

O resultado é apresentado como `± X,X cm`. Com apenas uma data válida, o desvio
padrão é `0,0 cm`.

### Coletas com medição

Conta os registros que possuem pelo menos um valor válido em `maior_cmj` ou
`maior_sj` dentro dos filtros ativos:

```text
coletas com medição = quantidade de registros em que
                      maior_cmj > 0 ou maior_sj > 0
```

Cada linha retornada pela view conta como um registro.

## Gráfico comparativo de alturas médias

Compara CMJ e SJ usando todos os registros válidos do período em cada escopo. A
média de cada barra é calculada por:

```text
média da métrica = soma dos valores válidos da métrica
                   -------------------------------------
                   quantidade de valores válidos
```

### Seleção atual

Exibe a média de CMJ e SJ dos registros que atendem simultaneamente aos filtros
de atleta, posição e período. A série recebe o nome do atleta selecionado, da
posição selecionada ou `Todos os atletas`.

### Média {Posição}

Exibe a média de CMJ e SJ de todos os registros dos jogadores da posição de
referência no período. Quando um jogador é selecionado sem um filtro explícito
de posição, a posição desse jogador é usada como referência.

### Média do elenco

Exibe a média de CMJ e SJ de todos os jogadores e de todas as posições no
período. Os filtros de atleta e posição não são aplicados a essa série.

## Gráfico de evolução do CMJ

Agrupa os registros por `data_coleta` e apresenta, em ordem cronológica, a média
dos valores válidos de `maior_cmj` em cada data.

### {Jogador}

Quando um jogador é selecionado, exibe o CMJ desse jogador ao longo do tempo. Se
existir mais de um registro do jogador na mesma data, o ponto representa a média
desses registros.

### Média {Posição}

Exibe, ao longo do tempo, a média do CMJ dos jogadores da posição de referência
em cada data. Quando um jogador é selecionado sem filtro explícito de posição, a
posição dele é usada como referência.

```text
média da posição na data = soma dos CMJs válidos da posição na data
                           ------------------------------------------
                           quantidade de CMJs válidos da posição na data
```

### Média do elenco

Exibe, ao longo do tempo, a média do CMJ de todos os jogadores de todas as
posições em cada data. Somente o filtro de período é aplicado a essa série.

```text
média do elenco na data = soma dos CMJs válidos do elenco na data
                          -----------------------------------------
                          quantidade de CMJs válidos do elenco na data
```

## Monitoramento de GPS
