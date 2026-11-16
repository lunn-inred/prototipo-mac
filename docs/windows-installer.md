# Instalador Windows — MAC Performance

[← Voltar ao README](../README.md)

## Estado da implementação

O código do instalador e a automação estão implementados para Windows 10 22H2 /
Windows 11 **x64 Intel/AMD**. A homologação inicial deve ser feita no Windows 11.
Não há suporte a ARM/32 bits. O `.exe` Windows e o `MAC-Setup.exe` precisam ser
gerados e testados dentro do Windows: testes no Linux não comprovam serviço,
ACLs, WebView2, OCR, reinicialização ou comportamento do instalador Inno Setup.
O desenvolvimento web/Linux e o Docker continuam separados e não são migrados
automaticamente pelo instalador.

Validação executada em duas VMs Windows 11 x64: uma de build e outra inicialmente
limpa, sem código-fonte, Python de sistema ou Docker. Passaram testes focados de
launcher, API, autenticação e GPS em Linux/Windows; os oito testes de migrations
no Windows incluíram cinco integrações com PostgreSQL temporário `mac_test`.
A regressão de espera por recuperação além de 60 segundos passou nos dois sistemas.

Na instalação limpa, foram confirmados:

- Instalação e banco inicial sem dados pessoais, com quatro registros de migrations.
- Serviço `LocalService`, papel SQL sem superusuário e OCR `eng`/`por` disponíveis.
- Abertura pelo atalho sem elevação, incluindo início do banco inicialmente parado.
- Interface de jogadores, GPS, salto, termografia (incluindo EVA), timeline e sincronização.
- HTTP 200 nas leituras autenticadas de atletas, painel, saltos, GPS e termografia.
- Fechamento normal da janela encerrando os processos da interface e da API.
- Desinstalação/reinstalação preservando UUID da instalação, identificador do cluster
  PostgreSQL, configuração e arquivo sintético de teste (removido ao concluir).
- Após reboot do pacote corrigido, banco automaticamente disponível e consultas
  autenticadas bem-sucedidas antes de qualquer login gráfico.

As verificações nativas corrigiram handles pywin32, `FILE_FLAG_OPEN_REPARSE_POINT`,
a dependência dinâmica `win32timezone`, a conta canônica do serviço e o timeout
de recuperação. O provisionamento repetido e o backup preventivo verificado passaram.

Ainda não foram homologados Windows 10, Google OAuth/Drive real, todos os fluxos
com dados reais nem todos os cenários adversos da matriz abaixo. Esta é uma
validação para piloto, não uma certificação completa de produção.

## Para o cliente

Entregue somente `MAC-Setup-<versão>-x64.exe` (e instruções de autorização Google,
se a sincronização fizer parte da entrega). Não entregar código, `.env` do
desenvolvedor, senhas Supabase, dumps pessoais, tokens ou ambientes virtuais.

O instalador solicita administrador uma vez, prepara dependências e banco,
autoriza um usuário Windows e cria o atalho. Se o UAC usar **outra conta**,
informe na página **Usuário autorizado** a conta real que abrirá o aplicativo.
O cliente não precisa de Python, Docker ou iniciar PostgreSQL manualmente.
O consentimento Google continua sendo uma ação do usuário.
Ao concluir, abra o atalho; o programa não é iniciado enquanto o Setup ainda
mantém o bloqueio de instalação. Pode haver pedido de reinicialização por um
pré-requisito Microsoft.

## Componentes e diretórios

