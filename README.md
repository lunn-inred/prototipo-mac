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
- [Termografia](#termografia)

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

### Logo

Para exibir a identidade do MAC na barra lateral, coloque a imagem PNG em
`assets/logo_mac.png`. O arquivo é carregado automaticamente quando existe; sua
ausência não impede a execução do protótipo.

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

## Monitoramento de GPS

### Extração de relatórios GPS

O botão **Adicionar novos arquivos**, no topo da página **Monitoramento GPS**,
permite enviar um ou vários relatórios PDF diretamente pelo navegador. Para cada
relatório, o extrator renderiza e analisa por OCR as duas últimas páginas (ou a
única página disponível), mostra uma prévia das tabelas reconhecidas e permite
corrigir os valores diretamente em uma grade editável. A grade e o CSV usam as
mesmas colunas e a mesma ordem de `public.vw_medidas_gps`. Equipe, adversário e
data são lidos da primeira linha da página das métricas e ficam bloqueados;
o grupo é sempre GPS. Os campos técnicos de
origem, página, tabela e linha não aparecem. Um único CSV consolidado é gerado
com os dados revisados, em UTF-8 com BOM e usando ponto e vírgula como separador.

O processamento requer as bibliotecas Python declaradas em `requirements.txt` e
o executável Tesseract com o idioma português. No Streamlit Community Cloud, os
pacotes de sistema necessários estão declarados em `packages.txt`. Em uma
instalação local no Windows, instale o Tesseract, inclua o executável no `PATH` e
confirme com:

```powershell
tesseract --list-langs
```

O idioma `por` deve aparecer na lista; se ele não estiver disponível, o extrator
usa `eng` como alternativa. Upload, OCR e edição não gravam no Supabase; os dados
só podem ser enviados após a validação e a confirmação descritas abaixo. O
painel continua consultando a view somente leitura `public.vw_medidas_gps`.

#### Conflito entre OpenCV e img2table

O `img2table` requer a distribuição contrib do OpenCV. Não mantenha
`opencv-python` ou `opencv-python-headless` instalados junto com
`opencv-contrib-python-headless`, pois esses pacotes compartilham o mesmo módulo
`cv2` e podem remover `cv2.ximgproc.niBlackThreshold`. Para recuperar um ambiente
local que apresente esse erro, execute com o ambiente virtual ativado:

```bash
python -m pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python opencv-contrib-python-headless
python -m pip install -r requirements.txt
python -c "import cv2; print(cv2.__version__); print(hasattr(cv2.ximgproc, 'niBlackThreshold'))"
```

A última linha deve mostrar `True`. As linhas impressas pelo Tesseract com versão,
bibliotecas e instruções de CPU (`AVX`, `FMA` e `SSE`) são apenas informativas e
não indicam falha.

### Envio dos dados revisados ao banco

Depois da conferência na grade, o botão **Validar para envio** verifica os dados
dos cabeçalhos, os valores numéricos, os cadastros que serão criados e as medições
já existentes. O nome do PDF é livre e serve apenas para identificar a origem.
Exemplo de primeira linha reconhecida na página:

```text
RELATÓRIO DE ATIVIDADES MAC X IAPE (MD) DOMINGO, MARÇO 1, 2026 - 03:06:22 PM PÁGINA 5/6
```

A gravação só acontece após **Confirmar envio ao banco**. Cada PDF usa uma
transação independente e as medições duplicadas são ignoradas. O timestamp do
cabeçalho da página é gravado em `partida.data` e `medida_valor.data`.
A primeira linha acima produz `MAC`, `IAPE` e `2026-03-01 15:06:22`.
O leitor aceita meses por extenso em português e horários AM/PM, preservando
os segundos. Também aceita datas numéricas com `/`, `.` ou `-`; sem horário,
usa-se `00:00`.
O texto do PDF é utilizado quando disponível; páginas digitalizadas usam OCR.
Cabeçalhos ausentes, inválidos ou divergentes entre páginas bloqueiam o envio,
sem usar o nome do arquivo como alternativa. Extrações de sessões antigas devem
ser refeitas para obter os metadados da página.
Os resultados guardam a versão do extrator. Quando ela muda, a aplicação solicita
nova extração e bloqueia validação e envio dos resultados antigos. Os dados e as
edições anteriores são preservados até a substituição por uma nova extração;
uma tentativa que falhe não apaga esses dados. Ao modificar a lógica de extração
de forma incompatível, incremente `EXTRACTION_VERSION` em `gps_extraction.py`.

As posições extraídas são normalizadas antes da revisão e do envio: `CA` vira
`Centroavante`, `EXT` vira `Extrema`, `GOL` vira `Goleiro`, `VOL` vira
`Volante`, `MEI` vira `Meia`, `LD` e `LE` viram `Lateral`, `ZAG` vira
`Zagueiro` e `ATA` vira `Atacante`. `Ponta` permanece `Ponta`. A normalização
ignora caixa, acentos, espaços e pontuação; valores desconhecidos precisam ser
corrigidos na grade.

As operações de escrita reutilizam as credenciais `SUPABASE_DB_*` já configuradas
para as consultas do painel. A separação continua existindo nas conexões: o
painel abre transações somente leitura, enquanto a confirmação da importação abre
uma transação de escrita. O usuário configurado precisa de `USAGE` no schema
`public`, `SELECT` e `INSERT` em `atleta`, `partida`, `grupo_medida`, `medida` e
`medida_valor`, além de acesso às sequências `serial` correspondentes.

A página `pages/Monitoramento_GPS.py` utiliza dados reais da view
`public.vw_medidas_gps`, carregados por `gps_data.py` e mantidos em cache por
cinco minutos. O seletor dos gráficos disponibiliza todas as medidas numéricas
presentes na view:

- `accel_de_cel_efforts`;
- `accel_de_cel_efforts_per_minute`;
- `distance_km`: distância total em quilômetros;
- `high_speed_distance`: distância HSR, convertida de quilômetros para metros;
- `high_speed_efforts`;
- `max_acceleration`;
- `max_deceleration`;
- `maximum_velocity_km_h`;
- `meterage_per_minute`;
- `player_load_per_minute`;
- `sprint_efforts`: número de sprints.

Os filtros de atletas, posição e período são compartilhados com a página de
saltos. A posição limita as opções do seletor múltiplo de atletas. Os cartões
apresentam a média e o desvio padrão populacional dos registros filtrados no
período completo. Nos gráficos, os valores são agrupados por data de coleta e
cada série de atleta, posição e elenco recebe uma faixa sombreada entre
`média diária − DP diário` e `média diária + DP diário`. O hover informa a média
e o DP de cada data, além do nome do time adversário; com uma única medição
válida no dia, o DP diário é zero. Quando houver mais de um adversário registrado
na mesma data, o hover apresenta os nomes juntos. Quando `adversario` for `MAC`,
o nome exibido é obtido da coluna `equipe`, cobrindo partidas cadastradas com a
orientação invertida. Se `adversario` estiver vazio e `equipe` seguir o formato
`Nome X MAC`, o trecho `Nome` é usado como adversário.

Foram removidos os componentes de distância em sprint, acelerações e
desacelerações separadas, player load total e zonas de velocidade, pois essas
métricas não estão disponíveis na view no formato exigido pelo protótipo.

## Termografia

A página `pages/Termografia.py` aceita múltiplas termografias em PNG ou JPEG de
até 20 MB cada. Para cada imagem, o usuário informa `Tmin` e `Tmax`, ajusta por
slider a temperatura mínima de um pixel quente e utiliza `streamlit-cropper`
para selecionar separadamente a perna esquerda e a perna direita. O limiar
padrão corresponde ao início dos 20% mais quentes do intervalo informado.

Nesta primeira versão, uma LUT Jet fixa associa as cores, do azul ao vermelho,
a posições entre `Tmin` e `Tmax`. A correspondência usa a cor mais próxima e
gera uma matriz de temperaturas aproximadas. As coordenadas dos recortes são
aplicadas sobre essa matriz, e a métrica exibida é a quantidade de pixels com
temperatura maior ou igual ao limiar escolhido.

Imagens, coordenadas e métricas permanecem somente na sessão do Streamlit. Nada
é gravado no banco ou no sistema de arquivos. A LUT é experimental e deverá ser
substituída ou validada contra a paleta real da câmera antes do uso definitivo.
