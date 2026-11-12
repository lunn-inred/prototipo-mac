# Backups no Google Drive

[← Voltar ao README](../README.md)

## Preparação

A página **Backups** exige login Google e `MAC_API_KEY`, a mesma conta autorizada
e a pasta existente configurada em `MAC_GOOGLE_BACKUP_FOLDER_ID`. Cada instalação
mantém seus próprios tokens; não compartilhe `data/credentials/`. A API renova o
token e valida novamente a pasta e sua permissão de escrita antes de usar o Drive.
No desktop usa a autorização nativa, quando disponível; com API externa e sem
token nativo, usa a autorização Web dessa instalação.

```env
MAC_DB_TARGET=local
MAC_BACKUPS_DIR=./data/backups
MAC_ANALYSES_DIR=./data/thermography
MAC_GOOGLE_BACKUP_FOLDER_ID=ID_DA_PASTA_OFICIAL
MAC_BACKUP_MAX_BYTES=10737418240
MAC_BACKUP_MAX_EXTRACTED_BYTES=21474836480
```

No Compose, os três diretórios privados precisam existir e ser graváveis pelo
usuário do backend. Não troque permissões recursivamente de todo o projeto.

```bash
mkdir -p data/thermography data/credentials data/backups
docker compose up -d --build backend frontend
```

`data/backups` e `data/thermography` são bind mounts no host, preservados ao
recriar containers. Os caminhos padrão no executável são relativos ao binário.
Um caminho customizado no Docker exige ajustar seu volume correspondente.

## Fazer backup

Clique em **Fazer backup**. A API aguarda as operações em andamento, bloqueia
temporariamente novas requisições de dados e copia todas as tabelas do schema
`public` e todos os arquivos das análises registradas. Depois libera a aplicação,
compacta e envia um arquivo novo à pasta do Drive. Cada arquivo tem data/hora UTC,
identificação anônima da instalação e um sufixo único. Não sobrescreve backups
anteriores e não há limpeza automática ou agendamento.

O pacote contém:

```text
manifest.json                 # versão, criação UTC, instalação e SHA-256/tamanho dos arquivos
database/database.json        # contrato do esquema, contagens e estado das sequências
database/0.csv, 1.csv, ...     # dump lógico via COPY de todas as tabelas public
analyses/atleta_<id>/<data>/analise_<uuid>/...
analyses/_drafts/<uuid>/draft.json  # rascunhos térmicos salvos, inclusive sem atleta
```

As análises incluem imagens originais, máscaras PNG, temperaturas NumPy e todos
os metadados/divisões/limiares. Inclui também os rascunhos térmicos persistidos por
**Salvar análise**, com imagens e ajustes já definidos, e suas medidas disponíveis
no banco. Campos não informados não ganham medidas fictícias.
Não inclui `.env`, tokens, sessões, o diretório de backups ou alterações ainda
somente na memória da interface. Os CSVs contêm dados privados reais;
não os publique, abra com ferramentas indiscriminadas ou versione o ZIP.
A identificação da instalação fica em `MAC_BACKUPS_DIR/installation.txt`.

Trata-se de um **backup lógico dos dados da aplicação**, não de um `pg_dump` nem
de uma cópia física do cluster. Não exige executáveis PostgreSQL extras no
Windows, macOS, Linux ou container. Não contém/restaura schemas `auth`, papéis,
senhas do PostgreSQL, extensões, large objects ou configuração do servidor.
O esquema local deve já existir e ser compatível: em uma instalação nova,
prepare primeiro o banco conforme [Banco local](local-database.md).

## Baixar e restaurar

Atualize a lista, escolha um backup e clique em **Baixar e restaurar**. A janela
explica a substituição do banco e exige marcar a autorização e confirmar. Fechar
o X cancela antes do início. Depois de iniciada, não feche a aplicação/API nem
repita a operação até ela terminar.

O fluxo é:

1. Baixar para uma pasta temporária, verificar tamanho e SHA-256, extrair somente
   caminhos permitidos e validar os arquivos de análise.
2. Bloquear temporariamente novas requisições de dados e aguardar as já iniciadas.
3. Conferir compatibilidade do esquema e criar uma **cópia preventiva completa**
   do estado local em `MAC_BACKUPS_DIR/recovery-<data>-<id>.zip`.
4. Substituir os dados das tabelas `public` em uma transação e reconciliar as
   análises locais mantidas, com suas medidas e referências necessárias.
5. Publicar os arquivos reconciliados e confirmar a transação. Atualizar caches
   e limpar rascunhos antigos desta interface, preservando o login Google.

**Baixar não é apenas obter um ZIP no navegador: essa ação restaura o banco local.**
GPS, saltos, cadastros e outros dados locais ausentes do backup são substituídos,
exceto referências necessárias às análises térmicas explicitamente preservadas.
O arquivo é baixado pelo backend, não pelo computador do navegador quando ele
está em outra máquina. A cópia preventiva permanece no backend e não é enviada
automaticamente ao Drive. As cópias originais geradas para envio também permanecem
em `MAC_BACKUPS_DIR`; cuide do espaço em disco e da retenção.

