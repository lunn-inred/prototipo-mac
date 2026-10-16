# Migrações

Armazene aqui mudanças SQL versionadas do schema/views quando forem necessárias.
`20261016_athlete_status.sql` adiciona `public.atleta.status` (`ativo`/`inativo`).
Os cadastros existentes e os novos recebem `ativo` por padrão. Execute uma vez
no banco antes de subir esta versão da API; a aplicação não executa DDL ao iniciar.
Não há exclusão de atletas nem alteração nas medições.
A fixture de testes fica em `backend/tests/fixtures/schema.sql` e deve ser
utilizada somente em bancos descartáveis.