| Componente | Local / comportamento |
|---|---|
| Aplicativo | `C:\Program Files\MAC Performance\`, PyInstaller em pasta, somente leitura no uso diário |
| PostgreSQL 17 | `runtime\pgsql\`; serviço exclusivo `MACPerformancePostgreSQL17`, automático e com recuperação de falhas |
| Dados PostgreSQL | `%PROGRAMDATA%\MAC Performance\postgres`, acesso de Administradores/SYSTEM/LocalService |
| Banco | `mac_dev`, usuário SQL `mac_app` proprietário, sem superusuário/CREATEDB/CREATEROLE |
| Configuração | Único `.env` gerado em `%PROGRAMDATA%\MAC Performance`; não é o `.env` do repositório |
| Identidade | `installation.json`, UUID e identificação do serviço/porta; não permite adoção automática de outro banco |
| Credencial de manutenção | `admin\postgres.json`, somente Administradores/SYSTEM; não copiar para equipe/Drive |
| Imagens e backups | `%PROGRAMDATA%\MAC Performance\thermography` e `backups`, grupo local `MACPerformanceUsers` e usuário autorizado |
| Tokens e sessões Google | `%LOCALAPPDATA%\MAC Performance\credentials`, privados de cada usuário |
| Logs | `%LOCALAPPDATA%\MAC Performance\logs\startup.log` e `api.log`, com rotação |

As senhas do banco e a chave da API são aleatórias por instalação. São protegidas
por **ACLs NTFS**, não por criptografia de disco implementada pelo aplicativo.
Use BitLocker e controles de conta do Windows conforme a política do cliente.
Todos os membros autorizados do grupo local podem acessar o conjunto de dados.
O instalador não concede acesso de escrita ao programa/serviço para esse grupo;
concede consulta/inicialização do serviço, não exclusão ou mudança da configuração.

O PostgreSQL roda como `LocalService`, não como administrador. `initdb` usa um
token restrito criado pelo próprio PostgreSQL 17 e um arquivo temporário de
senha, removido ao terminar. Não é recriado parcialmente esse token em Python:
o mecanismo do fornecedor também ajusta sua DACL para o usuário atual
([código do PostgreSQL](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/common/restricted_token.c)).
O marcador `PG_RESTRICT_EXEC` não é herdado do ambiente do instalador, para
não pular essa proteção nativa. O banco
escuta somente `127.0.0.1`, com autenticação SCRAM. A porta é escolhida entre
55434–55444 e persistida; não reutiliza o Docker em 55433 ou o Supabase.
O serviço usa o nome canônico `NT AUTHORITY\LocalService`, inclusive em Windows
traduzido: o SCM não aceita o nome localizado retornado por `LookupAccountSid`
([documentação Microsoft](https://learn.microsoft.com/en-us/windows/win32/services/localservice-account)).

A inicialização da API tolera até 120 segundos, para a primeira execução e
verificação dos binários pelo Windows. O OCR de GPS só é carregado quando há
uma extração solicitada, evitando inicializar img2table/Numba ao abrir o app.

O controlador PostgreSQL (`pg_ctl runservice -w -t 180`) e o launcher aguardam
até 180 segundos pelo serviço, incluindo recuperação após desligamento
interrompido. Na VM com armazenamento lento, a sincronização dos arquivos
ultrapassou o padrão de 60 segundos; a configuração ampliada evita abandonar
a inicialização nesse ponto. Reparar/reinstalar também atualiza esse comando.
Não apague `postmaster.pid` para contornar uma falha: pode haver um servidor
ativo. Identifique a instância e consulte seus logs antes de intervir.

## Preparar a VM de build

1. Windows 11 x64 e Python **3.11 x64** (a versão fixada para este build).
2. [Inno Setup 6.4+](https://jrsoftware.org/isinfo.php).
3. Binários completos [PostgreSQL 17 para Windows](https://www.postgresql.org/download/windows/), com `bin`, `lib`, `share` e licença.
4. Distribuição Windows do [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html), com DLLs, licenças e `por.traineddata`/`eng.traineddata`.
5. [WebView2 Evergreen Standalone x64](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution), instalador **completo/offline**, não o bootstrapper pequeno.
6. [Visual C++ Redistributable x64](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist), instalador completo.

Obtenha os arquivos dos fornecedores, confira origem/versão e preserve as
licenças. O build verifica assinaturas Microsoft do WebView2 e VC++ e gera hashes
dos runtimes. Esses hashes não substituem a conferência de origem de PostgreSQL
ou OCR. A validação de assinatura pode exigir conectividade na máquina de build.
O repositório não contém binários de terceiros nem faz download silencioso deles.

Na cópia limpa do código (sem `.env`/`data` privados), em PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-desktop.txt

powershell -NoProfile -ExecutionPolicy Bypass -File .\infrastructure\windows\build.ps1 `
  -PostgresRoot 'C:\MAC-vendor\pgsql' `
  -TesseractRoot 'C:\Program Files\Tesseract-OCR' `
  -WebView2Installer 'C:\MAC-vendor\MicrosoftEdgeWebView2RuntimeInstallerX64.exe' `
  -VcRedist 'C:\MAC-vendor\VC_redist.x64.exe' `
  -DeploymentConfig 'C:\MAC-vendor\mac-oauth-desktop.json' `
  -Version '1.0.0'
```

