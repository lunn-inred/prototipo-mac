# Configuração do ambiente

[← Voltar ao README](../README.md)

## Variáveis e responsabilidades

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

## Modelo local semipronto

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


## Segurança

A chave do modelo é somente para desenvolvimento local. Substitua-a por uma
chave própria ao hospedar a API. Nunca publique `.env`, `secrets.toml` ou
credenciais do banco. Distribuir o binário com `.env` concede acesso ao banco;
restrinja isso a máquinas confiáveis. Para uso externo, hospede a API.

As variáveis do processo têm prioridade sobre o `.env`. Na hospedagem Streamlit,
Secrets é uma alternativa somente para URL, chave e timeout do cliente.
Veja [hospedagem web](web.md#deploy-no-streamlit-community-cloud).
