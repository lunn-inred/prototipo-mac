# Migrações

`20261118_thermography_baseline.sql` cria `public.termografia_basal`, com uma
referência UUID por atleta e data da última atualização. Não altera medidas nem
arquivos de análises. Aplique no banco local antes de usar a nova API da timeline.
O instalador aplica a migration automaticamente pelo gerenciador existente;
a base histórica e seu manifesto permanecem intactos. Em desenvolvimento:

```powershell
Get-Content backend/migrations/20261118_thermography_baseline.sql -Raw -Encoding UTF8 | docker compose exec -T db-dev sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

A nova tabela participa dos backups de `public`. A sincronização exige estruturas
compatíveis em todas as instalações e não executa essa migration no Drive.

Armazene aqui mudanças SQL versionadas do schema/views quando forem necessárias.
`20261016_athlete_status.sql` adiciona `public.atleta.status` (`ativo`/`inativo`).
Os cadastros existentes e os novos recebem `ativo` por padrão. Execute uma vez
no banco antes de subir esta versão da API; a aplicação não executa DDL ao iniciar.
Não há exclusão de atletas nem alteração nas medições.
A fixture de testes fica em `backend/tests/fixtures/schema.sql` e deve ser
utilizada somente em bancos descartáveis.

`20261115_thermography_regional_zones.sql` cadastra 48 medidas de pixels:
coxa/joelho/canela/pé × direita/esquerda × frente/costas × fria/neutra/quente.
As quatro regiões seguem as divisões anatômicas ajustadas no sistema.
Cria `public.vw_termografia_zonas`, com uma coluna por medida, sem alterar a view
histórica. É transacional e pode ser reexecutada sem duplicar essas medidas.
Não recalcula registros antigos: as novas colunas ficam nulas para coletas sem
essas medidas. Execute no banco **local** antes de iniciar a API atualizada:

```powershell
Get-Content backend/migrations/20261115_thermography_regional_zones.sql -Raw -Encoding UTF8 | docker compose exec -T db-dev sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

O comando usa as credenciais já configuradas no contêiner. O Docker e o serviço
`db-dev` precisam estar em execução. Não use esse procedimento em banco remoto.
Se também for aplicar o EVA regional, mantenha a API parada até concluir ambas
as migrações e a transição do índice do Drive.

## EVA regional (20261116)

`20261116_thermography_regional_eva.sql` cria as 16 medidas `EVA_*` do grupo
termografia, a view `vw_termografia_eva_regional` e atualiza `eva_dor` em
`vw_medida_termografia` para o máximo regional da coleta. Não adiciona colunas às
tabelas e não distribui os valores gerais antigos pelas regiões.

**Remoção de dados:** a migração exclui a medida `EVA_DOR` e seus valores do grupo
termografia. Faça um dump antes, confira-o com `pg_restore --list` e mantenha-o
fora do Git. Pare a API antiga para que não tente gravar a medida removida.
Após a migração, inicie API/frontend atualizados. É transacional e idempotente.

```bash
docker compose stop backend
docker compose exec -T db-dev sh -c 'PGOPTIONS="-c default_transaction_read_only=on" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' > data/backups/pre-regional-eva.dump
docker compose exec -T db-dev sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/migrations/20261116_thermography_regional_eva.sql
```

Use um nome novo para cada backup: não sobrescreva uma cópia prévia. A migração
anterior de zonas regionais deve estar aplicada. A aplicação não migra ao iniciar.
O backup anterior exige a versão antiga do schema/código para restauração;
não o restaure sobre o banco em uso. Teste primeiro numa instância descartável.
Todos os computadores da equipe devem aplicar a migração: a sincronização
normal recusa schemas/views incompatíveis e não executa DDL. Se o Drive já tem
um índice antigo, pare a API e confirme que não há alterações pendentes em
outros computadores. Após aplicar **ambas** as migrações no primeiro computador,
reconstrua a imagem da API e publique o novo esquema antes de reiniciar a API:

```bash
docker compose build backend
docker compose run --rm --no-deps -T -e MAC_AUTO_SYNC_ENABLED=0 backend python -c 'from backend.mac_api.modules.backups.synchronization import synchronize; print(synchronize(schema_transition=True))'
docker compose up -d --no-deps --wait backend
docker compose up -d --build --no-deps frontend
```

Esse comando exige que o índice atual do Drive ainda seja exatamente o último
estado comum da instalação. Ele preserva o histórico e recusa divergências ou
outras mudanças de estrutura. Execute **uma vez**, apenas no computador que
publicará a migração. Os demais computadores precisam de revisão da base e
atualização coordenada antes de voltar a sincronizar: aplicar os arquivos SQL
sozinho não atualiza o estado comum antigo. Preserve todos os backups e índices.