## Regras de reconciliação

Rascunhos salvos também seguem as regras de revisão abaixo, mas possuem uma
identidade separada das análises completas de mesmo UUID. Preservar um rascunho
local mantém o cadastro do atleta necessário e as medidas SQL já registradas.
A identidade/revisão lógica das medidas é mantida para permitir futuras edições.
Uma versão completa e seu estado de edição parcial podem coexistir em arquivos. Após restaurar,
se a origem completa tiver sido alterada, será necessário reabri-la antes de
finalizar a edição; a revisão antiga não permite sobrescrevê-la silenciosamente.

A identidade da análise é seu UUID. A revisão é `created_at` dos metadados
(atualizado pelo salvamento de alterações), em UTC; não é a data da coleta nem
o horário de modificação do arquivo no sistema operacional.

| Situação | Resultado |
|---|---|
| Mesmo UUID e mesmos arquivos | Mantém a análise local |
| Mesmo UUID, local com salvamento mais recente | Mantém a análise local |
| Mesmo UUID, backup com salvamento mais recente | Usa a análise do backup |
| UUID apenas no local | Preserva a análise local |
| UUID apenas no backup | Inclui a análise do backup |
| Mesmo UUID/revisão, conteúdo diferente | Recusa a restauração para revisão manual |

As medidas SQL das análises locais mantidas são preservadas por atleta/data e
grupo termografia, remapeando medidas pelo nome e preservando o ID de um grupo
térmico ausente, quando livre (views legadas podem depender desse ID). Se a análise foi movida, os
registros da localização antiga no backup são retirados. Cadastros/referências
locais necessários e ausentes do backup são reinseridos. Arquivos legados que
não tinham medidas SQL continuam sem criação artificial de medidas.

IDs numéricos não identificam globalmente uma pessoa: se o mesmo ID de atleta
apontar para nomes completos diferentes, ou uma referência obrigatória colidir,
a restauração é recusada, em vez de associar dados à pessoa errada. Também
recusa análises distintas para o mesmo atleta/data. Não tenta mesclar pessoas
por apelido nem resolver conflitos silenciosamente.

## Segurança, falhas e limites

- Nunca usa o Supabase como destino ou fallback: exige `MAC_DB_TARGET=local`.
- SQL recebido do arquivo não é executado. O dump usa CSV, nomes SQL são
  identificadores escapados e a estrutura é comparada à do banco local.
- Não cria colunas, tabelas ou migrations. Esquemas diferentes exigem revisão
  prévia. Esta versão recusa particionamento, tabelas estrangeiras, views
  materializadas, FKs externas ao `public`, sequências decrescentes e ciclos
  entre tabelas. Funções, triggers, views, índices e constraints entram no
  contrato de compatibilidade; não são reinstalados pelo backup.
- O ZIP tem manifesto, hashes por arquivo e hash do pacote no Drive. Isso
  detecta corrupção, não é uma assinatura digital: use somente a pasta/conta
  confiável da equipe. Links simbólicos, caminhos externos e arquivos duplicados
  no ZIP são recusados. Limites padrão: 10 GiB ZIP, 20 GiB extraídos, 100 mil arquivos.
- A operação roda em tarefa de fundo; a página consulta seu progresso. Uma por
  vez por processo. Em uma falha normal antes do commit há rollback SQL e
  compensação dos arquivos; a cópia preventiva é mantida.
- **Use uma única instância/processo da API por banco e diretório.** Não rode
  simultaneamente API web e API embutida do desktop nos mesmos dados. Pare
  scripts externos e edições diretas durante backup/restauração. A exclusão de
  manutenção da API não coordena outros programas. A listagem e o polling de
  backups continuam disponíveis durante o bloqueio; demais rotas retornam 423.
- Não há transação distribuída entre PostgreSQL e filesystem. Em queda abrupta
  ou falha de recuperação, `MAC_BACKUPS_DIR/restore-pending.json` pode permanecer.
  As rotas de dados ficam bloqueadas inclusive após reiniciar. **Não apague esse
  diário nem pastas `.mac-before-*`/`.mac-restore-*` sem revisar a recuperação.**
  Ele aponta para a cópia preventiva e os diretórios envolvidos. Um responsável
  deve conferir banco/arquivos, recuperar o par consistente (com o pacote
  preventivo e os mesmos mecanismos transacionais) e só então remover o diário.
  A página não oferece uma recuperação automática de desastre nesta versão.
- Após restaurar, recarregue outras interfaces/clientes conectados para descartar
  caches e rascunhos antigos. Requisições autenticadas continuam obrigatórias;
  a autorização do Drive não é substituída pelo backup.

O backend guarda temporariamente espaço para download, extração, cópia preventiva
e arquivos reconciliados. Reserve várias vezes o tamanho dos dados. Falha no
upload não remove dados locais; pode ser necessário entrar novamente no Google
ou criar um novo backup. Não há retomada automática de upload interrompido.
