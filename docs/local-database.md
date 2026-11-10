# Banco local de desenvolvimento

[← Voltar ao README](../README.md)

## Ambientes separados

| Ambiente | Banco | Persistência | Porta no host |
|---|---|---|---|
| Desenvolvimento | `db-dev`, PostgreSQL 17, `mac_dev` | volume Compose `mac_dev_data` | `127.0.0.1:55433` |
| Testes automatizados | `postgres-test`, `mac_test` | descartável, fixture de testes | `127.0.0.1:55432` |
| Produção/origem | Supabase | remoto | não usado como fallback |

A aplicação usa **local por padrão**, mesmo que o `.env` antigo ainda contenha
credenciais `SUPABASE_DB_*`. Não é necessário apagar ou duplicar essas credenciais.
Somente a ferramenta explícita de exportação as utiliza em desenvolvimento.
Não há sincronização de alterações locais para a nuvem.

## Iniciar no dia a dia

Se a cópia já foi restaurada, basta iniciar o banco:

```bash
docker compose up -d --wait db-dev
```

Em seguida, use normalmente a API e o frontend/desktop. Para executar tudo em Docker:

```bash
docker compose up --build -d --wait
```

O backend no host usa `127.0.0.1:55433`; dentro do Compose, usa `db-dev:5432`.
O Compose faz essa troca automaticamente. Para parar sem perder o banco:

```bash
docker compose down
```

**Não use `down -v` nem remova o volume `mac_dev_data`**, pois isso apaga a cópia
persistente e o trabalho local. Subir/reiniciar containers nunca restaura o dump
automaticamente nem sobrescreve tabelas existentes. O diretório das termografias
continua sendo `./data/thermography` e não é alterado por esta ferramenta.

## Configuração

No único `.env` da raiz, os valores padrão equivalem a:

```env
MAC_ENVIRONMENT=development
MAC_DB_TARGET=local
MAC_LOCAL_DB_HOST=127.0.0.1
MAC_LOCAL_DB_PORT=55433
MAC_LOCAL_DB_NAME=mac_dev
MAC_LOCAL_DB_USER=mac_dev
MAC_LOCAL_DB_PASSWORD=mac_dev_local
```

A senha acima serve apenas para desenvolvimento local. Se alterá-la depois de
inicializar o volume, atualizar o `.env` não altera a senha do usuário já criado
no PostgreSQL: é necessário atualizá-la também no banco. Não apague o volume para
resolver uma divergência de credenciais.

Em desenvolvimento/testes, a API recusa `MAC_DB_TARGET=supabase`, hosts locais
que não sejam loopback ou os serviços `db-dev`/`postgres-test`, e bancos diferentes
de `mac_dev`/`mac_test`. A verificação ocorre ao criar a aplicação e antes de abrir
conexões. Não há fallback quando o banco local está indisponível.

Para um deploy de produção intencional, são necessários ambos
`MAC_ENVIRONMENT=production` e `MAC_DB_TARGET=supabase`, além de `SUPABASE_DB_*`.
Isso não é necessário nem recomendado no ambiente de desenvolvimento.

## Exportar a nuvem sem alterações

Com Docker disponível e as credenciais de origem `SUPABASE_DB_*` no `.env`:

```bash
python -m backend.tools.local_database export
```

A exportação abre uma transação somente leitura e usa `pg_dump` 17 dentro de um
container temporário, também com `default_transaction_read_only=on`. Um snapshot
compartilhado garante que o dump e o inventário leiam a mesma versão das tabelas.
Não é necessário instalar `pg_dump` no host. A origem deve ser PostgreSQL 17;
outra versão é recusada para exigir revisão explícita da compatibilidade.

O comando imprime um diretório novo, por exemplo:

```text
data/backups/cloud-AAAAMMDDTHHMMSSZ-identificador/
  banco.dump
  manifesto.json
```

O dump inclui dados e estrutura de `public`: tabelas, views, colunas, constraints,
índices e sequências. Os IDs e as configurações das colunas são preservados.
O manifesto contém versão da origem, contagens, hashes de dados/arquivo e descrição
da estrutura, sem linhas de atletas em texto. Datas e floats são canonicalizados
para a comparação não depender das configurações de exibição do servidor.

Não são clonados schemas gerenciados `auth`/`storage`/`vault`, roles, ACLs ou donos
do Supabase. O dono local é o usuário de desenvolvimento. A inspeção da origem
atual confirmou que os objetos da aplicação em `public` não exigem esses schemas
para a restauração. Dependências novas precisam ser reavaliadas; erros não são
ignorados silenciosamente.

O dump contém informações privadas reais. `data/backups/` está excluído do Git e
do contexto Docker. Os snapshots são criados em diretórios privados; uma falha
de exportação mantém o diretório marcado como `.incomplete`. Não envie esses
arquivos para repositórios ou pastas públicas. Imagens não fazem parte do dump.

## Restaurar explicitamente, somente uma vez

Para fazer exportação, restauração e verificação em uma execução, use o comando
Python abaixo **somente quando `mac_dev` estiver vazio**:

```bash
python -m backend.tools.local_database copy --confirm
```

Ele confere primeiro se o destino está vazio, cria um snapshot privado da nuvem
em modo somente leitura e restaura esse snapshot no banco local. O diretório
impresso pode ser usado depois com `verify`. Se `mac_dev` já contiver objetos,
o comando recusa a cópia; ele não atualiza nem sobrescreve dados locais.

Também é possível executar as etapas separadamente. Inicie `db-dev` e substitua
o caminho abaixo pelo diretório impresso na exportação:

```bash
python -m backend.tools.local_database restore data/backups/cloud-SEU-SNAPSHOT --confirm
```

O comando exige confirmação, confere o hash do arquivo e recusa um `mac_dev` que
já contenha tabelas, sequências, índices ou funções. O destino é fixo: serviço
Compose `db-dev`, banco `mac_dev`, loopback do container. Não há opção de host remoto,
`--clean`, exclusão de tabelas ou restauração automática na inicialização.

A restauração é uma transação única: em caso de erro, os objetos dessa tentativa
são desfeitos. O `public` vazio criado pelo PostgreSQL é mantido. A ferramenta roda
a partir do host, na raiz do projeto, com o ambiente Python ativado.

## Conferir a cópia

```bash
python -m backend.tools.local_database verify data/backups/cloud-SEU-SNAPSHOT
```

Confere hash do dump, contagens e hashes de todas as linhas, definições de colunas,
views, constraints, índices e nomes de sequências. Também consulta cada view para
verificar se ela funciona. Uma divergência retorna código de saída diferente de zero.
Após alterações intencionais locais, é esperado que a cópia deixe de coincidir
com o snapshot original; isso não significa corrupção.

O banco persistente não recebe dados artificiais dos testes. Os testes de CRUD
devem usar uma cópia descartável separada. O backup do banco **local atualizado**,
junto das imagens e do envio ao Google Drive, será uma etapa posterior; o comando
`export` descrito aqui sempre lê a **origem na nuvem**, não o trabalho local.
