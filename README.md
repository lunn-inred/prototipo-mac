# Protótipo — MAC Performance

Protótipo em Streamlit para estudar a lógica de visualização e cálculo das
métricas de desempenho do MAC. O projeto possui páginas de monitoramento de
saltos e GPS e utiliza Plotly para a construção dos gráficos.

## Sumário

- [Como executar](#como-executar)
- [Deploy no Streamlit Community Cloud](#deploy-no-streamlit-community-cloud)
- [Monitoramento de Salto](#monitoramento-de-salto)
  - [Consulta SQL](#consulta-sql)
  - [Gráfico comparativo de alturas médias](#gráfico-comparativo-de-alturas-médias)
  - [Gráfico de evolução de CMJ ou SJ](#gráfico-de-evolução-de-cmj-ou-sj)
- [Monitoramento de GPS](#monitoramento-de-gps)

## Como executar

Crie e ative um ambiente virtual, instale as dependências e copie o modelo de
configuração:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

No Windows PowerShell, a ativação do ambiente pode ser feita com:

```powershell
.venv\Scripts\Activate.ps1
```


Preencha `.streamlit/secrets.toml` com as credenciais do Supabase. Esse arquivo
contém dados sensíveis e está ignorado pelo Git; somente o modelo
`.streamlit/secrets.toml.example` é versionado.

Execute o protótipo com:

```bash
streamlit run app.py
```

O módulo `database.py` centraliza a conexão com o PostgreSQL do Supabase. As
conexões abertas pelo protótipo são configuradas e verificadas como somente
leitura antes de serem disponibilizadas às páginas.

## Deploy no Streamlit Community Cloud

O repositório já contém o arquivo `requirements.txt` e utiliza `app.py` como
ponto de entrada. No Streamlit Community Cloud, preencha o deploy com:

```text
Repository: owner/nome-do-repositorio
Branch: main
Main file path: app.py
```

Antes de publicar, abra **Advanced settings** e cole no campo **Secrets**:

```toml
SUPABASE_DB_HOST = "host-do-supabase"
SUPABASE_DB_PORT = "5432"
SUPABASE_DB_NAME = "postgres"
SUPABASE_DB_USER = "usuario-do-supabase"
SUPABASE_DB_PASSWORD = "senha-do-supabase"
SUPABASE_DB_SSLMODE = "require"
```

As mesmas chaves são lidas diretamente por `database.py` nos dois ambientes. No
desenvolvimento local, ficam em `.streamlit/secrets.toml`; no Community Cloud,
ficam no campo **Secrets** das configurações da aplicação. Nunca envie o arquivo
local com valores reais ao repositório.

Após cadastrar os Secrets, clique em **Deploy**. Para disponibilizar o painel
somente à equipe e ao cliente, mantenha a aplicação privada e adicione os
e-mails deles em **App settings > Sharing**.

## Monitoramento de Salto

A página `pages/Metricas_de_Salto.py` utiliza dados reais da view
`public.vw_medidas_saltos`. Os dados são carregados por `jump_data.py` e ficam
em cache no Streamlit por cinco minutos.

### Consulta SQL

```sql
SELECT
    atleta,
    posicao,
    grupo,
    data_coleta::date AS data_coleta,
    maior_cmj,
    maior_sj
FROM public.vw_medidas_saltos
ORDER BY data_coleta, atleta;
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

Quando `Todos os atletas` está selecionado, o indicador recebe o título
**Média do CMJ na última coleta**. A média considera todos os atletas da posição
selecionada ou, sem filtro de posição, todo o elenco.

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

Quando `Todos os atletas` está selecionado, o indicador recebe o título
**Média do SJ na última coleta**. A média considera todos os atletas da posição
selecionada ou, sem filtro de posição, todo o elenco.

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

O gráfico é exibido somente quando um atleta específico está selecionado.

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

## Gráfico de evolução de CMJ ou SJ

O gráfico é exibido somente quando um atleta específico está selecionado.

O usuário escolhe a métrica `CMJ` ou `SJ`. O gráfico agrupa os registros por
`data_coleta` e apresenta, em ordem cronológica, a média dos valores válidos de
`maior_cmj` ou `maior_sj` em cada data.

O usuário pode escolher entre três tipos de visualização:

- **Gráfico de linha:** apresenta a evolução das três séries ao longo das datas;
- **Gráfico de barras:** compara as três séries por data usando barras agrupadas;
- **Box plot:** resume a distribuição dos valores por data de cada série no
  período, exibindo mediana, quartis, média e pontos individuais.

As três opções usam as mesmas séries descritas abaixo.

O desvio padrão populacional do atleta no período também é apresentado no
gráfico. Na visualização de linha, uma área sombreada acompanha o atleta entre os
limites `valor − DP` e `valor + DP` da métrica escolhida. Na visualização de
barras, ele aparece como uma barra de erro `± DP` em cada valor do atleta. No box
plot, um losango indica a média do atleta e a barra vertical representa
`média ± DP`. As séries da posição e do elenco não recebem barras ou faixas de
desvio padrão.

### {Jogador}

Quando um jogador é selecionado, exibe o CMJ ou SJ desse jogador ao longo do
tempo. Se existir mais de um registro do jogador na mesma data, o ponto
representa a média desses registros.

### Média {Posição}

Exibe, ao longo do tempo, a média da métrica escolhida para os jogadores da
posição de referência em cada data. Quando um jogador é selecionado sem filtro
explícito de posição, a posição dele é usada como referência.

```text
média da posição na data = soma dos valores válidos da posição na data
                           ---------------------------------------------
                           quantidade de valores válidos na data
```

### Média do elenco

Exibe, ao longo do tempo, a média da métrica escolhida para todos os jogadores
de todas as posições em cada data. Somente o filtro de período é aplicado a essa
série.

```text
média do elenco na data = soma dos valores válidos do elenco na data
                          --------------------------------------------
                          quantidade de valores válidos na data
```

## Monitoramento de GPS
