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

O rascunho permanece na sessão até a confirmação. Adicionar à timeline grava
imagens, máscaras e matrizes no arquivo local do backend, permitindo reabrir a
comparação em outra sessão. A API lista metadados/miniaturas e carrega matrizes
sob demanda. O registro das medidas no banco continua uma operação separada.

Contratos: [API HTTP](api.md). Validação: [testes](testing.md).

## Carregamento e cache

- Em GPS e salto, o painel de análise só consulta o histórico e calcula os
  gráficos quando aberto. Os filtros dos gráficos executam em um `st.fragment`,
  sem reconstruir o CRUD/importador a cada interação.
- No salto, a lista de coletas editáveis é buscada somente nas abas **Editar**
  e **Excluir**. O importador permanece montado para preservar o upload e as
  edições durante a troca de abas.
- As leituras de jogadores e coletas do CRUD têm cache de 60 segundos, separado
  por URL da API, credencial e endpoint. Cadastros, alterações, mudança de status,
  exclusão e importação de saltos invalidam esse cache após sucesso. Falhas não
  invalidam as leituras anteriores. Alterações externas podem levar até 60
  segundos para aparecer nessas listas; o TTL não faz atualização automática.
- Os caches já existentes dos históricos gráficos (cinco minutos) e dos cálculos
  (60 segundos) permanecem. As confirmações do CRUD/importadores continuam
  invalidando o histórico correspondente; validação e gravação não usam o
  cache de referências e continuam consultando o backend.
- O cliente HTTP mantém conexões reutilizáveis, com autenticação enviada em
  cada requisição e encerramento do cliente na saída do processo. Isso não muda
  o timeout configurado em `MAC_API_TIMEOUT_SECONDS`.

As abas e painéis usam rastreamento de abertura do Streamlit. A versão mínima
do frontend é **1.63**; atualize as dependências com
`python -m pip install -r requirements.txt` (ambiente completo) ou
`python -m pip install -r frontend/requirements.txt` (somente frontend).
As mesmas otimizações se aplicam ao modo web e desktop. Não há alteração de
schema, índices ou permissões do banco, nem mudança nas fórmulas das métricas.

Essas mudanças reduzem requisições; não eliminam a latência de uma consulta
inicial ao Supabase. A suíte verifica contagens de chamadas com API/banco
simulados, não um benchmark de tempo do ambiente de produção.

## Responsabilidades

O tema compartilhado em `frontend/streamlit/components/ui.py` limita todas as
páginas (Jogadores, GPS, Salto e Termografia) a 90% da área principal, com máximo
de 1440 px e centralização. Em telas de até 900 px, usa 100% da largura disponível.
Assim, monitores ultrawide não esticam os componentes indefinidamente. Os limites
específicos das imagens e dos pop-ups térmicos continuam apenas na Termografia.

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
