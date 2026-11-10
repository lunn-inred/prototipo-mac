# Configuração do ambiente

[← Voltar ao README](../README.md)

## Variáveis e responsabilidades

A execução local, a API integrada e o aplicativo desktop utilizam o único arquivo
`.env`. Em hospedagens do Streamlit, somente URL, chave e timeout do cliente
podem ser cadastrados em `frontend/streamlit/.streamlit/secrets.toml` ou no painel
de Secrets. Credenciais do banco e OCR pertencem ao ambiente da API.

| Variável | Processo | Finalidade |
|---|---|---|
| `MAC_ENVIRONMENT` | API | `development` (padrão), `test` ou `production` |
| `MAC_DB_TARGET` | API | `local` (padrão); `supabase` somente em produção explícita |
| `MAC_LOCAL_DB_*` | API/Compose | PostgreSQL local persistente; padrão `127.0.0.1:55433/mac_dev` |
| `SUPABASE_DB_*` | Exportação/API de produção | Origem remota read-only para cópia; ignorada pela aplicação em modo local |
| `LLAMA_CLOUD_API_KEY` | API | Extração principal de documentos legados |
| `MAC_API_KEY` | Ambos | Exige/envia o cabeçalho `X-API-Key`; se vazio, autenticação fica desativada para desenvolvimento |
| `MAC_API_CORS_ORIGINS` | API | Origens permitidas, separadas por vírgula |
| `MAC_API_BASE_URL` | Streamlit | URL pública ou interna da API |
| `MAC_API_TIMEOUT_SECONDS` | Streamlit | Timeout de chamadas longas, padrão 300 s |
| `MAC_ANALYSES_DIR` | API | Arquivo local de análises; padrão `./data/thermography` |
| `MAC_GOOGLE_CLIENT_ID` | Ambos | Ativa o login Google quando preenchido |
| `MAC_GOOGLE_CLIENT_SECRET` | API | Segredo do cliente OAuth; nunca enviar ao navegador |
| `MAC_GOOGLE_ALLOWED_EMAIL` | API | Única conta Google autorizada nesta fase |
| `MAC_GOOGLE_REDIRECT_URI` | API | Retorno OAuth cadastrado no Google Cloud |
| `MAC_GOOGLE_FRONTEND_URL` | API | URL da interface após o login |
| `MAC_GOOGLE_PUBLIC_API_URL` | Streamlit | URL da API alcançável pelo navegador para iniciar o login |
| `MAC_GOOGLE_TOKEN_FILE` | API | Arquivo privado do token Drive; padrão `data/credentials/google-drive.json` |
| `MAC_GOOGLE_DESKTOP_CLIENT_ID` e `MAC_GOOGLE_DESKTOP_CLIENT_SECRET` | API desktop | Cliente OAuth Desktop app para retorno local em porta variável |

## Modelo local semipronto

API, Streamlit e launcher desktop utilizam o mesmo arquivo `.env` na raiz do
projeto. Você pode copiá-lo do modelo:

```bash
cp .env.example .env
```

Ou criar `.env` e copiar o modelo abaixo. O banco local já está preenchido;
campos remotos são necessários somente para exportar uma nova cópia da nuvem.
A chave do Llama Cloud é opcional. Não sobrescreva um `.env` já configurado:

```env
# Desenvolvimento: não acessa o Supabase
MAC_ENVIRONMENT=development
MAC_DB_TARGET=local
MAC_LOCAL_DB_HOST=127.0.0.1
MAC_LOCAL_DB_PORT=55433
MAC_LOCAL_DB_NAME=mac_dev
MAC_LOCAL_DB_USER=mac_dev
MAC_LOCAL_DB_PASSWORD=mac_dev_local

# Origem remota apenas para exportação explícita
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
MAC_ANALYSES_DIR=./data/thermography
```

O inicializador repassa automaticamente a URL e a chave da API local para o
Streamlit. Não é necessário criar ou repetir configurações em outro arquivo.
Inicie o PostgreSQL com `docker compose up -d --wait db-dev`. Na primeira
instalação, restaure a cópia seguindo [Banco local](local-database.md). O Compose
ajusta o host da API para `db-dev` e a porta para `5432` automaticamente. As
credenciais reais da origem não devem ser enviadas ao Git.

A configuração antiga contendo apenas `SUPABASE_DB_*` não ativa acesso remoto:
os padrões locais também se aplicam a ela. Para produção remota intencional,
configure **ambos** `MAC_ENVIRONMENT=production` e `MAC_DB_TARGET=supabase`.


## Segurança

A chave do modelo é somente para desenvolvimento local. Substitua-a por uma
chave própria ao hospedar a API. Nunca publique `.env`, `secrets.toml` ou
credenciais do banco. Distribuir o binário com `.env` concede acesso ao banco;
restrinja isso a máquinas confiáveis. Para uso externo, hospede a API.

As variáveis do processo têm prioridade sobre o `.env`. Na hospedagem Streamlit,
Secrets é uma alternativa somente para URL, chave e timeout do cliente.
Veja [hospedagem web](web.md#deploy-no-streamlit-community-cloud).

## Login Google em teste local

No cliente OAuth **Web application** do Google Cloud, cadastre exatamente
`http://localhost:8000/auth/google/callback` em **Authorized redirect URIs**.
Para o primeiro teste, execute API e Streamlit no mesmo computador e abra
`http://localhost:8501`. No `.env` da raiz, preencha:

```env
MAC_GOOGLE_CLIENT_ID=cole_o_client_id
MAC_GOOGLE_CLIENT_SECRET=cole_o_client_secret
MAC_GOOGLE_ALLOWED_EMAIL=conta_do_mac@example.org
MAC_GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
MAC_GOOGLE_FRONTEND_URL=http://localhost:8501
MAC_GOOGLE_PUBLIC_API_URL=http://localhost:8000
```

O ID e o secret não devem ser enviados por chat nem versionados. Ao preencher
`MAC_GOOGLE_CLIENT_ID`, todas as rotas `/api/v1` passam a exigir uma sessão
Google válida além de `MAC_API_KEY`; se faltar outra variável, o login falha
fechado. A primeira autorização pede `openid`, `email`, `profile` e
`drive.file`, cria **MAC Backups** no Meu Drive da conta autorizada e salva o
token de renovação e o ID da pasta no arquivo privado em `data/credentials/`.
O arquivo não entra no Git nem na imagem Docker. A pasta e o token preparam o
backup, mas **o envio automático dos arquivos ainda não foi implementado**.

No Compose, crie `data/credentials/` no host antes de iniciar os serviços e
garanta escrita ao usuário do container. O teste com `localhost` funciona apenas no computador servidor. Para dois
computadores, configure um endereço HTTPS estável, um proxy para Streamlit e
API, e atualize as três URLs acima e o redirect do cliente OAuth. As sessões
ficam na memória da API e expiram após 12 horas, reinício da API ou perda da
sessão do navegador; por enquanto use
um processo de API. No Google Auth Platform em **External + Testing**, o token
Drive expira em sete dias e requer novo consentimento.
