# Monitoramento de salto

[← Voltar ao README](../README.md)

## Monitoramento de Salto

A página `frontend/streamlit/pages/Metricas_de_Salto.py` utiliza dados reais da view
`public.vw_medidas_saltos`. Os dados são carregados por `jump_data.py` e ficam
em cache no Streamlit por cinco minutos.

### CRUD e importação de planilhas

O painel **Gerenciar coletas de salto** permite cadastrar, editar e excluir uma
coleta identificada pelo par jogador/data. Cada coleta pode conter `CMJ1`,
`CMJ2`, `CMJ3`, `MAIOR_CMJ`, `SJ1`, `SJ2`, `SJ3` e `MAIOR_SJ`; ao menos uma
medida positiva é obrigatória. Os valores de maior CMJ e maior SJ são gravados
como fornecidos, sem serem recalculados no consumo.

A aba **Importar planilha** aceita vários arquivos `.xlsx`. Somente abas cujo
nome está no formato `DDMMAAAA` são interpretadas como coletas; abas de modelo
como `EM BRANCO` são ignoradas. Linhas de média, valores `S/D`, campos vazios e
zeros não viram medições. A posição, o grupo e o peso presentes na planilha não
são importados: o atleta precisa existir e é correlacionado por nome, apelido ou
nome alternativo. Correspondências ausentes ou ambíguas podem ser corrigidas no
editor antes da validação.

O envio tem três etapas separadas: extração, validação e confirmação. Uma coleta
idêntica à existente é marcada como duplicada e ignorada; valores diferentes
para o mesmo jogador/data são marcados como conflito e bloqueiam o envio, para
evitar sobrescritas silenciosas. A confirmação grava o lote em uma única
transação.

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

#### Período de referência

Permite analisar os últimos 7, 30 ou 90 dias, ou todo o histórico disponível.
Assim como na página de GPS, o período padrão é **Últimos 90 dias**. Nos períodos
em dias, a data atual está incluída na contagem. A opção **Todo o histórico** usa
como limites a primeira e a última data existentes na view.

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

### Tabela comparativa por jogador

A tabela resume média e desvio padrão populacional de CMJ e SJ por jogador no
período filtrado. A coluna **Análise** compara cada atleta com os jogadores da
mesma posição usando um z-score combinado:

```text
z da métrica = (média do jogador - média da posição) / DP da posição
z combinado  = média dos z-scores disponíveis de CMJ e SJ
```

A referência da posição é calculada sobre as médias individuais, garantindo
que todos os atletas tenham o mesmo peso mesmo quando possuem quantidades
diferentes de coletas. O resultado é classificado como **Acima da média** para
`z >= 0,5`, **Na média** entre `-0,5` e `0,5`, e **Abaixo da média** para
`z <= -0,5`. A célula de análise recebe fundo verde, amarelo ou vermelho,
respectivamente. Casos com dados insuficientes recebem fundo cinza.

Quando somente CMJ ou SJ possui referência válida, a análise utiliza essa única
métrica. Posições com menos de dois atletas válidos ou sem variação recebem a
indicação **Dados insuficientes**.

## Gráfico de evolução de CMJ ou SJ

Os gráficos são exibidos quando pelo menos um atleta está selecionado. Um único
seletor define a métrica `CMJ` ou `SJ`, e duas visualizações aparecem ao mesmo
tempo:

- **Gráfico de linha:** evolução das séries ao longo das datas;
- **Box plot:** distribuição das médias por data, com mediana, quartis, média e
  pontos individuais.

O gráfico de linha ocupa a primeira linha e o box plot aparece logo abaixo, em
largura total.

No gráfico de linha, o desvio padrão populacional é calculado separadamente em
cada data para todas as séries: atleta, posição e elenco. A área sombreada usa os
limites `média diária − DP diário` e `média diária + DP diário`, e o hover mostra
a média e o DP correspondentes à data. Quando há somente uma medição válida no
dia, o DP diário é zero. No box plot, um losango continua indicando a média do
período e a barra vertical representa `média ± DP` agregado de cada atleta.

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
