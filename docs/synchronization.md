# Sincronização pelo Google Drive

[← Voltar ao README](../README.md)

## Uso

Na página **Sincronização**, salve suas alterações e clique em **Sincronizar
dados**. A mesma operação envia as alterações locais e recebe as compartilhadas:
cadastros, GPS, saltos, medidas térmicas e arquivos de análises completas/parciais.
Não é uma restauração integral do banco nem sincronização automática em segundo
plano. Alterações ainda apenas na interface não são enviadas nem descartadas.

Use a mesma pasta e a mesma conta Google autorizada em todas as instalações.
Mantenha `MAC_GOOGLE_BACKUP_FOLDER_ID` no `.env`: o nome da variável foi preservado
para compatibilidade. Cada computador mantém sua própria autorização OAuth.
Não compartilhe tokens, sessões nem `data/credentials/`.

Na primeira sincronização, a pasta existente será renomeada pelo ID para
**Analises MAC**. Não será criada outra pasta nem serão removidos os backups
antigos. O login continua apenas validando o acesso; renomear/enviar exige a ação
explícita de sincronizar. Pode ser necessário autorizar novamente a pasta se o
Google não permitir renomeá-la. O ID permanece o mesmo.

## Formato no Drive

```text
Analises MAC/
  analise-<uuid>-<hash>.zip
  analise-draft-<uuid>-<hash>.zip
  mac-sync-<uuid>.json
  ... índices e versões anteriores, além de backups legados existentes
```

Cada ZIP contém uma única análise, com originais, máscaras, temperaturas e
metadados, ou um estado parcial salvo. O índice JSON fica **fora dos ZIPs** e
contém os registros do banco, o contrato/versionamento de estrutura e as
referências dos ZIPs (ID Drive, revisão, hash do conteúdo e SHA-256 do pacote).
Assim, não é necessário baixar um ZIP para descobrir se a análise mudou.
ZIPs iguais são reaproveitados; uma alteração produz um novo objeto imutável.
O índice atual é publicado somente depois de enviar os arquivos necessários.

O banco é representado logicamente por tabela/chave primária, com valores
textuais PostgreSQL para preservar tipos e precisão. Todos os dados das tabelas
`public` são incluídos, inclusive usuários se presentes nesse schema. Não inclui
`.env`, autorizações Google, sessões externas nem outros schemas PostgreSQL.
O índice contém dados privados: não publique seus arquivos nem compartilhe a
pasta fora da equipe. Os hashes detectam corrupção, não autenticam o autor.

Os índices anteriores formam um histórico por referência ao índice pai. Arquivos
parciais de envios sem índice publicado não entram no estado compartilhado.
Não há limpeza automática: versões anteriores e ZIPs órfãos podem ocupar espaço.
Não apague índices/arquivos manualmente; eles podem ser necessários ao histórico.

## Mesclagem e conflitos

Cada instalação mantém em `MAC_BACKUPS_DIR/sync-state.json` o último estado
comum confirmado. Esse arquivo é privado e **não deve ser copiado para outro
computador**, assim como `installation.txt`. A cada operação são comparados:
estado comum, estado local e índice atual do Drive.

| Situação | Resultado |
|---|---|
| Alteração somente no local | Envia a alteração |
| Alteração somente no Drive | Recebe a alteração |
| Alterações em registros diferentes | Mescla ambas |
| Mesma alteração nos dois lados | Mantém uma versão |
| Exclusão de registro já sincronizado e outro lado inalterado | Propaga a exclusão |
| Registro novo, ainda não sincronizado | Preserva e compartilha |
| Alterações diferentes no mesmo registro/análise | Recusa para revisão |
| Exclusão de um lado e edição do outro | Recusa para revisão |

Não se escolhe vencedor pelo relógio do computador. A comparação de SQL é por
registro completo, não por coluna. Datas da coleta não decidem revisões.

As tabelas precisam ter chave primária. **Não há remapeamento automático de IDs
numéricos**: duas instalações que criarem registros diferentes com a mesma chave
terão conflito, sem associação silenciosa a outro atleta. Prefira inicializar a
equipe com a mesma base e sincronizar antes/depois de cadastrar/importar dados.
Isso reduz, mas não elimina colisões offline. Identidades globais com UUID e
resolução interativa são evoluções futuras; esta versão para na detecção.

