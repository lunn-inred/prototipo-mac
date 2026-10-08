# Arquitetura e contratos

## Responsabilidades

`frontend/` contém Streamlit, componentes, apresentação e clientes HTTP.
`backend/` contém FastAPI, regras, processamento e PostgreSQL.
`desktop/` inicia os processos e empacota os mesmos módulos usados na versão web.
O frontend pode ser instalado sem OpenCV, SciPy, OCR e driver de banco;
o backend pode ser instalado sem Streamlit. Use os respectivos requirements.

Não há fallback para serviços locais no cliente. Todos os modos consomem HTTP.
Filtros, desenhos, formatação e sessão ficam no frontend; cálculos e validações
definitivas ficam no backend. Testes de arquitetura impedem imports cruzados.
As consultas de métricas utilizam views; verificações transacionais de escrita
continuam nas tabelas. Não é necessário alterar o schema do Supabase.

## Contrato de termografia

`POST /api/v1/thermography/segment` recebe uma análise completa de uma vista:

- `image`: `{ "type": "image", "png": "<PNG em base64>" }`;
- `view`: `front` ou `back`;
- `minimum_temperature`, `maximum_temperature`, `threshold`, em °C;
- `manual_boxes`: caixas opcionais `right` e `left`;
- `colorbar_box`: caixa opcional da paleta;
- `seeds`: matrizes opcionais de correção de cada perna.

Uma caixa contém `left`, `top`, `width`, `height` em pixels da imagem original
com orientação EXIF corrigida. Seeds usam `int8`: `1` inclui, `-1` exclui e `0`
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
| `detect_leg_boxes`, `detect_colorbar_box` | Detectar regiões |
| `segment_leg_mask` | Segmentar com correções opcionais |
| `temperature_matrix`, `count_hot_pixels` | Conversão térmica e contagem |
| `temperature_from_scale_percentage`, `scale_percentage_from_temperature` | Converter limiar |
| `annotate_boxes`, `segmentation_overlay`, `hot_pixels_overlay` | Previews |
| `segmented_image` | Adaptador de análise completa |

Para novos consumidores, prefira a rota tipada `/segment` para análise completa.
As operações granulares preservam a interação do protótipo existente.

Imagens/matrizes ficam temporariamente na sessão do cliente e na requisição.
O backend não salva imagens nem cria análises persistentes. Encerrar a sessão
perde a timeline visual. Somente métricas confirmadas são gravadas no banco;
o histórico de métricas não reconstrói as imagens da comparação.

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
Os demais endpoints CRUD/importação estão no README e em `/docs`.

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

## React e desktop

React poderá entrar em `frontend/react/` e consumir a mesma API. Máscaras e
coordenadas têm contratos independentes do canvas. Antes de disponibilizar
chaves no navegador, implemente autenticação de usuários; a chave atual serve
para comunicação entre processos. Esta reorganização não adiciona login.

Docker atende à execução web e testes. O executável usa processos Python locais,
continua iniciando o backend automaticamente e é compilado por sistema operacional.
