# Protótipo — MAC Performance

Protótipo em Streamlit para estudar a lógica de visualização e cálculo das
métricas de desempenho do MAC. O projeto possui páginas de monitoramento de
saltos e GPS e utiliza Plotly para a construção dos gráficos.

## Sumário

- [Como executar](#como-executar)
- [Monitoramento de Salto](#monitoramento-de-salto)
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

Preencha o arquivo `.env` com as credenciais disponíveis em **Supabase > Project
Settings > Database**:

```text
SUPABASE_DB_HOST
SUPABASE_DB_PORT
SUPABASE_DB_NAME
SUPABASE_DB_USER
SUPABASE_DB_PASSWORD
SUPABASE_DB_SSLMODE
SUPABASE_DB_SCHEMA
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

A página `pages/Metricas_de_Salto.py` já utiliza dados reais da view
`public.vw_medidas_saltos`. A consulta fica centralizada em `jump_data.py` e seu
resultado é mantido em cache pelo Streamlit por cinco minutos.

### Estrutura atual da view

```text
id_atleta
atleta
posicao
grupo
data_coleta
cmj1
cmj2
cmj3
maior_cmj
maior_sj
sj
sj_1
sj_2
sj1
sj2
sj3
```

As colunas legadas `sj`, `sj_1` e `sj_2` continuam presentes na estrutura, mas
estão vazias. Os dados válidos de SJ estão concentrados em `sj1`, `sj2` e `sj3`.

### Dados consumidos pelo protótipo

O protótipo consulta:

```text
id_atleta
atleta
posicao
grupo
data_coleta
maior_cmj
maior_sj
```



### Filtros

A página permite filtrar por:

- atleta;
- posição;
- últimos 7 dias;
- últimos 30 dias;
- últimos 90 dias;
- todo o histórico.

Os períodos são calculados em relação à data mais recente disponível na view,
atualmente 28/07/2026. Essa abordagem mantém os filtros úteis mesmo quando não há
uma coleta no dia em que o protótipo é executado.

### Indicadores

A página apresenta:

- CMJ na última coleta;
- SJ na última coleta;
- quantidade de coletas com alguma medição válida.

O texto exibido abaixo de CMJ e SJ representa o desvio padrão populacional dos
valores das coletas válidas dentro dos filtros ativos. Por exemplo:

```text
Desvio padrão: 0,1 cm
```

indica que a dispersão dos valores em relação à média é de 0,1 cm.

Quando um atleta está selecionado, o cálculo considera a série de coletas desse
atleta. Na visão geral ou por posição, considera a série das médias por data. Com
apenas uma coleta válida, o desvio padrão exibido é 0,0 cm.

### Gráficos

#### Comparativo de alturas médias

Compara as médias de CMJ e SJ para:

- seleção atual;
- posição de referência, quando aplicável;
- elenco completo.

#### Evolução do CMJ

Apresenta os valores por data de coleta e pode incluir:

- histórico do atleta selecionado;
- média da posição;
- média do elenco.

### Métricas ainda indisponíveis

O desenho inicial previa um radar biomecânico. Ele não está sendo exibido porque
a fonte atual ainda não contém dados suficientes para:

- potência de pico;
- RSI ou índice de força reativa;
- assimetria entre os lados esquerdo e direito;
- simetria esquerda/direita.


### Campos ainda não utilizados

- `grupo` é carregado pela consulta, mas ainda não possui filtro ou gráfico.
- `cmj1`, `cmj2` e `cmj3` não são consumidos pela página.
- `sj1`, `sj2` e `sj3` não são consumidos pela página.
- `sj`, `sj_1` e `sj_2` estão vazios e não são consultados.

### Instruções SQL

## Monitoramento de GPS

A página `pages/Monitoramento_GPS.py` ainda utiliza dados fictícios definidos no
próprio código. Ela ainda não consulta o Supabase.

O protótipo atual apresenta:

- filtros de atleta, posição e período;
- distância total;
- distância em alta intensidade;
- distância em sprint;
- acelerações e desacelerações;
- evolução de variáveis selecionadas;
- distribuição por zonas de velocidade.

Antes da integração, será necessário analisar a estrutura das tabelas ou views de
GPS, validar as unidades, definir as fórmulas de agregação e relacionar os nomes
alternativos do sistema de GPS com `id_atleta`.
