# MAC Performance

Aplicação para cadastro de atletas e análise de saltos, GPS e termografia.
O frontend Streamlit consome uma API FastAPI, responsável pelos cálculos,
importações e acesso ao PostgreSQL/Supabase. A mesma interface funciona no
navegador ou em uma janela desktop (WebView).

## Sumário

- [Resumo do projeto](#resumo-do-projeto)
- [Preparação](#preparação)
- [Web — execução local](#web--execução-local)
- [Web — Docker](#web--docker)
- [Desktop — desenvolvimento](#desktop--desenvolvimento)
- [Desktop — standalone](#desktop--standalone)
- [Desktop — backend em Docker](#desktop--backend-em-docker)
- [API e endpoints](#api-e-endpoints)
- [Testes](#testes)
- Documentação detalhada:
  - [Configuração e modelo de .env](docs/configuration.md)
  - [Execução web, Docker e hospedagem](docs/web.md)
  - [Desktop, build e distribuição](docs/desktop.md)
  - [API — endpoints completos e contratos](docs/api.md)
  - [Arquitetura e estrutura de pastas](docs/architecture.md)
  - [Testes e PostgreSQL local](docs/testing.md)
  - [Jogadores e CRUD](docs/players.md)
  - [Saltos — importação, métricas e gráficos](docs/jumps.md)
  - [GPS — extração e importação](docs/gps.md)
  - [Termografia — etapas, cálculos, timeline e formulários](docs/thermography.md)

## Resumo do projeto

- `frontend/`: páginas Streamlit, componentes visuais e cliente HTTP.
- `backend/`: API, validações, processamento e persistência.
- `desktop/`: inicializador e empacotamento com PyInstaller.
- `infrastructure/`: imagens Docker; `docs/`: guias detalhados.

As métricas são consultadas nas views do banco. Escritas passam pelas validações
e transações da API. Imagens de termografia e a timeline ficam temporariamente
na sessão; somente medidas confirmadas são persistidas.

## Preparação

Use Python 3.10+ e execute os comandos a partir da raiz do repositório:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

No PowerShell, ative com `.venv\Scripts\Activate.ps1` e copie com
`Copy-Item .env.example .env`. Preencha as credenciais do banco no `.env`.
O [modelo único](.env.example) já aponta a API para `http://127.0.0.1:8000`.
Não sobrescreva um `.env` já configurado nem versione credenciais. A chave de
exemplo é somente para desenvolvimento; substitua-a ao hospedar a API.

Dependências de sistema, configuração semipronta e variáveis:
[configuração](docs/configuration.md), [web](docs/web.md) e [desktop](docs/desktop.md).
Para Docker web, não é necessário instalar Python ou dependências no host.

## Web — execução local

Com o ambiente ativado, execute em dois terminais:

```bash
# Terminal 1 — backend
uvicorn backend.mac_api.main:app --reload --host 127.0.0.1 --port 8000 --env-file .env
```

```bash
# Terminal 2 — frontend
python -m frontend.run
```

Interface: [localhost:8501](http://localhost:8501).
A API é obrigatória; ambos os processos utilizam o `.env` da raiz.
Hospedagem e instalação por processo: [guia web](docs/web.md).

## Web — Docker

Com Docker Compose instalado e o `.env` preenchido:

```bash
docker compose up --build -d
```

Interface: [localhost:8501](http://localhost:8501).
Apenas o backend recebe as credenciais do banco. Para encerrar:

```bash
docker compose down
```

Logs, portas e detalhes: [Docker web](docs/web.md#docker).

## Desktop — desenvolvimento

Instale as dependências adicionais:

```bash
python -m pip install -r requirements-desktop.txt
```

Inicie a API com o comando da [execução web local](#web--execução-local) e,
em outro terminal, abra a janela:

```bash
python desktop.py
```

Esse comando **não inicia a API**. Requisitos de WebView e bibliotecas por
sistema operacional: [guia desktop](docs/desktop.md).

## Desktop — standalone

O executável empacotado inicia API, Streamlit e WebView automaticamente,
sem exigir Python ou Docker no computador do usuário. Para gerar o binário:

```bash
python -m PyInstaller --clean --noconfirm desktop/desktop.spec
```

No Linux, coloque o `.env` ao lado do executável e abra:

```bash
cp .env dist/.env
"./dist/MAC Performance"
```

Cada build deve ser gerado no sistema operacional de destino. Distribua
credenciais do banco somente para máquinas confiáveis. Instruções para Windows,
macOS e empacotamento do OCR: [build e distribuição](docs/desktop.md).

## Desktop — backend em Docker

Com as dependências desktop instaladas e o `.env` preenchido:

```bash
docker compose up --build -d backend
python desktop.py
```

Mantenha `MAC_API_BASE_URL=http://127.0.0.1:8000`. Docker executa o backend;
a janela WebView roda localmente. Não existe um container da janela desktop.
Fechar a janela não encerra o container: use `docker compose stop backend`.
O binário standalone usa sua própria API e dispensa esse modo.

## API e endpoints

A API utiliza `/api/v1` e o cabeçalho `X-API-Key`, com a mesma `MAC_API_KEY`
configurada no cliente e no backend. Não publique a chave no navegador.

| Grupo | Rotas principais | Finalidade |
|---|---|---|
| Atletas | `/api/v1/athletes` | Cadastro, consulta, edição e exclusão |
| Mural | `/api/v1/players/dashboard` | Resumo dos jogadores |
| Saltos | `/api/v1/jumps`, `/api/v1/jumps/collections` | Métricas e gerenciamento de coletas |
| GPS | `/api/v1/gps`, `/api/v1/gps/import` | Métricas e importação revisada |
| Termografia | `/api/v1/thermography`, `/api/v1/thermography/segment` | Registro de medidas e análise de imagens |
| Indicadores | `/api/v1/analytics/{operation}` | Estatísticas e comparações |

Com a API local iniciada: [Swagger](http://127.0.0.1:8000/docs),
[ReDoc](http://127.0.0.1:8000/redoc), [OpenAPI](http://127.0.0.1:8000/openapi.json)
e [saúde do processo](http://127.0.0.1:8000/health).
A lista completa de métodos, rotas, autenticação e formatos está em [API HTTP](docs/api.md).

## Testes

```bash
python -m unittest discover -v
```

Testes opcionais de integração exigem habilitação explícita. Para validar
escritas, utilize somente o PostgreSQL local descartável, nunca o Supabase de
produção. Procedimentos e limites da validação: [guia de testes](docs/testing.md).
