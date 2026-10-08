# Protótipo — MAC Performance

Aplicação dividida em uma API FastAPI e uma interface Streamlit para cadastro
de atletas, análise e visualização das métricas de desempenho do MAC. A API
centraliza banco, importações e processamento; o Streamlit funciona como cliente
da API em todos os modos, incluindo o desktop. O frontend não acessa o banco diretamente.

## Sumário

- [Como executar](#como-executar)
  - [Execução separada da API e do Streamlit](#execução-separada-da-api-e-do-streamlit)
  - [Como executar o aplicativo desktop](#como-executar-o-aplicativo-desktop)
  - [Testes](#testes)
- [Docker](#docker)
- [Arquitetura](#arquitetura)
- [Configuração](#configuração)
- [API HTTP](#api-http)
  - [Autenticação](#autenticação)
  - [Documentação interativa](#documentação-interativa)
  - [Endpoints](#endpoints)
- [Deploy no Streamlit Community Cloud](#deploy-no-streamlit-community-cloud)
- [Mural e CRUD de jogadores](#mural-e-crud-de-jogadores)
- [Monitoramento de Salto](#monitoramento-de-salto)
- [Monitoramento de GPS](#monitoramento-de-gps)
- [Termografia](#termografia)

## Como executar

Requer Python 3.10 ou mais recente e os pacotes de sistema de `packages.txt`.
Crie o ambiente, instale as dependências e copie os modelos de configuração:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

No Windows PowerShell, ative com `.venv\Scripts\Activate.ps1`. Nunca versione o
`.env`: ele está no `.gitignore`. O arquivo `frontend/streamlit/.streamlit/secrets.toml` é apenas
uma alternativa para ambientes hospedados do Streamlit, não sendo necessário
para a execução local ou desktop.

### Execução separada da API e do Streamlit

Inicie cada processo em um terminal, a partir da raiz do projeto:

```bash
# Terminal 1 — API
uvicorn backend.mac_api.main:app --reload --host 127.0.0.1 --port 8000 --env-file .env

# Terminal 2 — interface
python -m frontend.run
```

A API é obrigatória. Sem `MAC_API_BASE_URL`, o cliente tenta
`http://127.0.0.1:8000`. Ambos os processos leem o mesmo `.env`; não é necessário
repetir a chave no comando. O cliente não executa serviços locais nem abre
conexões com o banco. Abra `http://localhost:8501` e consulte a API em
`http://127.0.0.1:8000/docs`.

Para instalar somente um processo, use `frontend/requirements.txt` ou
`backend/requirements.txt`. O `requirements.txt` da raiz instala ambos.
Os comandos antigos `streamlit run app.py` e `python desktop.py` continuam como
pontos de entrada de compatibilidade; para a interface web, prefira
`python -m frontend.run`, que também carrega o tema da pasta do frontend.

### Docker

Com o `.env` preenchido na raiz:

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f backend frontend
```

Abra `http://localhost:8501`; API e Swagger ficam em `http://127.0.0.1:8000/docs`.
O frontend usa `http://backend:8000` na rede interna. Somente o backend recebe
as credenciais do banco. Tesseract e seus idiomas são instalados na imagem do
backend. Os containers executam com usuário sem privilégios.

```bash
docker compose down
```

O Docker é opcional para desenvolvimento e implantação web. O executável
desktop continua usando processos Python locais e não exige Docker do usuário.
O procedimento de teste com PostgreSQL isolado está em
[docs/architecture.md](docs/architecture.md).

### Como executar o aplicativo desktop

O cliente também pode ser executado em uma janela nativa com
`streamlit-desktop-app`. O conteúdo continua sendo renderizado pelo Streamlit,
mas fica dentro de uma WebView, sem abrir uma aba do navegador. Durante o
desenvolvimento com `python desktop.py`, a FastAPI é iniciada separadamente. No
executável empacotado, API, Streamlit e WebView são iniciados automaticamente.

#### 1. Instale as dependências

Com o ambiente virtual ativado, instale as dependências do desktop. Esse arquivo
também instala o conteúdo de `requirements.txt`:

```bash
python -m pip install -r requirements-desktop.txt
```

No Ubuntu/Debian, instale também as bibliotecas do sistema:

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-por libxcb-cursor0
```

No Windows e no macOS essas bibliotecas Linux não são necessárias.

#### 2. Configure o `.env`

API, Streamlit e launcher desktop utilizam o mesmo arquivo `.env` na raiz do
projeto. Você pode copiá-lo do modelo:

```bash
cp .env.example .env
```

Ou criar `.env` e copiar todo o modelo semipronto abaixo. Preencha somente os
campos vazios do Supabase. A chave do Llama Cloud é opcional:

```env
# PostgreSQL/Supabase
SUPABASE_DB_HOST=
SUPABASE_DB_PORT=5432
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=
SUPABASE_DB_PASSWORD=
SUPABASE_DB_SSLMODE=require

# Extração de formulários legados — opcional
LLAMA_CLOUD_API_KEY=

# API local
MAC_API_KEY=mac-local-dev-7f2c9a41d8e64b30b53f
MAC_API_CORS_ORIGINS=http://localhost:8501
MAC_API_TIMEOUT_SECONDS=300

# Usada por python desktop.py e pelo modo web separado.
# O executável empacotado substitui a porta automaticamente.
MAC_API_BASE_URL=http://127.0.0.1:8000
```

O inicializador repassa automaticamente a URL e a chave da API local para o
Streamlit. Não é necessário criar ou repetir configurações em outro arquivo.
Os campos `SUPABASE_DB_HOST`, `SUPABASE_DB_USER` e `SUPABASE_DB_PASSWORD` são
obrigatórios para acessar os dados; os valores reais não devem ser enviados ao
Git.

#### 3. Execute em desenvolvimento

No primeiro terminal, inicie a API:

```bash
source .venv/bin/activate
uvicorn backend.mac_api.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

No segundo terminal, inicie Streamlit e WebView:

```bash
source .venv/bin/activate
python desktop.py
```

O `python desktop.py` não inicia nem encerra a API. Ele utiliza a URL configurada
em `MAC_API_BASE_URL`, que no modelo aponta para `http://127.0.0.1:8000`.
Quando a inicialização estiver correta, seu terminal apresentará:

```text
[MAC Desktop] Usando API externa em http://127.0.0.1:8000.
You can now view your Streamlit app in your browser.
URL: http://localhost:56789
```

Valide o backend em `http://127.0.0.1:8000/health` e acesse o Swagger em
`http://127.0.0.1:8000/docs`.

No Windows PowerShell, substitua `source .venv/bin/activate` por:

```powershell
.venv\Scripts\Activate.ps1
```

#### 4. Gere um executável

Para gerar o executável da plataforma atual:

```bash
python -m PyInstaller --clean --noconfirm desktop/desktop.spec
```

O resultado fica em `dist/MAC Performance` no Linux. No Windows, o arquivo terá
extensão `.exe`. Antes de executá-lo, copie o mesmo `.env` para o diretório do
binário:

```bash
cp .env "dist/.env"
```

Abra o executável Linux:

```bash
"./dist/MAC Performance"
```

No Windows PowerShell, copie a configuração e abra o `.exe` com:

```powershell
Copy-Item .env "dist\.env"
& ".\dist\MAC Performance.exe"
```

O `.env` não é incluído no pacote nem versionado, evitando que credenciais sejam
gravadas no binário. O executável inicia a API automaticamente usando esse
arquivo único. Diferentemente de `python desktop.py`, não é necessário executar
o comando `uvicorn` antes de abrir o binário. Ao fechar o executável, seus
processos internos da API e do Streamlit são encerrados.

O `.env` concede acesso ao banco e deve ser entregue somente a máquinas
confiáveis. Para distribuição fora de um ambiente controlado, prefira hospedar
a API e não distribuir credenciais do Supabase.

O build é específico do sistema operacional: gere a versão Windows no Windows,
a versão Linux no Linux e a versão macOS no macOS. No Linux, a interface usa
PySide6/Qt6; no Windows, a WebView depende do Microsoft Edge WebView2,
normalmente já instalado. O build inclui o
Tesseract e os dados de idioma quando eles estão instalados na máquina usada
para empacotar, necessários à leitura dos formulários legados.

Arquivos relacionados:

- `desktop/launcher.py`: inicia a interface e, no binário, também a API;
- `desktop.py`: entrada de compatibilidade para o launcher;
- `desktop/desktop.spec`: inclui páginas, assets, dependências dinâmicas e Tesseract;
- `requirements-desktop.txt`: dependências adicionais do cliente desktop;
- `.env.example`: único modelo de configuração da aplicação completa.

O primeiro início do executável único pode demorar alguns segundos enquanto os
arquivos internos são extraídos. A versão web e os comandos existentes não são
alterados por essa modalidade.

### Testes

```bash
python -m unittest discover -v
```

A suíte cobre regras de domínio, persistência simulada, importações e contratos
HTTP. A integração real com LlamaParse só roda quando explicitamente habilitada.

### Logo

Para exibir a identidade do MAC na barra lateral, coloque a imagem PNG em
`frontend/streamlit/assets/logo_mac.png`. O arquivo é carregado automaticamente quando existe; sua
ausência não impede a execução do protótipo.

## Arquitetura

```text
.
├── frontend/
│   ├── run.py                   # inicialização web
│   ├── requirements.txt
│   ├── streamlit/
│   │   ├── app.py e pages/      # navegação e páginas
│   │   ├── components/         # filtros, importadores e termografia
│   │   ├── api_client/         # HTTP, DTOs e transporte de imagens/matrizes
│   │   ├── presentation/       # cache e adaptação visual
│   │   ├── assets/
│   │   └── .streamlit/
│   └── tests/
├── backend/
│   ├── mac_api/
│   │   ├── main.py e schemas.py
│   │   ├── core/               # configuração, conexão e transporte
│   │   ├── repositories/       # leitura de dados
│   │   └── modules/            # atletas, GPS, saltos, termografia e indicadores
│   ├── requirements.txt
│   ├── migrations/             # alterações SQL versionadas, quando necessárias
│   └── tests/                  # unitários, contratos e integração local
├── desktop/                    # launcher, spec do PyInstaller e testes
├── infrastructure/docker/      # imagens dos processos web
├── experiments/                # protótipos de pesquisa, quando presentes
├── docs/
├── compose.yaml e compose.test.yaml
├── .env.example
├── app.py e desktop.py          # entradas de compatibilidade
└── README.md
```

Fluxo web: navegador → Streamlit → HTTP → FastAPI → serviços/repositórios → Supabase.
No executável, a mesma API é iniciada localmente e consumida pela WebView.

O frontend controla widgets, desenho, formulários e estado temporário. O backend
calcula segmentação, temperaturas, pixels quentes, divisão anatômica, comparação
basal/atual, estatísticas e classificação EVA; também valida e persiste dados.
Não há imports do backend no cliente. Testes de arquitetura protegem essa regra.

As métricas de leitura vêm das views; cadastro de atletas continua na tabela
`public.atleta`. Operações de escrita consultam tabelas dentro de transações para
validar existência, duplicatas e integridade. Nenhuma alteração de schema é
necessária para esta reorganização.

As imagens permanecem temporárias na sessão do cliente e durante as requisições.
A API não salva arquivos nem mantém análises persistentes. A timeline visual
continua temporária; somente medidas confirmadas são gravadas no banco.

Detalhes de contratos, testes e evolução para React:
[docs/architecture.md](docs/architecture.md).

## Configuração

A execução local, a API integrada e o aplicativo desktop utilizam o único arquivo
`.env`. Em hospedagens do Streamlit, somente URL, chave e timeout do cliente
podem ser cadastrados em `frontend/streamlit/.streamlit/secrets.toml` ou no painel
de Secrets. Credenciais do banco e OCR pertencem ao ambiente da API.

| Variável | Processo | Finalidade |
|---|---|---|
| `SUPABASE_DB_*` | API | Conexão PostgreSQL com SSL |
| `LLAMA_CLOUD_API_KEY` | API | Extração principal de documentos legados |
| `MAC_API_KEY` | Ambos | Exige/envia o cabeçalho `X-API-Key`; se vazio, autenticação fica desativada para desenvolvimento |
| `MAC_API_CORS_ORIGINS` | API | Origens permitidas, separadas por vírgula |
| `MAC_API_BASE_URL` | Streamlit | URL pública ou interna da API |
| `MAC_API_TIMEOUT_SECONDS` | Streamlit | Timeout de chamadas longas, padrão 300 s |

## API HTTP

A versão inicial usa o prefixo `/api/v1`. Erros de validação retornam `422`,
recursos inexistentes `404` e conflitos de integridade `409`. O banco continua
usando transações para que uma falha não deixe gravações parciais.

### Autenticação

Defina a mesma `MAC_API_KEY` na API e no Streamlit. Clientes externos devem enviar:

```http
X-API-Key: sua-chave
```

Use HTTPS no ambiente hospedado. A chave é uma proteção simples entre serviços;
quando houver usuários finais e permissões distintas, adote autenticação por
usuário/token no sistema consumidor.

### Documentação interativa

Com a API em execução:

- Swagger UI: `http://127.0.0.1:8000/docs`;
- ReDoc: `http://127.0.0.1:8000/redoc`;
- contrato OpenAPI: `http://127.0.0.1:8000/openapi.json`;
- saúde do processo: `GET /health` (não exige chave).

### Endpoints

| Método e rota | Função | Escrita no banco |
|---|---|---|
| `GET /api/v1/athletes` | Lista os atletas | Não |
| `GET /api/v1/athletes/{id}` | Consulta um atleta | Não |
| `POST /api/v1/athletes` | Cadastra atleta | Sim |
| `PUT /api/v1/athletes/{id}` | Atualiza atleta, preservando `nome_alternativo` | Sim |
| `DELETE /api/v1/athletes/{id}` | Exclui atleta sem medições | Sim |
| `GET /api/v1/players/dashboard` | Dados do mural | Não |
| `POST /api/v1/athletes/match` | Correlaciona um nome ao cadastro | Não |
| `POST /api/v1/analytics/{operation}` | Calcula indicadores e estatísticas | Não |
| `GET /api/v1/jumps` | Registros da view de saltos | Não |
| `GET /api/v1/jumps/collections` | Lista coletas de salto editáveis | Não |
| `POST /api/v1/jumps/collections` | Cadastra uma coleta de salto | Sim |
| `PUT /api/v1/jumps/collections/{athlete_id}/{date}` | Substitui uma coleta de salto | Sim |
| `DELETE /api/v1/jumps/collections/{athlete_id}/{date}` | Exclui uma coleta de salto | Sim |
| `POST /api/v1/jumps/import/extract` | Extrai planilhas XLSX sem persistir | Não |
| `POST /api/v1/jumps/import/preview` | Valida duplicatas e conflitos do lote | Não |
| `POST /api/v1/jumps/import` | Confirma o lote XLSX revisado | Sim |
| `GET /api/v1/gps` | Registros da view GPS | Não |
| `POST /api/v1/gps/extract` | Extrai um lote de PDFs | Não |
| `POST /api/v1/gps/editor-rows` | Prepara linhas editáveis e vínculos dos atletas | Não |
| `POST /api/v1/gps/preview` | Valida e prevê alterações do lote | Não |
| `POST /api/v1/gps/import` | Confirma a importação GPS revisada | Sim |
| `GET /api/v1/thermography?athlete_id=` | Histórico térmico, opcionalmente por atleta | Não |
| `POST /api/v1/thermography/scale` | Extrai Tmin e Tmax impressos na imagem | Não |
| `POST /api/v1/thermography/analyze` | Detecta pernas e conta pixels em uma imagem | Não |
| `POST /api/v1/thermography/segment` | Análise completa com caixas, paleta e correções manuais | Não |
| `POST /api/v1/thermography/operations/{operation}` | Divisão anatômica, timeline e operações de edição | Não |
| `POST /api/v1/thermography` | Registra uma coleta de frente e verso | Sim |
| `POST /api/v1/thermography/legacy/extract` | Extrai documentos manuscritos | Não |
| `POST /api/v1/thermography/legacy/validate-athletes` | Correlaciona nomes revisados | Não |
| `POST /api/v1/thermography/legacy/import` | Registra o lote legado validado | Sim |

Uploads usam `multipart/form-data`; os demais corpos usam JSON. Os esquemas,
campos obrigatórios e exemplos para testar cada chamada ficam sempre atualizados
na página `/docs`.
Os formatos de imagens/matrizes e as operações permitidas estão em
[docs/architecture.md](docs/architecture.md).

## Mural e CRUD de jogadores

A página inicial lista o elenco e resume CMJ, distância GPS e a EVA Dor mais
recente. O gerenciador permite cadastrar, editar e excluir atletas. Somente o
nome é obrigatório; `nome_alternativo` não é exposto no CRUD e permanece
inalterado nas edições. Atletas que já possuem medições não podem ser excluídos.

## Deploy no Streamlit Community Cloud

Hospede a API separadamente. No Community Cloud, use `app.py` como entrada de
compatibilidade e configure somente os dados do cliente em **Secrets**:

```toml
MAC_API_BASE_URL = "https://sua-api.exemplo.com"
MAC_API_KEY = "a-mesma-chave-configurada-no-backend"
MAC_API_TIMEOUT_SECONDS = "300"
```

Credenciais do Supabase e `LLAMA_CLOUD_API_KEY` pertencem à hospedagem da API.
O backend não lê `secrets.toml`. O exemplo de secrets do cliente fica em
`frontend/streamlit/.streamlit/secrets.toml.example`.

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
dos cabeçalhos, os valores numéricos, os cadastros auxiliares e as medições
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

O nome reconhecido no PDF permanece visível e bloqueado para conferência. O
sistema tenta associá-lo a um jogador existente por `nome`, `apelido` ou
`nome_alternativo`, ignorando caixa, acentos e pontuação. A grade aceita apenas a
seleção de jogadores cadastrados, usa a posição do cadastro e bloqueia validação
e envio enquanto houver linhas sem associação única. A importação GPS nunca cria
jogadores automaticamente.

As operações de escrita reutilizam as credenciais `SUPABASE_DB_*` já configuradas
para as consultas do painel. A separação continua existindo nas conexões: o
painel abre transações somente leitura, enquanto a confirmação da importação abre
uma transação de escrita. O usuário configurado precisa de `USAGE` no schema
`public`, `SELECT` e `INSERT` em `atleta`, `partida`, `grupo_medida`, `medida` e
`medida_valor`, além de acesso às sequências `serial` correspondentes.

A página `frontend/streamlit/pages/Monitoramento_GPS.py` utiliza dados reais da view
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

A página `frontend/streamlit/pages/Termografia.py` registra uma nova análise a partir das imagens
de frente e verso. Ao final da página, o componente recolhido **Formulários**
permite importar fichas manuscritas. Ao adicionar a análise à timeline ou
registrá-la no banco, uma janela solicita a data da coleta e apresenta a data
atual de São Paulo como padrão. Quando omitida em uma chamada à API, a mesma
data padrão é aplicada pelo serviço.

A nova análise utiliza um assistente com **Continuar** e **Voltar**, apresentando
somente uma etapa por vez:

1. Jogador, massa, EVA Dor e observações opcionais.
2. Upload de frente/verso, prévia e rotação em incrementos de 90°.
3. Caixas das pernas e barra de cores, Tmin/Tmax e limiar de pixels quentes.
4. Segmentação automática por GrabCut.
5. Divisão de cada perna em coxa, joelho, canela e pé.
6. Revisão das métricas, tabela do registro e confirmação do envio.

As correções de caixas, máscaras e divisões são feitas em pop-ups. Na divisão
anatômica, arraste as três linhas sobre a imagem; não é necessário ajustar
sliders percentuais. O rascunho e as imagens ficam na sessão ao voltar para
etapas anteriores. **Iniciar outra análise** descarta somente o rascunho atual,
mediante confirmação, preservando o banco e a timeline. A API considera a rotação
ao localizar as caixas e ler a barra térmica, preservando sua ordem quente/frio.

Durante a sessão, o botão **Adicionar à timeline** mantém temporariamente as
imagens, matrizes de temperatura, caixas e segmentações anatômicas. A máscara de
pixels quentes e as métricas não são congeladas: elas são recalculadas em tempo
real pelos controles das coletas basal e atual. Os cartões da timeline permitem
marcar independentemente uma coleta **Basal** e uma coleta **Atual** do mesmo
jogador. A interface alerta quando a Atual antecede a Basal, sem bloquear a
comparação. Nas abas de
frente e verso, a comparação exibe as duas imagens, mapas normalizados por perna
e as métricas atuais com deltas em relação à basal. Vermelho identifica pixels que
ficaram quentes, amarelo os persistentes e azul os resolvidos.

Na nova análise, o usuário informa jogador, massa, data da coleta, EVA Dor e,
opcionalmente, observações. O sistema tenta identificar automaticamente as duas
caixas R1/R2; quando elas não existem ou estão incorretas, cria regiões iniciais
que podem ser redesenhadas pelo usuário. A lateralidade é invertida entre frente
e verso e o OCR é aplicado às regiões superior e inferior
do canto direito para preencher automaticamente Tmax e Tmin. Os campos continuam
editáveis e usam 20–40 °C como valores iniciais quando o OCR não reconhece uma
escala válida. Em seguida, o sistema estima a temperatura dos pixels pela barra
térmica lateral e conta como quentes os pixels a partir de 90% da escala por
padrão: `Tmin + 0,90 × (Tmax − Tmin)`. O usuário ainda pode ajustar esse limiar
no slider antes do cálculo. Em cada imagem, um seletor
permite controlar o limiar pela porcentagem da escala (modo padrão) ou
diretamente pela temperatura em °C. Ao alternar o modo, o sistema preserva o
limiar equivalente; a análise e os resultados continuam usando a temperatura
convertida em °C.

Dentro de cada região, o GrabCut separa os pixels da perna do fundo. A prévia
exibe a máscara sobre a imagem e oferece dois ajustes manuais: **Corrigir
áreas**, para redesenhar o retângulo de cada perna, e **Corrigir segmentação**,
com pincel verde para incluir perna e vermelho para excluir fundo. Cada ajuste
recalcula as métricas. A barra térmica vertical também é localizada
automaticamente e destacada na prévia. Dentro de **Corrigir áreas**, a opção
**Barra de cores** permite redesenhar sua caixa; a paleta extraída dessa região é a fonte usada
para converter as cores da imagem em temperaturas aproximadas. Para cada perna
e para os totais de frente/verso, a tela
apresenta a quantidade de pixels quentes, a área total segmentada e o percentual
`pixels quentes ÷ área segmentada × 100`. A área do retângulo não é usada como
denominador. Ao lado da máscara, uma segunda prévia usa fundo preto e mantém
visíveis somente os pixels que pertencem às pernas segmentadas e alcançam o
limiar térmico selecionado.

Cada perna também pode ser dividida em coxa, joelho, canela e pé. Na seção
**Divisão anatômica**, selecione a orientação horizontal ou vertical, indique
onde começa a coxa e arraste os três limites no pop-up **Editar divisões na imagem**.
Por padrão, a coxa começa em cima nas imagens verticais. Os percentuais internos
crescem da coxa ao pé mesmo em imagens invertidas. As linhas e
os números das partes aparecem na prévia; a contagem usa somente pixels da
máscara. A soma das quatro regiões corresponde ao total da perna. Uma região
com área zero indica que ela não está visível na máscara. Essas métricas são
temporárias na interface; não são enviadas ao banco.

Ao confirmar o registro, uma única transação grava em `public.medida_valor` as
medidas `MASSA`, `EVA_DOR`, `PERNA_DIREITA_FRENTE`,
`PERNA_ESQUERDA_FRENTE`, `PERNA_DIREITA_VERSO`,
`PERNA_ESQUERDA_VERSO`, `SOMA_FRENTE`, `SOMA_VERSO` e, quando preenchida,
`OBSERVACOES`. Todas recebem o mesmo jogador e timestamp. Uma coleta já
existente para o mesmo jogador e data é rejeitada para evitar duplicidade.

As fichas legadas em PDF, PNG ou JPEG são enviadas ao LlamaParse Cloud, usando
o modo `agentic`, e apresentadas em uma grade editável. Configure
`LLAMA_CLOUD_API_KEY` no ambiente da API ou no `.env` da raiz. Se a chave estiver ausente, a
API falhar ou a resposta não contiver a tabela esperada, o sistema utiliza
automaticamente o extrator local com OpenCV e Tesseract e informa o fallback na
tela. O nome reconhecido é preservado para conferência e a coluna Jogador aceita
somente cadastros existentes, sugeridos pelas mesmas regras de correspondência
de nome usadas no GPS. Após revisão, as fichas podem ser gravadas em lote usando
`MASSA`, `EVA_DOR`, `SOMA_FRENTE`, `SOMA_VERSO` e `OBSERVACOES`; as quatro
medidas individuais das pernas permanecem ausentes porque o documento original
não possui essa separação. O lote é atômico: qualquer erro impede todas as
inserções daquele envio.

As imagens e os documentos enviados nunca são armazenados no banco. Os arquivos
temporários locais usados no envio ao LlamaParse são removidos ao final; o
tratamento e a retenção no serviço externo seguem as políticas do LlamaCloud.
Somente as medidas revisadas são persistidas pelo protótipo. A conversão
de cor em temperatura e a identificação das caixas ainda são experimentais e
devem ser validadas antes do uso definitivo.
