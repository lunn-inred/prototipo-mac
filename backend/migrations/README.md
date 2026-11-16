# Migrações

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
docker compose up -d --build --no-deps backend
```

O comando usa as credenciais já configuradas no contêiner. O Docker e o serviço
`db-dev` precisam estar em execução. Não use esse procedimento em banco remoto.
