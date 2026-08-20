# Protótipo — MAC Performance

Protótipo em Streamlit para estudar a lógica de visualização e cálculo das
métricas de desempenho do MAC. O projeto possui páginas de monitoramento de
saltos e GPS e utiliza Plotly para a construção dos gráficos.

## Sumário

- [Como executar](#como-executar)
- [Deploy no Streamlit Community Cloud](#deploy-no-streamlit-community-cloud)
- [Monitoramento de Salto](#monitoramento-de-salto)
  - [Consulta SQL](#consulta-sql)
  - [Gráfico de evolução de CMJ ou SJ](#gráfico-de-evolução-de-cmj-ou-sj)
  - [Radar das últimas cinco datas](#radar-das-últimas-cinco-datas)
  - [Radar comparativo por atleta](#radar-comparativo-por-atleta)
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

#### Atletas

Permite selecionar um ou vários atletas. Quando a seleção está vazia, são
considerados todos os atletas disponíveis para a posição escolhida. Os gráficos
são exibidos somente quando há pelo menos um atleta selecionado explicitamente.

#### Posição

Mantém somente os registros dos atletas da posição selecionada. A lista de
atletas também é limitada por esse filtro. Selecionar uma posição equivale a
selecionar o grupo completo de jogadores daquela posição: os gráficos e o radar
usam todos eles quando nenhum atleta específico é marcado. Caso sejam marcados
atletas no componente múltiplo, somente esse subconjunto da posição é analisado.

#### Período de análise

Permite escolher diretamente as datas inicial e final. As duas datas são
incluídas na análise. Por padrão, a data final é o dia atual e a data inicial é
30 dias antes.

### Média do CMJ

Exibe a média de todos os valores válidos de `maior_cmj` que atendem aos filtros:

```text
média do CMJ = soma dos valores válidos de maior_cmj
               ---------------------------------------
               quantidade de valores válidos
```

### Índice de CMJ (±)

Exibe o desvio padrão populacional dos mesmos valores usados na média:

```text
desvio padrão = raiz(
    soma((CMJ - média do CMJ)²) / quantidade de valores válidos
)
```

### Média do SJ

Exibe a média de todos os valores válidos de `maior_sj` que atendem aos filtros:

```text
média do SJ = soma dos valores válidos de maior_sj
              --------------------------------------
              quantidade de valores válidos
```

### Índice de SJ (±)

Exibe o desvio padrão populacional dos mesmos valores usados na média:

```text
desvio padrão = raiz(
    soma((SJ - média do SJ)²) / quantidade de valores válidos
)
```

Os desvios são apresentados como `± X,X cm`. Com apenas um valor válido, o
desvio padrão é `0,0 cm`.

### Coletas com medição

Conta os registros que possuem pelo menos um valor válido em `maior_cmj` ou
`maior_sj` dentro dos filtros ativos:

```text
coletas com medição = quantidade de registros em que
                      maior_cmj > 0 ou maior_sj > 0
```

Cada linha retornada pela view conta como um registro.

## Gráfico de evolução de CMJ ou SJ

Os gráficos são exibidos quando pelo menos um atleta está selecionado. Um único
seletor define a métrica `CMJ` ou `SJ`, e duas visualizações aparecem ao mesmo
tempo:

- **Gráfico de linha:** evolução das séries ao longo das datas;
- **Box plot:** distribuição das médias por data, com mediana, quartis, média e
  pontos individuais.

O gráfico de linha ocupa a primeira linha e o box plot aparece logo abaixo, em
largura total.

O desvio padrão populacional do atleta no período também é apresentado no
gráfico. Na visualização de linha, uma área sombreada acompanha cada atleta entre
os limites `valor − DP` e `valor + DP`. No box plot, um losango indica a média e
a barra vertical representa `média ± DP` de cada atleta.

### {Jogador}

Cada atleta selecionado recebe uma série própria. Se existir mais de um registro
do atleta na mesma data, o ponto representa a média desses registros.

### Média {Posição}

Exibe, ao longo do tempo, a média da métrica escolhida para os jogadores da
posição de referência em cada data. Sem filtro explícito de posição, é incluída
uma série média para cada posição presente entre os atletas selecionados.

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

## Radar das últimas cinco datas

O radar temporal aparece abaixo do box plot. Cada eixo representa uma das cinco
últimas datas válidas da métrica escolhida, contando para trás a partir da data
final do período. A data inicial não limita essa busca.

São apresentadas as mesmas séries do gráfico evolutivo: cada atleta selecionado,
as médias das posições de referência e a média do elenco. Todos os valores são
alinhados nas mesmas cinco datas.

Quando houver menos de cinco datas válidas até a data final, o radar utiliza
somente as datas disponíveis.

## Radar comparativo por atleta

O radar aparece ao lado do radar temporal somente quando pelo menos três atletas
são selecionados. O mesmo seletor dos gráficos define se a análise usa `CMJ` ou
`SJ`.

Cada eixo representa um atleta, e o raio corresponde à média dos valores válidos
desse atleta no período selecionado:

```text
média do atleta = soma dos valores válidos do atleta no período
                  -----------------------------------------------
                  quantidade de valores válidos do atleta
```

Caso menos de três atletas selecionados possuam dados válidos para a métrica no
período, o radar é substituído por uma mensagem informativa.

## Monitoramento de GPS