`-ExecutionPolicy Bypass` vale somente para esse processo, não muda a política
global. O build PyInstaller gera `dist\MAC Performance\`; Inno gera
`dist\installer\MAC-Setup-1.0.0-x64.exe`. Não distribua somente o executável
interno da pasta: o instalador inclui os runtimes e prepara o serviço.

O build reutiliza o cache do PyInstaller quando possível; alterações de código
ou dependências invalidam as etapas afetadas. Acrescente `-Clean` ao script
PowerShell para limpar esse cache numa compilação de diagnóstico/reprodução.
Feche a instância em `dist\MAC Performance` antes de recompilar. O script
recusa sobrescrever o executável em uso; não encerra processos automaticamente.

O build exige `-DeploymentConfig` apontando para um JSON privado fora do Git,
contendo somente parâmetros do cliente OAuth Desktop
e o ID da pasta compartilhada:

```json
{
  "MAC_GOOGLE_DESKTOP_CLIENT_ID": "cliente.apps.googleusercontent.com",
  "MAC_GOOGLE_DESKTOP_CLIENT_SECRET": "valor-do-cliente-desktop",
  "MAC_GOOGLE_ALLOWED_EMAIL": "conta-da-equipe@example.org",
  "MAC_GOOGLE_BACKUP_FOLDER_ID": "id-da-pasta-da-equipe"
}
```

Nenhum token, conta de serviço, chave de nuvem ou senha PostgreSQL pode entrar
nesse arquivo. O consentimento Desktop e as permissões da pasta precisam estar
configurados no Google; o instalador não os concede automaticamente.
No pacote gerenciado, a tela de login e a exigência de sessão na API ficam
sempre ativas. Sem os parâmetros OAuth Desktop, a tela informa que o login não
foi configurado e não abre as páginas internas. O ID do cliente Web não é
necessário nessa instalação. A correção exige gerar e instalar um novo Setup;
o pacote já instalado não atualiza sozinho.

Assinatura digital do instalador final é recomendada antes da distribuição.
O pipeline ainda não possui certificado nem assinatura automática: antivírus e
SmartScreen podem alertar sobre builds não assinados. Não desative proteções do
Windows para contornar problemas; valide a origem e configure a assinatura.

## Banco inicial e migrations

`backend/bootstrap/initial.sql` contém somente estrutura de `public`, views e o
catálogo técnico de grupos/medidas. Não contém atletas, usuários, partidas ou
medições. Não é a fixture de testes nem um dump com dados do desenvolvimento.
O manifesto registra as migrations já incorporadas nessa base.

O banco novo recebe a base uma única vez. O histórico fica em
`mac_internal.schema_migrations`, fora de `public` para não sincronizar IDs e
histórico de outra instalação. As migrations históricas incorporadas são
registradas pelo checksum, não reexecutadas sobre a base atual.

Novas migrations SQL em `backend/migrations` são aplicadas antes de abrir a API:

- Verificação de UUID, checksum, versão e fingerprint da estrutura pública.
- Advisory lock para impedir dois migradores simultâneos.
- Dump lógico verificado com `pg_restore --list` e hash SHA-256 antes de alterar
  um banco existente, em `backups\migrations`.
- Uma transação para SQL e histórico: `BEGIN/COMMIT` externos dos scripts são
  removidos pelo gerenciador. Scripts que exigem execução fora de transação
  precisam de adaptação explícita, não devem ser incluídos sem revisão.
- Falha bloqueia a abertura e preserva os dados; não faz restauração automática.

Não altere migrations históricas ou a base já publicada. Crie uma migration nova.
Backups feitos pelo instalador elevado ficam em `admin\migration-backups`,
separados dos backups graváveis pelo aplicativo e acessíveis aos administradores.
Checksum divergente, banco mais novo, alteração manual de schema ou banco sem
identificação bloqueiam a abertura; nada é recriado ou adotado como fallback.
Instalações existentes de desenvolvimento/portáteis exigem migração assistida,
não se deve apontar o instalador ao volume Docker atual.

A sincronização continua sem executar DDL. Todos os computadores precisam estar
na mesma versão/estrutura; índices Drive antigos podem exigir transição de pasta.
Uma restauração que altere o schema será detectada no próximo início e exigirá
revisão; não remova `mac_internal` para contornar uma incompatibilidade.

## Atualizar, reparar e desinstalar

Execute um novo instalador com o mesmo AppId e número de versão maior. Ele pede
para fechar o aplicativo, faz backup antes de parar o serviço/substituir o pacote,
instala os arquivos novos e aplica apenas migrations pendentes. Não há atualizador
online automático nesta etapa. Downgrade é bloqueado pelo instalador e pelo histórico.

Executar novamente a mesma versão permite reparar serviço/configuração sem apagar
dados. Senhas administrativas ausentes, pasta não identificada ou cluster apagado
não provocam criação de um banco vazio por cima: a instalação pede revisão.
Alterações da versão principal do PostgreSQL exigem procedimento próprio, não
uma simples substituição de `runtime\pgsql`.

Desinstalar encerra e remove somente o serviço próprio e os binários. Banco,
análises, backups, tokens e configuração persistente ficam preservados. Dados
de outros programas/instâncias PostgreSQL não são tocados.

## Homologação na VM

Use duas VMs ou clones: uma para build e uma limpa para o cliente. Com dados
fictícios, confira instalação, reinicialização, usuário padrão sem UAC diário,
serviço inicialmente parado, porta ocupada, conta Windows com espaços/acentos,
upload/OCR, edição/salvamento parcial e completo, atualização com dados, falha
de migration, falta de espaço/permissão, reparação e desinstalação/reinstalação.
Confira que os dados sobrevivem e que API/banco não escutam na rede externa.

Os testes Python simulam as chamadas Windows e executam a base/migrations no
`mac_test` descartável. Não substituem a execução real de `build.ps1`/Inno,
o token restrito, as ACLs, o registro no SCM e o WebView2 na VM Windows.
