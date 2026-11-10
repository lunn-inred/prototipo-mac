# Execução web e hospedagem

[← Voltar ao README](../README.md)

## Preparação

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

## Execução separada da API e do Streamlit

O banco padrão é o PostgreSQL local. Inicie-o com
`docker compose up -d --wait db-dev` e confira a [restauração inicial](local-database.md).

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

## Docker

Com o `.env` preenchido na raiz:

```bash
mkdir -p data/thermography data/credentials
docker compose up --build -d
docker compose ps
docker compose logs -f backend frontend
```

Abra `http://localhost:8501`; API e Swagger ficam em `http://127.0.0.1:8000/docs`.
O frontend usa `http://backend:8000` na rede interna. Somente o backend recebe
as credenciais do banco. Tesseract e seus idiomas são instalados na imagem do
backend. Os containers executam com usuário sem privilégios.

O Compose também inicia `db-dev` (PostgreSQL 17), com volume persistente e porta
`127.0.0.1:55433`. O backend usa `db-dev:5432`. O início dos serviços não importa
nenhum dump automaticamente. `docker compose down` preserva a cópia do banco;
não use `down -v` se quiser manter seus dados. Para produção remota, é necessário
configurar explicitamente `MAC_ENVIRONMENT=production` e `MAC_DB_TARGET=supabase`.

```bash
docker compose down
```

O Docker é opcional para desenvolvimento e implantação web. O executável
desktop continua usando processos Python locais e não exige Docker do usuário.
O procedimento de teste com PostgreSQL isolado está em
[Testes locais](testing.md).

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

## Logo

Para exibir a identidade do MAC na barra lateral, coloque a imagem PNG em
`frontend/streamlit/assets/logo_mac.png`. O arquivo é carregado automaticamente quando existe; sua
ausência não impede a execução do protótipo.

Veja também [configuração](configuration.md), [desktop](desktop.md) e [API](api.md).

## Login Google

O teste inicial do login com Google usa o navegador no mesmo computador da API
e do Streamlit. Configure o cliente OAuth e o `.env` conforme
[Login Google em teste local](configuration.md#login-google-em-teste-local).
O botão **Entrar com Google** só aparece após preencher `MAC_GOOGLE_CLIENT_ID`.
Antes do login, a navegação contém somente a página **Entrar**; as páginas de
trabalho não aparecem no menu nem ficam disponíveis por seus endereços. Ao
reabrir o app, a sessão é verificada na API antes de mostrar a navegação.
O fluxo cria a pasta **MAC Backups** e guarda a autorização do Drive no backend;
o envio periódico dos backups ainda não faz parte desta etapa.

O retorno OAuth de `localhost:8000` não serve para o segundo computador. O modo
desktop/WebView, que usa portas variáveis, também não participa deste primeiro
teste. Para o uso em rede, será preciso configurar um endereço HTTPS estável,
um proxy para os dois serviços e atualizar o cliente OAuth.
