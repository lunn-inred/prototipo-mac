# Revisões necessárias no banco de dados

Este documento reúne as observações levantadas durante a análise somente leitura
da view `public.vw_medidas_saltos`. Ele serve como referência para discutir com a
equipe os ajustes necessários antes de conectar os dados reais ao protótipo em
Streamlit.

Nenhuma alteração foi realizada no banco durante a análise.

## Diagnóstico atual

A view possui:

- 1.017 linhas;
- 44 atletas distintos;
- 32 datas de coleta;
- dados entre 25/11/2025 e 28/07/2026;
- nenhuma data de coleta nula;
- nenhuma duplicação por atleta, data, equipe e adversário;
- nenhuma linha completamente vazia considerando as métricas atualmente expostas.

Ela já pode servir como base para séries históricas de CMJ, mas ainda não está
adequada como fonte definitiva de toda a página de saltos.

## Estrutura atual da view

```text
atleta
posicao
grupo
data_coleta
equipe
adversario
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

## Revisões prioritárias

### 1. Adicionar o identificador do atleta

A view deve expor `id_atleta`. O protótipo deve usar esse ID para filtros,
consultas e agrupamentos, deixando o nome apenas como rótulo visual. Usar somente
o nome pode causar problemas quando um nome for corrigido, estiver duplicado ou
precisar ser relacionado com outra fonte.

Também é útil incluir `apelido` para uso como rótulo curto na interface.

### 2. Não depender do ID fixo do grupo de medidas

A definição atual usa:

```sql
WHERE m.id_grupo_medida = 1
```

Atualmente o ID 1 representa `Saltos`, mas essa associação pode mudar. A view
deve relacionar `grupo_medida` e filtrar pelo significado:

```sql
JOIN grupo_medida gm
  ON gm.id_grupo_medida = m.id_grupo_medida
