# Testes e validação

[← Voltar ao README](../README.md)

## Suíte automatizada

```bash
python -m unittest discover -v
```

A suíte cobre regras de domínio, persistência simulada, importações e contratos
HTTP. A integração real com LlamaParse só roda quando explicitamente habilitada.

Para verificar especificamente o carregamento sob demanda e os caches:

```bash
python -m unittest frontend.tests.test_loading_performance -v
```

Esses testes usam AppTest, a API via TestClient e repositórios simulados, bloqueando
conexões PostgreSQL reais. Verificam que painéis fechados não buscam históricos
nem executam estatísticas, que Editar/Excluir compartilham o cache de coletas,
que gravações bem-sucedidas invalidam referências e que credenciais diferentes
não compartilham o mesmo cache. Também verificam o reaproveitamento do cliente
HTTP. As contagens de chamadas não representam medições de latência do Supabase.

## Testes locais com PostgreSQL

A fixture `backend/tests/fixtures/schema.sql` reproduz o modelo necessário aos
testes. Não é um dump completo do Supabase nem uma migração de produção.
Com `.env` presente na raiz, inicie somente o banco descartável:

```bash
docker compose -p mac-tests --profile test up -d --wait postgres-test
```

```bash
MAC_TEST_DB_ENABLED=1 \
SUPABASE_DB_HOST=127.0.0.1 SUPABASE_DB_PORT=55432 \
SUPABASE_DB_NAME=mac_test SUPABASE_DB_USER=mac_test \
SUPABASE_DB_PASSWORD=mac_test_local SUPABASE_DB_SSLMODE=disable \
python -m unittest backend.tests.test_local_postgres backend.tests.test_web_ui -v
```

Esses testes recusam hosts externos e bancos diferentes de `mac_test`.
Para testar também os processos Docker com esse banco:

```bash
docker compose -p mac-tests -f compose.yaml -f compose.test.yaml \
  --profile test up --build -d --wait
```

O override força as credenciais locais. Frontend: porta 18501; API: 18000;
PostgreSQL: 55432. A chave da API vem do `.env`. Execute uma instância de teste
por vez, pois as portas são fixas. Ao terminar:

```bash
docker compose -p mac-tests -f compose.yaml -f compose.test.yaml --profile test down
```

O banco de teste não tem volume persistente: remover o container descarta seus dados.

## Limites da validação

Para reproduzir o dimensionamento dos diálogos sem API nem banco:

```bash
python -m streamlit run frontend/tests/fixtures/dialog_browser_app.py
```

Clique em **Abrir** e compare a primeira abertura com a reabertura. A legenda
`MEASURED` mostra os limites recebidos do navegador. Essa tela é apenas uma
fixture de diagnóstico, não faz parte da navegação do produto.

Os testes de interface usam Streamlit AppTest e simulam o retorno do canvas.
Eles verificam navegação, rascunho, prévias e atualização das divisões, mas não
substituem uma revisão visual do arraste no navegador/WebView. Testes opcionais
com PostgreSQL e LlamaParse só executam quando explicitamente habilitados.
Não use credenciais do Supabase de produção nos testes de escrita.
