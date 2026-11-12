# API HTTP e contratos

[← Voltar ao README](../README.md)

## Visão geral

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
| `GET /api/v1/athletes/{athlete_id}` | Consulta um atleta | Não |
| `POST /api/v1/athletes` | Cadastra atleta | Sim |
| `PUT /api/v1/athletes/{athlete_id}` | Atualiza atleta, preservando `nome_alternativo` | Sim |
| `PATCH /api/v1/athletes/{athlete_id}/deactivate` | Desativa atleta sem excluir cadastro ou medições | Sim |
| `PATCH /api/v1/athletes/{athlete_id}/reactivate` | Reativa o cadastro existente | Sim |
| `GET /api/v1/players/dashboard` | Dados do mural | Não |
| `POST /api/v1/athletes/match` | Correlaciona um nome ao cadastro | Não |
| `POST /api/v1/analytics/{operation}` | Calcula indicadores e estatísticas | Não |
| `GET /api/v1/jumps` | Registros da view de saltos | Não |
| `GET /api/v1/jumps/collections` | Lista coletas de salto editáveis | Não |
| `POST /api/v1/jumps/collections` | Cadastra uma coleta de salto | Sim |
| `PUT /api/v1/jumps/collections/{athlete_id}/{collected_at}` | Substitui uma coleta de salto | Sim |
| `DELETE /api/v1/jumps/collections/{athlete_id}/{collected_at}` | Exclui uma coleta de salto | Sim |
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
| `POST /api/v1/thermography/analyses` | Salva imagens e dados da análise localmente | Não |
| `POST /api/v1/thermography/analyses/register` | Registra medidas no banco local e arquivos da timeline em uma operação | Sim |
| `PUT /api/v1/thermography/analyses/{athlete_id}/{collected_at}/{analysis_id}` | Substitui uma análise salva, podendo mudar atleta/data | Sim |
| `GET /api/v1/thermography/analyses?athlete_id=` | Lista análises locais com miniatura | Não |
| `GET /api/v1/thermography/analyses/{athlete_id}/{collected_at}/{analysis_id}` | Carrega imagens, máscaras e matrizes de uma análise | Não |
| `POST /api/v1/thermography/drafts` | Salva análise parcial e suas medidas disponíveis no banco local | Sim, se houver atleta |
| `GET /api/v1/thermography/drafts/{draft_id}` | Carrega o estado de um rascunho | Não |
| `GET /api/v1/backups?desktop=false` | Lista pacotes MAC na pasta configurada do Drive | Não |
| `POST /api/v1/backups` | Inicia snapshot local e envio de um novo pacote ao Drive | Arquivos/Drive |
| `POST /api/v1/backups/restore` | Baixa e restaura o banco local com reconciliação das análises | Sim, exige confirmação |
| `GET /api/v1/backups/jobs/{id}` | Progresso/resultado da operação em segundo plano | Não |