WHERE gm.nome = 'Saltos'
```

### 3. Unificar as tentativas de SJ

Existem duas convenções para a mesma sequência de tentativas:

```text
SJ, SJ.1, SJ.2
SJ1, SJ2, SJ3
```

As métricas sem número aparecem somente em 25/11/2025. As métricas numeradas
aparecem entre 30/03/2026 e 02/06/2026.

A view de consumo deve expor apenas:

```text
sj1
sj2
sj3
```

Correspondência sugerida:

```text
sj1 = SJ ou SJ1
sj2 = SJ.1 ou SJ2
sj3 = SJ.2 ou SJ3
```

É necessário decidir a prioridade caso os dois padrões apareçam na mesma coleta.
O ideal, a longo prazo, é normalizar também os nomes na tabela `medida`.

### 4. Tratar zero como ausência de medição

Foram encontrados:

- 177 registros com `maior_cmj = 0`;
- 176 desses registros sem nenhuma tentativa de CMJ preenchida;
- 31 registros com `maior_sj = 0` e sem nenhuma tentativa de SJ preenchida.

Esses zeros representam majoritariamente ausência de medição. Se forem usados
diretamente, reduzem artificialmente médias, mínimos e tendências.

A view deve converter para `NULL` os zeros que não possuem tentativas válidas.
O único caso de `maior_cmj = 0` com alguma tentativa preenchida deve ser
investigado separadamente.

### 5. Calcular o maior CMJ pelas tentativas

Foram encontradas três divergências:

| Atleta | Data | Valor informado | Maior tentativa |
|---|---:|---:|---:|
| Breno Alan Monteiro Chaves | 22/01/2026 | 47,7 | 47,4 |
| Pedro Lucas Oliveira Melo | 26/01/2026 | 41,5 | 42,5 |
| Felipe Cruz | 30/03/2026 | 43,8 | 44,4 |

Para consumo analítico, `maior_cmj` deve ser calculado a partir de `cmj1`,
`cmj2` e `cmj3`, desconsiderando valores nulos.

Durante a validação, é recomendável manter:

```text
maior_cmj_informado
maior_cmj_calculado
```

Isso permite auditar as diferenças antes de escolher o campo definitivo.

### 6. Calcular o maior SJ pelas tentativas

Depois de unificar as colunas de SJ, calcular `maior_sj` a partir de `sj1`,
`sj2` e `sj3`, desconsiderando valores nulos. Durante a auditoria, podem ser
mantidos `maior_sj_informado` e `maior_sj_calculado`.

### 7. Definir explicitamente a granularidade

A granularidade desejada para o protótipo é, inicialmente:

```text
id_atleta + data_coleta
```

Hoje não existem duplicações na view nem na origem para atleta, data, partida e
medida. Mesmo assim, o uso de `MAX` pode esconder duas medições legítimas no mesmo
dia no futuro.

Se houver mais de uma sessão diária, será necessário incluir horário da coleta,
identificador da sessão ou identificador do teste.

### 8. Remover colunas de partida sem uso

`equipe` e `adversario` estão vazias nas 1.017 linhas porque os saltos não estão
associados a partidas. Elas podem ser removidas da view de consumo e reintroduzidas
no futuro caso essa associação passe a existir.

### 9. Definir o tipo adequado para a data

`data_coleta` é `timestamp without time zone`, mas os dados atuais não possuem
horário relevante. Para simplificar filtros e agrupamentos, considerar:

```sql
mv.data::date AS data_coleta
```

Se houver previsão de múltiplas sessões diárias, o timestamp deve ser mantido e
preenchido corretamente.

### 10. Definir a semântica de posição e grupo

`posicao` e `grupo` vêm do cadastro atual do atleta. Eles não representam
necessariamente a situação na data da coleta. Para deixar isso explícito, a view
pode usar:

```text
posicao_atual
grupo_atual
```

Se for necessário analisar o histórico, será preciso criar uma tabela histórica
ou registrar esses atributos junto à coleta.

Na tabela atual de atletas, foram observados:

- 10 atletas sem posição preenchida;
- 11 atletas sem grupo preenchido.

Os filtros do protótipo precisam tratar esses valores ausentes.

### 11. Não retornar linhas sem métrica útil

Após converter zeros inválidos para `NULL`, algumas linhas podem ficar sem CMJ e
sem SJ. A equipe deve decidir entre excluí-las da view ou mantê-las com um campo
como `possui_medicao`. Para os gráficos atuais, excluir linhas sem medição útil é
a alternativa mais simples.

### 12. Documentar as unidades

As alturas aparentam estar em centímetros. A unidade deve ser documentada e,
preferencialmente, incorporada aos nomes:

```text
cmj1_cm
cmj2_cm
cmj3_cm
maior_cmj_cm
sj1_cm
sj2_cm
sj3_cm
maior_sj_cm
```

## Estrutura sugerida para a view de consumo

```text
id_atleta
atleta
apelido
posicao_atual
grupo_atual
data_coleta
cmj1_cm
cmj2_cm
cmj3_cm
maior_cmj_cm
sj1_cm
sj2_cm
sj3_cm
maior_sj_cm
```

Durante a auditoria, incluir também:

```text
maior_cmj_informado_cm
maior_sj_informado_cm
```

## Métricas que a view não possui

O radar atual do protótipo também apresenta:

- potência de pico;
- RSI;
- simetria esquerda/direita.

Essas métricas não estão disponíveis na view analisada. Para manter o radar
completo, a equipe precisa decidir entre:

1. localizar essas métricas em outra tabela ou fonte;
2. definir fórmulas válidas para calculá-las com os dados existentes;
3. criar outra view que reúna as fontes necessárias; ou
4. reduzir o radar às dimensões realmente disponíveis.

## Pontos já considerados adequados

- Não há datas nulas.
- Não foram encontradas duplicações atuais por atleta e coleta.
- Todas as linhas possuem ao menos uma métrica na estrutura atual.
- Os campos numéricos estão em tipos apropriados para cálculos e gráficos.
- O intervalo de datas permite implementar os filtros de período.
- A view já serve para uma primeira série de CMJ, desde que os zeros sejam tratados.

## Ordem recomendada de trabalho

- [ ] Adicionar `id_atleta` e `apelido`.
- [ ] Relacionar `grupo_medida` e filtrar pelo nome `Saltos`.
- [ ] Unificar `SJ`/`SJ.1`/`SJ.2` com `SJ1`/`SJ2`/`SJ3`.
- [ ] Tratar zeros que representam ausência de medição.
- [ ] Investigar o zero de CMJ que possui tentativa preenchida.
- [ ] Calcular o maior CMJ a partir das tentativas.
- [ ] Revisar as três divergências de maior CMJ.
- [ ] Calcular o maior SJ a partir das tentativas unificadas.
- [ ] Definir a granularidade por atleta, data e sessão.
- [ ] Remover `equipe` e `adversario` da view de consumo.
- [ ] Decidir entre `date` e `timestamp` para `data_coleta`.
- [ ] Renomear ou documentar posição e grupo como valores atuais.
- [ ] Definir o tratamento de atletas sem posição ou grupo.
- [ ] Excluir ou identificar linhas sem medição útil.
- [ ] Documentar as unidades das métricas.
- [ ] Definir a origem de potência, RSI e simetria, ou revisar o radar.
- [ ] Validar novamente contagens, nulos, zeros, duplicações e divergências.
- [ ] Conectar a view revisada ao protótipo somente após a validação.
