
# Testes e validação

[← Voltar ao README](../README.md)

## Suíte automatizada

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

Os backups têm cobertura em `backend.tests.test_backup_bundle`,
`backend.tests.test_backup_drive`, `backend.tests.test_backup_routes` e
`frontend.tests.test_backups_page`, sem usar o Drive real. No banco descartável,
`backend.tests.test_backup_postgres` testa restauração dos dados e imagens,
preservação de medidas locais mais recentes, conflito de IDs e rollback em
falha na publicação dos arquivos. Execute com as mesmas variáveis seguras abaixo.
Esses testes usam somente arquivos temporários e recusam qualquer banco diferente
de `mac_test`; não os direcione à cópia persistente.

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
O teste de edição térmica cobre substituição, mudança de atleta/data,
confirmação de conflito, revisão desatualizada, preservação de saltos e
rollback de banco/arquivos em falha de gravação. As imagens usam diretórios
temporários. Os testes AppTest de histórico e registro verificam seleção,
restauração das máscaras/temperaturas, cancelamento e confirmação de sobrescrita.
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

Os testes `test_thermal_drafts.py` e `test_thermal_draft_flow.py` cobrem confirmação
e cancelamento, compatibilidade da API com rascunhos antigos sem atleta,
bloqueio na interface por toast quando falta jogador, retorno à primeira etapa
sem perda de dados/imagens, upload de uma única vista, retomada em
outra sessão, preservação de matrizes/ajustes e revisão desatualizada. O teste do
assistente verifica que a coluna editável de data é enviada ao salvar, sem
diálogo de data. Após sucesso completo ou parcial, verificam campos/imagens
limpos, retorno à primeira etapa e toast de confirmação exibido uma única vez;
falhas e cancelamentos mantêm o preenchimento. Usam diretórios temporários e
API interna de teste.
O salvamento na primeira etapa verifica também o sinal `set_value` enviado aos
widgets: o estado Python vazio, sozinho, não comprova que o navegador limpou os
campos já montados.
Os testes de reabertura usam a mesma sessão após a limpeza e após preencher outro
atleta, verificando restauração explícita dos widgets, campos ausentes e EVA zero.

`test_thermal_save_readiness.py` verifica completude nas etapas anteriores ao
resumo, reabertura de análise completa sem confirmação indevida e rejeição de
caches antigos após mudar imagem, rotação, caixas, barra ou escala. Também cobre
EVA zero, metadados atuais e o contrato de armazenamento das matrizes restauradas.

Com PostgreSQL descartável habilitado, `test_thermal_drafts_postgres.py` cobre
promoção do rascunho mantendo UUID, edição incompleta preservando a versão
completa em arquivos, atualização imediata de medidas parciais no SQL, mudança
de jogador/data sem duplicação, EVA zero, omissão de campos ausentes, contagens
recalculadas, rollback SQL/arquivos, sobrescrita explícita e restauração de
backup preservando análise parcial, medidas e atleta.

Os testes de OAuth em `backend/tests/test_google_auth.py` simulam as respostas do
Google e usam arquivos de credenciais temporários. Cobrem a pasta configurada,
tokens independentes web/desktop, acesso negado, lixeira, destino sem escrita,
falhas de rede e ausência de criação automática. Não comprovam o acesso real
à pasta da equipe: após preencher `MAC_GOOGLE_BACKUP_FOLDER_ID`, faça novo login
nos dois modos e confirme que a autorização `drive.file` permite esse destino.

Para reproduzir o dimensionamento dos diálogos sem API nem banco:

```bash
python -m streamlit run frontend/tests/fixtures/dialog_browser_app.py
```

Clique em **Abrir** e compare a primeira abertura com a reabertura. A legenda
`MEASURED` mostra os limites recebidos do navegador. Essa tela é apenas uma
fixture de diagnóstico, não faz parte da navegação do produto.

Para conferir o popup de análises anteriores com listas longas de atletas e
análises fictícios, sem API nem banco:

```bash
python -m streamlit run frontend/tests/fixtures/history_browser_app.py
```

Confira as margens superior/inferior, o acesso ao último cartão pela rolagem e
o botão **Voltar aos atletas** em diferentes alturas de janela. Essa fixture
reutiliza os estilos da página térmica para reproduzir seus limites internos.

Os testes de interface usam Streamlit AppTest e simulam o retorno do canvas.
Eles verificam navegação, rascunho, prévias e atualização das divisões, mas não
substituem uma revisão visual do arraste no navegador/WebView. Testes opcionais
com PostgreSQL e LlamaParse só executam quando explicitamente habilitados.
Não use credenciais do Supabase de produção nos testes de escrita.