Uploads usam `multipart/form-data`; os demais corpos usam JSON. Os esquemas,
campos obrigatórios e exemplos para testar cada chamada ficam sempre atualizados
na página `/docs`.
Os formatos de imagens/matrizes e as operações permitidas estão em
[Contratos de processamento](#contrato-de-termografia).

## Contrato de backups

As rotas de backup exigem chave de API e sessão Google mesmo no desenvolvimento;
operam exclusivamente em `MAC_DB_TARGET=local`. A listagem retorna metadados do
Drive (`id`, `name`, `size`, `createdTime`, `properties`). O campo
`properties.sha256` identifica o conteúdo que será confirmado para restauração.

`POST /api/v1/backups` recebe `{"desktop": false}`. `POST .../restore` recebe:

```json
{
  "desktop": false,
  "file_id": "ID_DO_ARQUIVO_DE_BACKUP",
  "expected_sha256": "HASH_SHA256_DE_64_CARACTERES_HEXADECIMAIS",
  "confirm": true
}
```

O hash deve ser o valor real da listagem. `confirm` omitido/falso retorna 422;
o arquivo precisa continuar pertencendo à pasta configurada e ter o hash
confirmado. `desktop=true` seleciona o token nativo quando disponível, sem
compartilhá-lo com o cliente OAuth Web. As respostas de início são `202`, com
`id`, `kind`, `status` e `message`; consulte `GET .../jobs/{id}` até `completed`
ou `failed`. Em sucesso, `result` informa contagens e caminho da cópia local ou
preventiva, nunca credenciais. Não repita automaticamente um POST após perder
a resposta; confira o estado para não iniciar duas restaurações.

Uma tarefa por vez por processo (409 em tentativa simultânea). Enquanto aplica
uma restauração ou copia o snapshot, as rotas normais de dados retornam 423;
os endpoints de listagem/polling de backups continuam disponíveis. As tarefas
não sobrevivem ao reinício da API; um diário de restauração pendente mantém
os dados bloqueados até revisão. Regras, formato e limites: [Backups](backups.md).

## Contrato de termografia

O frontend organiza a coleta em sete etapas com rascunho na sessão
(`components/thermography/wizard.py`). O campo opcional `image_rotation`
de `/thermography/segment` aceita 0, 90, 180 ou 270 graus anti-horários:
`image` já deve estar rotacionada. O backend localiza as regiões na orientação
original e transforma as caixas, preservando a lateralidade e a ordem da paleta.
`operations/image_regions` recebe imagem, vista e rotação e retorna as caixas
antes da segmentação. Correções manuais usam coordenadas da imagem rotacionada.

`POST /api/v1/thermography/segment` recebe uma análise completa de uma vista:

- `image`: `{ "type": "image", "png": "<PNG em base64>" }`;
- `view`: `front` ou `back`;
- `image_rotation`: rotação anti-horária já aplicada à imagem, padrão `0`;
- `minimum_temperature`, `maximum_temperature`, `threshold`, em °C;
- `manual_boxes`: caixas opcionais `right` e `left`;
- `colorbar_box`: caixa opcional da paleta;
- `seeds`: matrizes opcionais de correção de cada perna.

Uma caixa contém `left`, `top`, `width`, `height` em pixels da imagem enviada,
com orientação EXIF corrigida e rotação aplicada. Seeds usam `int8`: `1` inclui, `-1` exclui e `0`
permanece desconhecido. O cliente converte coordenadas do canvas antes do envio.

O resultado contém caixas automáticas/utilizadas, máscaras, temperaturas,
métricas de área/pixels/percentual e previews. Sem caixas detectadas, a API
fornece regiões iniciais para correção. A escala, o limiar e as regiões são
validados no backend. O Swagger apresenta os modelos de entrada e saída.

Matrizes usam bytes em ordem C, comprimidos com zlib e codificados em base64:

```json
{"type":"array","dtype":"float32","shape":[200,320],"data":"<base64>"}
```

Os tipos numéricos são little-endian nas plataformas de build suportadas.
O decoder limita o tamanho de descompressão e valida dimensões e dtype.
Não há pickle. Datas usam `{ "type": "date", "value": "2026-10-08" }`.
Mapas com chaves numéricas ou datas usam `type: mapping` e pares `items`.

`POST /api/v1/thermography/operations/{operation}` é o contrato granular para
interação. Recebe `{ "args": [...], "kwargs": {...} }` e retorna
`{ "result": ... }`, usando a codificação acima. Operações autorizadas:

| Operação | Finalidade |
|---|---|
| `leg_part_metrics` | Métricas de coxa, joelho, canela e pé e limites de divisão |
| `timeline_view_at_threshold` | Recalcular máscaras quentes e métricas |
| `compare_hot_masks` | Mapa de pixels novos, persistentes e resolvidos |
| `summarize_pair` | Totais e percentuais de frente/verso |
| `detect_leg_boxes`, `detect_colorbar_box`, `image_regions` | Detectar regiões e transformar caixas após rotação |
| `segment_leg_mask` | Segmentar com correções opcionais |
| `temperature_matrix`, `count_hot_pixels` | Conversão térmica e contagem |
| `temperature_from_scale_percentage`, `scale_percentage_from_temperature` | Converter limiar |
| `annotate_boxes`, `segmentation_overlay`, `hot_pixels_overlay` | Previews |
| `segmented_image` | Adaptador de análise completa |

Para novos consumidores, prefira a rota tipada `/segment` para análise completa.
`leg_part_metrics` aceita `region_box` opcional para manter os limites das partes
relativos à caixa escolhida antes do GrabCut. A contagem continua restrita à máscara.
As operações granulares preservam a interação do protótipo existente.

As rotas de processamento são stateless. Para persistir uma análise, utilize
`POST /api/v1/thermography/analyses`: informe `athlete_id`, `athlete_name`,
`collected_at` (ISO), `mass`, `pain_score`, `observations` e `views` com
`front`/`back`. Cada vista contém `image`, `temperatures`, `segmentation_masks`
(`right`/`left`), `boxes`, Tmin/Tmax (`minimum_temperature`/`maximum_temperature`),
`default_threshold`, `part_settings`, `image_rotation`, `original_filename` e
`colorbar_box` opcional. Imagens/matrizes usam o formato de transporte descrito acima.
O backend valida e recalcula métricas antes de gravar. Resposta `201`: resumo
com UUID, data e miniatura. Listagem retorna resumos; detalhe retorna também
`views` e `metadata`. As três rotas exigem a mesma chave da API e não consultam
nem alteram o banco. Data e UUID identificam arquivos, não coletas SQL.
O arquivo local permite recuperar as imagens após encerrar a sessão;
o histórico de medidas do banco continua sem imagens.

### Registro único de análise

O botão **Salvar análise**, quando completa, usa `POST /api/v1/thermography/analyses/register`.
O corpo tem o mesmo formato de `analyses`, mas `mass` e `pain_score` são
obrigatórios; EVA zero é válido. `observations` é opcional. `athlete_name` deve
ser enviado, mas o nome persistido é o do cadastro SQL. A data informada é usada
no banco e no arquivo. As contagens não são recebidas como fonte de verdade:
o backend calcula os pixels sobre máscaras e temperaturas de cada vista.

Resposta `201`: `{ "analysis": <resumo da análise>, "inserted_measurements": 8 }`
(9 medidas quando há observações), com imagens codificadas pelo transporte padrão.
Retorna `409` para jogador/data já registrado, `422` para dados inválidos ou
destino não local e `503` para falha de banco/arquivos. O registro usa uma
transação SQL e compensação dos arquivos em falhas normais; não é uma transação
distribuída tolerante a desligamento abrupto. Veja [registro unificado](thermography.md#registro-unificado).

As rotas antigas permanecem disponíveis para compatibilidade. Não execute a
rota antiga de medidas e a rota unificada para a mesma coleta: isso gera conflito.

### Rascunhos térmicos persistentes

`POST /api/v1/thermography/drafts` recebe `state`, `draft_id` e
`expected_revision` opcionais, mais `overwrite` (padrão `false`). `state` usa o
transporte de matrizes existente e contém `step` (0–6), `draft` (`player`,
`mass`, `pain`, `notes`, `collected_at`), `uploads` por `front`/`back` (nome,
conteúdo original em base64 e rotação), `items` com os ajustes de cada imagem e
`source` opcional com a identidade/revisão da análise completa em edição.
Campos de coleta podem ser nulos. Não aceita pickle nem objetos executáveis.

A resposta contém o resumo com `id`, `created_at` (revisão) e `is_draft: true`.
Para atualizar, envie o ID e a revisão recebidos. `GET .../drafts/{draft_id}`
retorna também `state`. Exige chave da API e destino local; valida o atleta
selecionado e insere as medidas disponíveis nas tabelas existentes. Não exige
massa, EVA ou ambas as imagens para salvar; omite medidas ausentes, preservando
EVA zero. Contagens disponíveis na etapa de cálculo são recalculadas no backend.
Novos salvamentos substituem as medidas da mesma coleta; mudanças de jogador/data
movem os dados, sem duplicar. Por compatibilidade, esta rota ainda aceita um
rascunho sem atleta somente em arquivos, sem conexão SQL; a interface, porém,
bloqueia esse caso antes da chamada, mostra um toast e pede a seleção do jogador.
Uma análise já vinculada ao
banco não pode perder o jogador ao ser salva.
Conflitos de atleta/data e revisão usam os mesmos códigos `409` da análise
completa; `overwrite` não ignora revisões desatualizadas.

`GET .../analyses?athlete_id=<id>&include_drafts=true` inclui rascunhos; o ID `0`
lista apenas os ainda sem atleta. Sem `include_drafts`, a listagem permanece
restrita às análises completas, como exige a timeline. Uma edição em rascunho
aparece no histórico no lugar da versão completa. Atualiza as medidas SQL
imediatamente, preserva internamente os arquivos completos antigos até a
finalização e retira essa versão antiga da listagem usada pela timeline.
O resumo do rascunho inclui `sql_pair` e `sql_revision` para identificar a coleta
parcial e detectar alterações concorrentes, sem adicionar colunas ao banco.

Na finalização, envie `draft_id` e `draft_revision` no `POST .../analyses/register`
(novo registro) ou no `PUT` da origem (edição existente). O backend confere as
revisões e a origem, mantém o UUID e só remove o rascunho depois do sucesso.
Falha de registro preserva o rascunho para nova tentativa. O `POST` retorna `201`
e o `PUT`, `200`, com o envelope de registro unificado. A data vem da coluna
editável do resumo; nenhuma chamada separada para escolha de data é necessária.

### Edição e sobrescrita de análise

O `PUT` recebe o mesmo corpo do registro unificado e `expected_revision`, com o
`created_at` retornado pelo detalhe/listagem da análise aberta. A URL identifica
a origem; `athlete_id` e `collected_at` no corpo definem o destino, que pode mudar.
A resposta `200` tem o mesmo envelope do registro. O UUID é preservado e
`created_at` é atualizado para detectar edições concorrentes e renovar caches.
Não há histórico permanente de versões. Uma análise antiga somente em arquivos
também pode ser editada; ao salvar, suas medidas passam a existir no banco local.

Se outro registro existir para o atleta/data de destino, a API responde `409`:

```json
{"detail":{"code":"analysis_date_conflict","message":"Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?"}}
```

Somente após a confirmação do usuário, repita a requisição com `overwrite: true`.
O `POST .../register` também aceita essa confirmação. Um `PUT` com revisão
desatualizada retorna `409` com código `analysis_changed`; nesse caso é necessário
reabrir a análise, não forçar a sobrescrita.

A substituição remove apenas medidas do grupo termografia dos pares atleta/data
envolvidos; GPS e saltos são preservados. Arquivos antigos ficam temporariamente
em pastas ocultas `.replacing_*`, com recuperação em falhas normais, e são
removidos após o commit. Banco e disco não têm transação distribuída: uma queda
abrupta exige conferir banco e essas pastas antes de reenviar. Faça backup dos dois.

## Indicadores e importações

`POST /api/v1/analytics/{operation}` usa o mesmo envelope `args`/`kwargs` e
retorna `result`. A lista permitida inclui:

- `player_data.group_measurements`, `player_data.metric_summary`,
  `player_data.latest_eva`, `player_data.eva_classification`;
- `jump_data.average`, `jump_data.metric_summary`, `jump_data.build_jump_comparison`;
- `gps_data.average`, `gps_data.opponents_by_date`;
- `chart_statistics.daily`, `population_deviation`.

`POST /api/v1/gps/editor-rows` recebe `filename` e `rows` e retorna linhas
correlacionadas ao cadastro. `POST /api/v1/athletes/match` recebe `name` e retorna
`athlete_id` ou `null`. Nomes desconhecidos/ambíguos exigem seleção manual.
Os demais endpoints CRUD/importação estão na tabela acima e em `/docs`.
