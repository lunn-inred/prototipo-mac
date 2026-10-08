# Arquitetura e estrutura do projeto

[← Voltar ao README](../README.md)

## Arquitetura

```text
.
├── frontend/
│   ├── run.py                   # inicialização web
│   ├── requirements.txt
│   ├── streamlit/
│   │   ├── app.py e pages/      # navegação e páginas
│   │   ├── components/         # filtros, importadores e termografia
│   │   ├── api_client/         # HTTP, DTOs e transporte de imagens/matrizes
│   │   ├── presentation/       # cache e adaptação visual
│   │   ├── assets/
│   │   └── .streamlit/
│   └── tests/
├── backend/
│   ├── mac_api/
│   │   ├── main.py e schemas.py
│   │   ├── core/               # configuração, conexão e transporte
│   │   ├── repositories/       # leitura de dados
│   │   └── modules/            # atletas, GPS, saltos, termografia e indicadores
│   ├── requirements.txt
│   ├── migrations/             # alterações SQL versionadas, quando necessárias
│   └── tests/                  # unitários, contratos e integração local
├── desktop/                    # launcher, spec do PyInstaller e testes
├── infrastructure/docker/      # imagens dos processos web
├── experiments/                # protótipos de pesquisa, quando presentes
├── docs/
├── compose.yaml e compose.test.yaml
├── .env.example
├── app.py e desktop.py          # entradas de compatibilidade
└── README.md
```

Fluxo web: navegador → Streamlit → HTTP → FastAPI → serviços/repositórios → Supabase.
No executável, a mesma API é iniciada localmente e consumida pela WebView.

O frontend controla widgets, desenho, formulários e estado temporário. O backend
calcula segmentação, temperaturas, pixels quentes, divisão anatômica, comparação
basal/atual, estatísticas e classificação EVA; também valida e persiste dados.
Não há imports do backend no cliente. Testes de arquitetura protegem essa regra.

As métricas de leitura vêm das views; cadastro de atletas continua na tabela
`public.atleta`. Operações de escrita consultam tabelas dentro de transações para
validar existência, duplicatas e integridade. Nenhuma alteração de schema é
necessária para esta reorganização.

As imagens permanecem temporárias na sessão do cliente e durante as requisições.
A API não salva arquivos nem mantém análises persistentes. A timeline visual
continua temporária; somente medidas confirmadas são gravadas no banco.

Contratos: [API HTTP](api.md). Validação: [testes](testing.md).

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

A view `vw_medidas_saltos` não precisa expor `id_atleta`: o backend
correlaciona seu campo `atleta` com nome, apelido e nomes alternativos do
cadastro. Apenas correspondências únicas recebem ID para edição/exclusão;
nomes ambíguos ou desconhecidos continuam nas leituras dos gráficos, mas não
são disponibilizados no gerenciamento de coletas nem associados no mural.

## React e desktop

React poderá entrar em `frontend/react/` e consumir a mesma API. Máscaras e
coordenadas têm contratos independentes do canvas. Antes de disponibilizar
chaves no navegador, implemente autenticação de usuários; a chave atual serve
para comunicação entre processos. Esta reorganização não adiciona login.

Docker atende à execução web e testes. O executável usa processos Python locais,
continua iniciando o backend automaticamente e é compilado por sistema operacional.
