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
| `GET /api/v1/thermography/analyses?athlete_id=` | Lista análises locais com miniatura | Não |
| `GET /api/v1/thermography/analyses/{athlete_id}/{collected_at}/{analysis_id}` | Carrega imagens, máscaras e matrizes de uma análise | Não |

Uploads usam `multipart/form-data`; os demais corpos usam JSON. Os esquemas,
campos obrigatórios e exemplos para testar cada chamada ficam sempre atualizados
na página `/docs`.
Os formatos de imagens/matrizes e as operações permitidas estão em
[Contratos de processamento](#contrato-de-termografia).

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
