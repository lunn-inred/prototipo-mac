# Orientações para agentes — MAC Performance

Este repositório reúne uma API FastAPI e um frontend Streamlit para cadastro de
atletas e acompanhamento de GPS, saltos e termografia. A interface também roda
em desktop/WebView. Estas orientações complementam o [README](README.md) e a
documentação em `docs/`; não substituem a inspeção do código atual.

## Antes de alterar

- Confira a branch e `git status`; preserve alterações existentes da equipe.
- Leia o documento do assunto na lista abaixo e os testes relacionados.
- Faça mudanças focadas no pedido. Não mude fórmulas, schema ou contratos públicos
  como efeito colateral de ajustes de interface ou refatorações.
- Não faça commits, pushes, deploys ou operações destrutivas sem solicitação clara.
- Comunique e documente limitações reais; não declare testes executados ou
  garantias de persistência que não foram verificados.

## Arquitetura

- `frontend/`: páginas, widgets, edição visual, sessão, caches e cliente HTTP.
- `backend/`: API, regras de domínio, cálculos, OCR, processamento e persistência.
- `desktop/`: inicialização e empacotamento dos mesmos componentes web/API.
- `infrastructure/` e `compose*.yaml`: infraestrutura; `docs/`: documentação.
- O frontend consome somente a API: não importe o backend nem abra conexões
  PostgreSQL nele. Não duplique regras de negócio no Streamlit.
- Métricas são lidas pelas views; cadastro de atletas e validações transacionais
  do CRUD podem usar as tabelas correspondentes no backend.
- Preserve contratos usados por web e desktop e invalide os caches afetados
  somente após gravações bem-sucedidas. Não perca rascunhos em reruns ou troca de abas.

## Banco e dados privados

- Desenvolvimento usa `MAC_DB_TARGET=local` e `MAC_ENVIRONMENT=development`.
  O banco persistente é `mac_dev`, serviço Compose `db-dev`, porta do host `55433`.
  No backend dentro do Compose, a conexão usa `db-dev:5432`.
- Nunca use o Supabase como fallback, desative a trava de destino local ou ative
  modo de produção apenas para contornar um erro de conexão.
- Acesso à nuvem exige autorização explícita para a tarefa. Exportações usam
  conexão somente leitura; nunca aplique mudanças remotas por conveniência.
- O arquivo de configuração é o único `.env` da raiz. Preserve-o; mantenha
  `.env.example` sem credenciais reais. Não exiba segredos em logs ou comandos.
- Não versione nem inclua em imagens Docker dumps, dados dos atletas ou os
  diretórios `data/backups/` e `data/thermography/`.
- Não apague volumes, restaure sobre um banco populado ou use `down -v` no
  projeto de desenvolvimento. A restauração deve ser explícita e protegida.
  Limpeza de recursos descartáveis só pode atingir alvos de teste identificados.
- Atletas são desativados/reativados pelo status; não substitua isso por exclusão.

## Termografia

- Preserve as análises existentes e o formato de máscaras, matrizes e metadados.
  `MAC_ANALYSES_DIR` tem padrão `./data/thermography`, resolvido no backend.
- O botão **Registrar Análise** registra medidas no banco local e arquivos para
  a timeline em uma operação da API, com a mesma data e o atleta cadastrado.
- Recalcule contagens no backend sobre temperaturas e máscaras, não sobre valores
  resumidos enviados pela interface. Preserve medidas por perna e somas por vista.
- Preserve rollback SQL e compensação dos arquivos recém-criados nas falhas.
  Não prometa atomicidade distribuída entre banco e filesystem.
- A comparação térmica usa o basal como referência de segmentação. Não altere
  alinhamento, paleta, limiar ou interpretação das métricas sem pedido específico.
- **Costas** é o rótulo visual; chaves e nomes legados como `back`, `verso` e
  `SOMA_VERSO` continuam válidos nos contratos e arquivos existentes.

## Execução e validação

Execute os comandos a partir da raiz, usando o Python do ambiente virtual:

```bash
docker compose up -d --wait db-dev
python -m uvicorn backend.mac_api.main:app --reload --host 127.0.0.1 --port 8000 --env-file .env
python -m frontend.run
```

API e frontend são processos separados; execute-os em terminais diferentes.
`python desktop.py` também exige API separada; o binário empacotado inicia sua
API automaticamente, mas não inicia Docker nem restaura o banco.

- Crie/ajuste testes junto das mudanças. Rode os testes pertinentes e, quando
  viável, a suíte completa: `python -m unittest discover -v`.
- Testes de escrita usam exclusivamente `mac_test` descartável, nunca `mac_dev`
  nem Supabase. Só habilite `MAC_TEST_DB_ENABLED=1` após conferir explicitamente
  host, porta e nome desse banco, conforme [docs/testing.md](docs/testing.md).
- Use diretórios temporários para imagens e arquivos de testes; nunca o arquivo
  real de termografias. Não habilite serviços externos pagos/OCR em testes sem pedido.
- Relate falhas, testes ignorados e limites da validação. AppTest não substitui
  uma conferência visual do arraste, zoom e dimensionamento no navegador/WebView.
- Atualize a documentação pertinente ao mudar comportamento ou configuração.

## Onde buscar detalhes

- [Arquitetura e caches](docs/architecture.md)
- [Configuração e .env](docs/configuration.md)
- [Banco local, exportação e restauração](docs/local-database.md)
- [Execução web/Docker](docs/web.md) e [desktop/build](docs/desktop.md)
- [API e contratos](docs/api.md)
- [Testes e PostgreSQL descartável](docs/testing.md)
- [Jogadores](docs/players.md), [saltos](docs/jumps.md) e [GPS](docs/gps.md)
- [Termografia, registro unificado e timeline](docs/thermography.md)

Mantenha este arquivo curto e estável. Acrescente regras apenas quando forem
acordos duradouros da equipe; detalhes e justificativas pertencem à documentação
específica. Não salve aqui conversas, credenciais, dados privados ou estado temporário.
