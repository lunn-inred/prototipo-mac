# Testes e validação

[← Voltar ao README](../README.md)

## Suíte automatizada

Regressões da segmentação watershed (sem banco, OCR ou dados privados):

```bash
python -X utf8 -m unittest backend.tests.test_watershed backend.tests.test_thermal_rotation backend.tests.test_processing_contracts backend.tests.test_analysis_archive frontend.tests.test_thermal_wizard -v
```

Validam a faixa circular de vermelho, linhas R1/R2 sem inclusão do fundo,
lateralidade frente/costas, rotação já aplicada, pincéis, recuperação por regiões
manuais, contagens via HTTP, referências anatômicas e leitura de arquivos GrabCut
sem resegmentação. A suíte usa UTF-8 explícito para rodar também no Windows.
`scripts/validate_watershed.py` permite repetir manualmente o pipeline em lotes
locais, com `--session PASTA ROTACAO GLOB --output PASTA_SEPARADA` (repetível).
Esse replay usa escala ilustrativa para conferir os contratos e não mede precisão
anatômica ou temperatura clínica. Não roda sobre imagens reais como parte dos testes.

Na validação local da integração, 229 das 230 termografias dos quatro lotes
geraram máscaras; uma imagem com enquadramento fechado exigiu delimitação manual.
A correção da faixa vermelha reduziu o indicador de buracos internos nos lotes
FLIR de 1,270% para 0,068% e de 1,487% para 0,107%. Esse indicador mede apenas
pixels ausentes dentro dos contornos, não precisão anatômica. As imagens e as
galerias de validação ficam fora do versionamento em `data/watershed-validation/`.

```bash
python -m unittest discover -v
```

A suíte cobre regras de domínio, persistência simulada, importações e contratos
HTTP. A integração real com LlamaParse só roda quando explicitamente habilitada.
Os pacotes de teste desativam o OAuth configurado no `.env` para não usar a conta
Google real; os testes específicos de login ativam uma configuração simulada.

O registro térmico unificado é coberto por
`backend.tests.test_analysis_registration` e `frontend.tests.test_combined_registration`:
validam contagens persistidas, data, campos obrigatórios, uma única requisição,
conflitos, rollback SQL e compensação de arquivos. Quando PostgreSQL local está
habilitado, `test_combined_analysis_registration_and_file_failure_rollback` também
exercita essas garantias com gravação real no banco descartável `mac_test` e
imagens em diretório temporário, nunca na cópia persistente `mac_dev`.

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
MAC_ENVIRONMENT=test MAC_DB_TARGET=local \
MAC_LOCAL_DB_HOST=127.0.0.1 MAC_LOCAL_DB_PORT=55432 \
MAC_LOCAL_DB_NAME=mac_test MAC_LOCAL_DB_USER=mac_test \
MAC_LOCAL_DB_PASSWORD=mac_test_local \
python -m unittest backend.tests.test_local_postgres backend.tests.test_web_ui -v
```

Esses testes recusam hosts externos e bancos diferentes de `mac_test`.
Nunca aponte os testes destrutivos para o `mac_dev` persistente. A cópia de
desenvolvimento é descrita em [Banco local](local-database.md).
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