Use um computador por vez para publicar. O índice é reconferido antes e depois
da publicação. Se duas máquinas publicarem sobre o mesmo pai ao mesmo tempo,
o histórico terá dois destinos e a sincronização será bloqueada para revisão.
O Drive não é um banco transacional; não há trava distribuída nem resolução
automática dessas ramificações. Preserve as duas cópias e peça revisão técnica,
em vez de apagar o índice ou escolher o arquivo de data mais recente.

## Estrutura do banco e migrações

O índice inclui a estrutura e sua identificação SHA-256: tabelas, colunas,
chaves, views, funções, triggers, índices, sequências e demais contratos já
inspecionados pelo mecanismo de backup. A estrutura local deve coincidir com
a compartilhada e com a base de sincronização da instalação.

Uma diferença bloqueia a operação **antes de publicar dados ou aplicar mudanças
locais**. A sincronização não executa SQL recebido do Drive e não instala DDL.
Migrações são arquivos versionados distribuídos pelo aplicativo em
`backend/migrations/`; sua aplicação continua explícita, conforme o guia dessa
pasta. Atualizar apenas a view em uma máquina não atualiza as demais.

Nesta primeira versão, uma mudança de estrutura após iniciar a sincronização
também exige migração planejada dos índices/estados comuns; somente aplicar SQL
nos computadores não converte o índice antigo. Esse upgrade não é automático.
Finalize as sincronizações pendentes antes de uma alteração de estrutura e
planeje a conversão com a equipe. Não apague `sync-state.json` para contornar
incompatibilidade, pois isso perde o histórico necessário às exclusões/conflitos.
Os limites de estrutura suportada são os mesmos do [backup lógico](backups.md).

## Segurança e recuperação

- Exige banco local, login Google e chave da API. Nunca usa Supabase como fallback.
- A aplicação temporariamente bloqueia as rotas de dados durante a operação.
  Use uma única API por banco/diretório e não execute scripts de escrita externos.
- SQL é aplicado com INSERT/UPDATE/DELETE dos registros alterados, **sem TRUNCATE**,
  respeitando vínculos e reajustando sequências para não reutilizar IDs antigos.
- Antes de alterar o SQL local, gera um ZIP preventivo completo em
  `MAC_BACKUPS_DIR/recovery-sync-<uuid>.zip`, sem enviá-lo ao Drive.
- Uma falha anterior ao commit reverte o SQL e compensa a publicação de arquivos.
  A publicação mantém a raiz de `MAC_ANALYSES_DIR` no lugar e prepara/move seus
  filhos dentro do próprio volume, compatível com bind mounts Docker e sem
  renomes entre filesystems. O diário também registra `.mac-incoming-*`.
  Se o índice já foi publicado, ele pode permanecer válido no Drive; uma nova
  tentativa mescla a partir da base anterior. Não promete atomicidade distribuída.
- Quedas abruptas ou falha durante/depois do commit deixam
  `restore-pending.json`: o acesso fica bloqueado até revisão técnica. Preserve
  esse diário, a cópia preventiva e as pastas `.mac-before-*`/`.mac-sync-*`.
- Falhas informam a etapa e a categoria (rede, PostgreSQL ou arquivos). O log do
  backend registra o ID da tarefa, o tipo da exceção e funções/linhas de origem,
  sem mensagens brutas, SQL, URLs autenticadas ou dados pessoais da exceção.
- Após sucesso, os caches desta interface são invalidados; análises não salvas
  permanecem preenchidas. Outros clientes abertos devem atualizar suas telas.
- Reserve espaço para cópia preventiva, ZIPs temporários e uma árvore de análises
  preparada. A operação baixa somente ZIPs necessários, mas o índice do banco é
  transferido completo. Limite do índice recebido: 128 MiB; ZIPs usam os limites
  já configurados de backup/extração. Não há streaming de alterações SQL.

Backups antigos continuam disponíveis pelos endpoints legados para recuperação
explícita, mas não são usados automaticamente como fonte de sincronização.
Restaurar um backup depois de iniciar a sincronização exige revisar o estado
comum: não trate uma recuperação de desastre como simples troca de computador.
