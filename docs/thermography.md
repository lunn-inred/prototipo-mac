# Termografia

[← Voltar ao README](../README.md)

## Fluxo da página

A página `frontend/streamlit/pages/Termografia.py` registra uma nova análise a partir das imagens
de frente e costas. O título **Termografia - Nova análise térmica** reúne o
nome da página e do assistente, sem um subtítulo duplicado. Quando habilitado,
o componente **Envio de Formulário** aparece ao final para importar fichas manuscritas.
A consulta e a comparação de análises ficam na página separada **Timeline térmica**.
A data da coleta aparece como campo editável no resumo da última etapa, com a
data atual de São Paulo como padrão. Não há pop-up para escolher a data.
Quando omitida em uma chamada à API, a mesma data padrão é aplicada pelo serviço.

A nova análise utiliza um assistente com **Continuar** e **Voltar**, apresentando
somente uma etapa por vez:

1. Jogador e massa, mapa de EVA Dor por região e observações opcionais.
2. Upload de frente/costas, prévia e botão para girar 90° para a direita.
3. Regiões das pernas e barra de cores, com **Ajustar regiões** em uma linha
   alinhada às colunas de **Voltar** e **Continuar**.
4. Divisão de cada perna em coxa, joelho, canela e pé, com uma prévia anatômica por vista
   e o botão **Redefinir regiões**.
5. Revisão da segmentação automática por watershed e correção manual pelo botão **Ajustar área perna**.
6. Cálculo da termografia: Tmin/Tmax, seleção da zona térmica e métricas.
   Cada vista apresenta a imagem
   com divisões e nomes das áreas anatômicas, as pernas segmentadas sem fundo
   e os pixels da zona selecionada.
7. Resumo da coleta: campos individuais de jogador, massa e **Data da coleta**
   lado a lado, com observações abaixo e tabelas de contagens regionais.
   A data é editável nessa etapa, sem popup. **Salvar análise** grava medidas no banco local e arquivos na
   timeline quando todos os dados estão completos.
   As 48 contagens regionais aparecem em abas Frente/Costas, com uma tabela por
   perna: linhas Coxa/Joelho/Canela/Pé/Total e colunas Fria/Neutra/Quente, em pixels.
   A API calcula a prévia com as mesmas regras usadas no registro. Os atalhos
   permitem voltar às divisões e à segmentação sem perder os metadados editados.
   Se a prévia falhar, o salvamento completo fica indisponível; permanece possível
   salvar os dados disponíveis como análise parcial mediante confirmação.

### EVA regional na primeira etapa

Logo abaixo de jogador/massa e antes das observações, o mapa apresenta frente e
costas, somente as pernas e os 16 grupos personalizados. Os números permanecem
visíveis, com uma região selecionada por vez. O campo único de EVA foi removido
dessa primeira etapa; basta preencher jogador e massa para avançar.

Os 16 valores são gravados no banco e nos arquivos da análise, inclusive em
salvamentos parciais, e restaurados no diagrama ao reabrir. Regiões não preenchidas
em uma avaliação nova recebem zero. A API valida inteiros de 0 a 10 e IDs conhecidos.
Os IDs seguem `front/back` + `thigh/knee/lower-leg/foot` + `left/right`.
No grupo `termografia`, as medidas seguem `EVA_{COXA|JOELHO|CANELA|PE}_{ESQUERDA|DIREITA}_{FRENTE|VERSO}`.
Não há medida `EVA_DOR`: a coluna `eva_dor` da view `vw_medida_termografia`
calcula o maior valor regional daquela coleta. A view `vw_termografia_eva_regional`
expõe as 16 medidas por atleta/data; o mural usa o máximo da última coleta.
`regional_eva: null` identifica análises antigas sem avaliação regional: não é
convertido em zero nem preenchido com o antigo EVA geral. O EVA geral anterior
é removido pela migração e permanece recuperável somente no backup prévio.
O laboratório independente não aparece no menu e não grava dados. Veja [mapa corporal](body-muscles.md).

### Salvar e retomar uma análise incompleta

**Salvar análise**, abaixo de **Continuar**, está disponível em todas as etapas,
mesmo quando não é possível avançar. Sem jogador selecionado, mostra um aviso
temporário no canto da tela: **Selecione um jogador antes de salvar a análise.**
O assistente volta à primeira etapa, preservando os dados e imagens já preenchidos;
não abre popup nem grava arquivos ou medidas. Se faltam outros dados ou etapas de cálculo, o
sistema pergunta **A análise atual possui etapas pendentes. Deseja salvar mesmo
assim?**, com **Não, voltar** à esquerda e **Salvar mesmo assim** à direita.
No histórico, o cartão recebe o aviso **Análise incompleta** em vermelho.
A completude depende dos dados obrigatórios e dos cálculos válidos das duas
imagens, não da etapa aberta. Uma análise completa pode ser salva ao voltar a
qualquer etapa ou logo após reabri-la do histórico, sem aviso de incompletude.
Trocar imagem, rotação, caixas, barra térmica ou escala pode deixar os cálculos
desatualizados; nesse caso, recalcule antes de salvar como completa ou confirme
o salvamento parcial. O backend continua recalculando as contagens ao registrar.
Com jogador selecionado, confirmar
grava no PostgreSQL local as medidas disponíveis e mantém o estado de edição
nos arquivos locais. Campos ausentes não recebem zeros nem valores fictícios:
uma massa não informada não gera a medida `MASSA`. A avaliação regional nova é a
exceção explícita: regiões omitidas no mapa recebem zero; avaliações antigas
ausentes continuam nulas. Observações preenchidas também são registradas. As contagens
das imagens já calculadas são recalculadas no backend sobre máscaras e
temperaturas; vistas ainda sem cálculo não recebem contagens inventadas.
Cancelar ou fechar o diálogo não grava nada.

Depois de salvar com sucesso, o assistente é reiniciado automaticamente na
primeira etapa, com jogador, campos, imagens e ajustes limpos para outra análise.
Os campos recebem valores vazios explicitamente antes de serem renderizados,
inclusive quando o salvamento ocorre na própria primeira etapa, para limpar
também o que já está exibido no navegador.
Uma mensagem temporária confirma: **Análise salva. Você poderá visualizá-la em
Ver análises anteriores.** ou **Análise parcial salva. Você poderá visualizá-la
em Ver análises anteriores.** Para continuar editando a análise salva, reabra-a
pelo histórico. Erros e cancelamentos preservam os dados preenchidos; o reinício
limpa somente a sessão do assistente, não registros no banco ou arquivos salvos.

O estado de edição guarda jogador, massa, EVA, observações, data, imagens
disponíveis, rotações, caixas, barra de cores, divisões anatômicas, ajustes de
máscara, escala e limiar já definidos. É possível salvar com somente uma imagem,
desde que o jogador seja informado. Rascunhos antigos ainda sem jogador podem
ser abertos, mas precisam receber um jogador antes de um novo salvamento.
Use **Ver análises anteriores** para retomá-lo, inclusive após
reiniciar a aplicação; os sem jogador ficam no cartão **Sem atleta (rascunhos)**.
A retomada usa a etapa salva, limitada pelas informações disponíveis; o resumo
é recalculado antes da finalização. A timeline compara somente análises completas.

O arquivo fica em `MAC_ANALYSES_DIR/_drafts/<uuid>/draft.json`, com imagens e
matrizes codificadas no próprio JSON. Rascunhos salvos entram no backup; mudanças
ainda somente na sessão não entram. Ao finalizar, o UUID é preservado e o
rascunho é removido somente depois do sucesso da gravação completa.

Cada salvamento atualiza as medidas da mesma análise no banco, sem duplicar a
coleta. Remover um dado antes de salvar também remove sua medida; mudar
jogador/data move a coleta, sem deixar as medidas no destino anterior. Outras
modalidades, como GPS e saltos, não são alteradas. O estado local identifica o
par atleta/data e a revisão lógica das medidas, recusando alterações concorrentes.

Uma edição incompleta de análise existente atualiza o SQL imediatamente; os
arquivos completos antigos são preservados internamente até a finalização,
mas deixam de ser oferecidos na timeline enquanto a edição está incompleta.
Ao escolher outro atleta/data que já
possui análise, a confirmação de sobrescrita continua obrigatória. Para um
rascunho, confirmar já substitui as medidas térmicas conflitantes no banco pelos
dados disponíveis; os arquivos completos são substituídos na finalização. Revisões concorrentes
exigem reabrir a análise, não uma sobrescrita forçada.

As correções de caixas, máscaras e divisões são feitas em pop-ups. Na divisão
anatômica, os limites são definidos sobre as caixas derivadas das máscaras
watershed (ou delimitadas manualmente) e mantêm suas coordenadas depois de
exclusões pelo pincel. Os canvases
dos pop-ups são centralizados.
Cada abertura de editor cria uma identidade nova para o canvas e para o
componente de medição da janela. Ao voltar entre regiões, divisão anatômica e
segmentação, o popup é remontado com os ajustes atuais da análise, sem reutilizar
o desenho da abertura anterior. Reruns dentro do mesmo popup mantêm a identidade
para permitir continuar a edição; máscaras aplicadas e divisões salvas permanecem
no rascunho.

Os diálogos de edição ocupam até 96% da largura da janela, limitados a 1600 px,
e seu conteúdo usa 100% dessa área. Um componente mede a altura útil da janela
e a posição do editor, reservando espaço para controles, toolbar e botões.
O canvas reduz ou amplia sua prévia para caber nessa área, sem scroll do diálogo;
a medição é repetida após a montagem/transição da janela, e a última dimensão
válida é preservada para evitar reabrir com uma prévia pequena. Na primeira
abertura, o editor usa um tamanho compacto provisório se a medição ainda não
chegou, evitando deixar o pop-up vazio em WebViews. Assim que recebe uma medida
estável, ajusta o canvas à janela; a medição também cobre montagem tardia.
Os botões têm
uma margem inferior reservada. **Concluir** é a ação destacada; aplicar,
restaurar e confirmar registros são ações secundárias. As barras cinzas do canvas
(Undo, Redo, Clear e botões de zoom) ficam ocultas; o zoom pela roda do mouse
permanece disponível nos editores de caixas e máscaras.
A roda do mouse fica reservada ao zoom da imagem. A página usa 90%
da área principal, limitada a 1440 px (100% em telas menores). Na página,
as prévias ficam limitadas a 400 px e 40% da altura da janela, evitando expansão
excessiva em monitores ultrawide. Os pop-ups mantêm seus limites ampliados,
e as barras anatômicas são mais grossas para facilitar a visualização e o arraste.

No editor de segmentação, aparece somente a perna selecionada,
com a área segmentada em fundo preto à direita; os traços desse
recorte são convertidos para coordenadas da imagem inteira antes do processamento.
Na divisão
anatômica, arraste as três linhas sobre a imagem; não é necessário ajustar
sliders percentuais. O rascunho e as imagens ficam na sessão ao voltar para
etapas anteriores. **Iniciar outra análise** descarta somente o rascunho atual,
mediante confirmação, preservando o banco e a timeline. A API considera a rotação
ao localizar as caixas e ler a barra térmica, preservando sua ordem quente/frio.
As vistas de frente e costas são apresentadas lado a lado, com as prévias
centralizadas e botões que ocupam a largura disponível de suas colunas.
Na divisão anatômica, aparece somente a prévia com nomes e limites das áreas.
Na segmentação, a segunda prévia mostra a área completa das pernas sem fundo.
A filtragem de pixels quentes aparece
somente na etapa de cálculo, após a definição da escala e da zona térmica.

O botão **Salvar análise**, com a análise completa, registra as medidas no PostgreSQL local e salva as
imagens, matrizes de temperatura, caixas e segmentações anatômicas. A máscara de
pixels quentes e as métricas não são congeladas: elas são recalculadas em tempo
real com a zona térmica (ou o limiar legado) salvo em cada vista da coleta,
sem controles de ajuste na timeline.
Ao escolher o jogador, a timeline
seleciona automaticamente a data mais antiga como **Basal** e a mais recente como
**Atual**. O botão **Mudar Basal**, abaixo da imagem basal, abre um pop-up com as análises desse jogador;
selecionar uma análise atualiza o basal e fecha o pop-up. A coleta **Atual** é
escolhida por uma barra deslizante com apenas as datas disponíveis. Ao mudar a
data, as imagens e o mapa são recalculados, mantendo o basal escolhido.
Se houver múltiplas análises na mesma data, a barra usa a última registrada;
o pop-up continua permitindo escolher qualquer análise como basal.
Com uma única data, a mesma coleta é usada nas duas pontas, sem barra deslizante.
A interface alerta quando a Atual antecede a Basal, sem bloquear a
comparação. Nas abas de
frente e costas, a comparação exibe as duas imagens, mapas normalizados por perna
e as métricas atuais com deltas em relação à basal. O mapa destaca somente em
vermelho os pixels quentes na Atual que não estavam quentes na Basal selecionada.
As demais áreas ficam no fundo escuro. A função `compare_hot_masks` preserva as
contagens e a visualização multicolorida para reutilização; a timeline solicita
`only_new=True`, sem modificar os registros salvos.

Na nova análise, o usuário informa jogador, massa, data da coleta, EVA Dor e,
opcionalmente, observações. O sistema segmenta as pernas na imagem inteira por
watershed, sem ler as caixas R1/R2 impressas. As pernas devem estar verticais,
com os pés para baixo; use a rotação na etapa de imagens. As caixas exibidas são
derivadas das máscaras. Se a detecção falhar, o aviso solicita rotação ou
delimitação das duas pernas em **Ajustar regiões** antes de continuar.
A lateralidade é invertida entre frente
e costas e o OCR é aplicado às regiões superior e inferior
do canto direito para preencher automaticamente Tmax e Tmin. Os campos continuam
editáveis e usam 20–40 °C como valores iniciais quando o OCR não reconhece uma
escala válida. Em seguida, o sistema estima a temperatura dos pixels pela barra
térmica lateral. Na etapa de cálculo, cada vista oferece três botões:
**Zona fria** (T < 31 °C), **Zona neutra** (31 ≤ T < 33 °C) e
**Zona quente** (T ≥ 33 °C, padrão). Não há slider ou seletor de unidade do
limiar nesse assistente. As faixas são fixas, sem sobreposição, e não são
redefinidas por Tmin/Tmax; uma zona fora da escala pode retornar zero pixels.
A imagem resultante usa o nome da zona selecionada. Contagens e percentuais
totais e por coxa/joelho/canela/pé usam somente pixels dessa zona dentro das
máscaras. O denominador continua sendo a área segmentada total de cada região:
`pixels na zona ÷ pixels segmentados × 100`. O resumo e o registro utilizam
as mesmas contagens recalculadas no backend.

A zona é salva por vista nos metadados `thermal_zone` (`cold`, `neutral`, `hot`).
No **Registrar Análise**, também são gravadas as três zonas simultaneamente,
independentemente do botão selecionado: 48 contagens inteiras de pixels para
coxa/joelho/canela/pé, direita/esquerda e frente/costas. Elas seguem os limites anatômicos
ajustados na análise e somente a máscara segmentada. As quatro regiões permanecem
separadas, inclusive joelho e pé. Os intervalos de 1 °C
da planilha são consolidados em fria (T < 31 °C), neutra (31 ≤ T < 33 °C) e quente
(T ≥ 33 °C), incluindo temperaturas abaixo de 28 ou acima de 36 °C. Não há
importação dos valores da planilha nem conversão para percentuais.

As medidas seguem o nome `COXA_DIREITA_FRENTE_ZONA_FRIA` (e combinações
equivalentes). São armazenadas no modelo existente `medida`/`medida_valor`;
a view `public.vw_termografia_zonas` apresenta uma coluna por combinação,
identificada por atleta e data. Os totais legados continuam representando a zona
selecionada na interface. O endpoint antigo de contagens resumidas permanece
compatível e não inventa medidas regionais sem matrizes e máscaras.
Antes de usar esse registro, aplique a
[migração regional](../backend/migrations/README.md). Coletas antigas não são
alteradas; valores regionais ausentes aparecem como nulos, e não como zero.

Ao atualizar para esse fluxo, reinicie também a API, não somente o Streamlit.
Se a API roda no Docker, use `docker compose up -d --build --no-deps backend`:
reiniciar um Python no host não atualiza o código copiado para a imagem.
Esse comando substitui apenas a API; não restaura o banco nem remove volumes.
Após atualizar arquivos do desktop, feche e reabra sua janela para recarregar
os módulos da interface, pois o launcher desativa o monitoramento de arquivos.
O cliente exige que a resposta confirme a zona pedida; uma API antiga interrompe
o cálculo com orientação de reinicialização, em vez de exibir contagens por
limiar como se fossem da zona. Resultados antigos na sessão são recalculados,
preservando os demais campos do rascunho. A legenda pode ser obtida pelo nome
da zona confirmada quando o campo de apresentação `zone_label` estiver ausente.
Chaves técnicas legadas `hot_pixels`, `hot_percentage` e `hot_overlay` permanecem
nos contratos para compatibilidade, representando a zona selecionada quando
informada. Análises antigas sem zona continuam usando o limiar salvo. Na timeline,
a zona basal é a referência para os percentuais e contornos das duas coletas;
o alinhamento e o mapa de diferenças de temperatura permanecem iguais.

O watershed usa marcadores automáticos da paleta térmica, incluindo os dois
extremos de vermelho do HSV. Linhas finas claras são suprimidas apenas numa cópia
de processamento; os valores RGB originais continuam sendo usados nos cálculos.
O espaço entre as pernas fornece a separação inicial: busca-se um corredor
contínuo de fundo com regiões térmicas dos dois lados, sem exigir magenta.
O corredor deve continuar por uma faixa vertical mais longa, reduzindo a confusão
com pequenas manchas escuras no short.
Fundos neutros (cinza, preto e branco), azulados e roxos também são aceitos.
Regiões neutras largas conectadas à borda da imagem são identificadas como fundo;
regiões brancas quentes isoladas dentro das pernas são preservadas.
Não há preenchimento global
de contornos que transforme as caixas impressas em área válida. O método ainda
depende de contraste/paleta e enquadramento: confira o início das coxas, os pés,
roupas e textos sobrepostos. A segmentação não recupera temperaturas ocultadas
por anotações da câmera.

A prévia exibe a máscara sobre a imagem e oferece dois ajustes manuais:
**Ajustar regiões**, para delimitar explicitamente uma perna e executar watershed
dentro dessa área, e **Ajustar área perna**,
com pincel verde para incluir área e vermelho para excluir área. Os controles
Perna, Pincel e Tamanho do pincel ficam lado a lado no diálogo. Cada ajuste
recalcula as métricas. A barra térmica vertical também é localizada
automaticamente e destacada na prévia. Dentro de **Ajustar regiões**, a opção
**Barra de cores** permite redesenhar sua caixa; a paleta extraída dessa região é a fonte usada
para converter as cores da imagem em temperaturas aproximadas. Para cada perna
e para os totais de frente/costas, a tela
apresenta a quantidade de pixels da zona, a área total segmentada e o percentual
`pixels na zona ÷ área segmentada × 100`. A área do retângulo não é usada como
denominador. Ao lado da máscara, uma segunda prévia usa fundo preto e mantém
visíveis somente os pixels que pertencem às pernas segmentadas e à zona selecionada.

Novas análises usam a versão `thermal-rgb-watershed-v2`. Fundos com cores
semelhantes às próprias pernas ou pouco contraste ainda podem exigir ajuste
manual; a mudança não constitui uma identificação universal de qualquer fundo.
O formato de arquivos permanece o mesmo; análises GrabCut e watershed anteriores conservam máscaras, temperaturas,
divisões e comparação originais, sem resegmentação automática ao abrir a timeline.

Cada perna também pode ser dividida em coxa, joelho, canela e pé. Na seção
**Divisão anatômica**, arraste os três limites no pop-up **Redefinir regiões**.
A orientação é sempre vertical, com Coxa, Joelho, Canela e Pé de cima para baixo.
Os nomes aparecem na imagem e as posições são salvas ao soltar o mouse.
As prévias anatômicas também mostram o contorno da caixa atual de cada perna,
incluindo correções manuais, com rótulos ampliados no pop-up e na etapa de cálculo.
Os rótulos usam a DejaVu Sans incluída em `frontend/streamlit/assets/fonts/`,
com sua licença, sem depender de fontes do sistema ou do fallback do Pillow.
Os rótulos das caixas usam a mesma fonte a 10 px, enquanto a divisão anatômica
permanece em 25 px; o backend distribui
sua cópia em `backend/mac_api/assets/fonts/` para funcionar sem o frontend instalado.
Os percentuais internos
crescem da coxa ao pé mesmo em imagens invertidas. As linhas e
os nomes das partes aparecem na prévia; a contagem usa somente pixels da
máscara. A soma das quatro regiões corresponde ao total da perna. Uma região
com área zero indica que ela não está visível na máscara. Essas métricas são
salvas nos metadados locais, mas não são enviadas ao banco.

Ao confirmar o registro, uma única transação grava em `public.medida_valor` as
medidas `MASSA`, as 16 medidas `EVA_*` quando avaliadas, `PERNA_DIREITA_FRENTE`,
`PERNA_ESQUERDA_FRENTE`, `PERNA_DIREITA_VERSO`,
`PERNA_ESQUERDA_VERSO`, `SOMA_FRENTE`, `SOMA_VERSO` e, quando preenchida,
`OBSERVACOES`. Todas recebem o mesmo jogador e timestamp. Se já houver uma coleta
para o mesmo jogador/data, a interface solicita confirmação antes de substituí-la.

## Abrir e editar análises anteriores

O botão **Ver análises anteriores**, abaixo de **Voltar**, abre um pop-up com
os cartões dos atletas e busca por nome. O cartão inteiro é clicável e pode ser
acionado também pelo teclado, sem um botão de seleção separado. Ao selecionar um
atleta, aparecem suas análises salvas com data e prévias de **Frente** e **Costas**
lado a lado. Ao selecionar um atleta, a lista anterior é limpa antes da consulta
à API e o pop-up indica o carregamento, sem manter os cartões dos atletas na tela
enquanto aguarda a resposta. A API gera cada prévia a partir da imagem original, preservando
proporção e rotação, com limite de 640 × 480 px e redução LANCZOS; o cartão não
reduz novamente a imagem antes de exibi-la. Imagens pequenas não são ampliadas
artificialmente na geração das miniaturas. Em análises parciais, uma vista ausente
aparece como **Imagem não enviada**, sem repetir a outra vista.
As prévias são geradas na leitura: análises existentes não precisam ser salvas
novamente, e os originais, máscaras, temperaturas e arquivos de análise não são
alterados. O pop-up aproveita
quase toda a altura da janela, com margem de 1 rem no topo e embaixo; a lista
acompanha a altura disponível, sem o limite fixo anterior de 450 px.
O cabeçalho, a busca e o botão de voltar ficam fora da rolagem; a lista ocupa
o espaço restante por layout flexível, sem reserva fixa de altura ou faixa
vazia cortando os cartões na base.
As listas usam rolagem interna, sem paginação;
o pop-up pode ser fechado pelo X. Cada nova abertura volta à seleção de atletas
com a busca limpa, sem descartar o rascunho. Dentro da lista de análises, **Voltar
aos atletas** fica abaixo dos cartões. Os cartões de análise também são inteiramente
clicáveis, incluindo a miniatura e a data, tanto aqui quanto em **Mudar Basal** na
timeline, sem botões de seleção separados. A seleção de uma análise fecha o pop-up e
abre o assistente com os dados preenchidos (análises completas começam na primeira
etapa; rascunhos retomam a etapa possível). Isso substitui o
rascunho em andamento, mas não modifica o registro salvo até a confirmação final.
Ao abrir uma análise completa ou parcial, jogador, massa, EVA e observações são
sincronizados explicitamente com os campos da primeira etapa. Isso substitui os
valores vazios deixados pelo último salvamento ou os de outro atleta, sem alterar
o arquivo salvo; campos ausentes continuam vazios e EVA zero é preservado. Ao
avançar e voltar à primeira etapa, os campos são restaurados do rascunho em
edição, inclusive alterações feitas após abrir a análise.

As imagens, rotações, caixas, divisões anatômicas, máscaras corrigidas,
temperaturas e limiares são restaurados. Avançar pelas etapas sem modificações
não executa novamente o GrabCut sobre as máscaras salvas nem reestima as
temperaturas. Alterar uma caixa permite refazer sua segmentação; modificar a
escala térmica, barra de cores ou rotação exige reestimar o campo de temperaturas.
O botão de restaurar a máscara automática permite descartar uma correção anterior.

Atleta e data podem ser alterados. Com a análise completa, **Salvar análise** substitui
a análise original, sem manter uma versão anterior. Se houver outra análise no
destino, o pop-up mostra **Uma análise do atleta já foi realizada nessa data.
Deseja sobrescrevê-la?**, com **Sim, sobrescrever** e **Não, voltar**. Cancelar
preserva o rascunho e ambos os registros; confirmar substitui também o registro
conflitante. A timeline é atualizada após o sucesso.

A API atualiza arquivos e medidas de termografia no banco local. Se a análise
antiga só existia no arquivo local, suas medidas são criadas ao salvar. Não são
criadas colunas ou tabelas novas. Uma edição salva por outra sessão é detectada
e exige reabrir o registro antes de continuar. Saltos e GPS não são excluídos.
Há rollback SQL e recuperação dos arquivos em falhas normais, mas não atomicidade
entre disco e banco em caso de desligamento abrupto: preserve pastas
`.replacing_*` para conferência/recuperação e mantenha backup dos dois conjuntos.

As fichas legadas em PDF, PNG ou JPEG são enviadas ao LlamaParse Cloud, usando
o modo `agentic`, e apresentadas em uma grade editável. Configure
`LLAMA_CLOUD_API_KEY` no ambiente da API ou no `.env` da raiz. Se a chave estiver ausente, a
API falhar ou a resposta não contiver a tabela esperada, o sistema utiliza
automaticamente o extrator local com OpenCV e Tesseract e informa o fallback na
tela. O nome reconhecido é preservado para conferência e a coluna Jogador aceita
somente cadastros existentes, sugeridos pelas mesmas regras de correspondência
de nome usadas no GPS. Após revisão, as fichas podem ser gravadas em lote usando
`MASSA`, `SOMA_FRENTE`, `SOMA_VERSO` e `OBSERVACOES`. O EVA geral do formulário
pode ser reconhecido para conferência, mas não é gravado nem distribuído pelas regiões; as quatro
medidas individuais das pernas permanecem ausentes porque o documento original
não possui essa separação. O lote é atômico: qualquer erro impede todas as
inserções daquele envio.

As imagens e os documentos enviados nunca são armazenados no banco. Os arquivos
temporários locais usados no envio ao LlamaParse são removidos ao final; o
tratamento e a retenção no serviço externo seguem as políticas do LlamaCloud.
Somente as medidas revisadas são persistidas no banco. As imagens térmicas
confirmadas para a timeline são persistidas localmente. A conversão
de cor em temperatura e a identificação das caixas ainda são experimentais e
devem ser validadas antes do uso definitivo.

## Armazenamento local

```env
MAC_ANALYSES_DIR=./data/thermography
```

Esse é o padrão mesmo sem a variável. Caminhos relativos são resolvidos pela
raiz do projeto; no executável, pelo diretório do binário, nunca pela pasta
temporária do PyInstaller. Um caminho absoluto também é aceito. A API precisa
ter permissão de escrita nesse diretório.

```text
data/thermography/
  atleta_123/
    2026-10-14/
      analise_<uuid>/
        metadados.json
        frente/
          original.png
          mascara_direita.png
          mascara_esquerda.png
          temperaturas.npy
        verso/
          original.png
          mascara_direita.png
          mascara_esquerda.png
          temperaturas.npy
```

`original.png` é a imagem orientada/rotacionada usada na análise, sem overlays
adicionados pela aplicação. As máscaras são PNGs binários, não previews
coloridos; a matriz de temperaturas é float32, carregada com `allow_pickle=False`.
O JSON contém ID e nome do jogador, UUID, data da coleta, criação em UTC, massa,
EVA Dor, observações, versões do formato/algoritmo e, por vista: nome do arquivo,
dimensões, rotação, hash SHA-256, escala, limiar em °C e percentual, caixas,
divisões em percentuais e coordenadas em pixels e métricas por perna/região.
Não há referência a coletas do banco. Basal/Atual são seleções de comparação,
não propriedades permanentes da análise.

Uma nova análise recebe um UUID; a edição preserva esse identificador, inclusive
ao mudar atleta/data, e atualiza o instante de gravação. A gravação
é preparada em diretório temporário e publicada por renomeação somente após
concluir todos os arquivos. Ao selecionar um jogador, a timeline lê suas análises
salvas; mudar o basal ou a data atual não modifica os arquivos. Para visualizar Basal/Atual, as
matrizes são carregadas pela API. O mapa calcula `atual − basal` em °C sobre
**a geometria da segmentação basal**, sem modificar os arquivos de nenhuma coleta.

### Alinhamento anatômico na referência basal

O backend utiliza as divisões salvas de coxa, joelho, canela e pé. Cada região
atual é mapeada separadamente para a região correspondente no basal, evitando
que diferenças nas proporções do recorte comparem joelho com coxa, por exemplo.
Dentro de cada região, a posição vertical é proporcional aos seus limites; na
horizontal, as bordas segmentadas de cada linha estabelecem a correspondência
entre as larguras das pernas. A silhueta basal não é deformada. A orientação
horizontal/invertida de registros antigos também é respeitada.

A interpolação pondera apenas temperaturas de pixels válidos da perna, sem
misturar o fundo com a borda. Buracos, linhas e regiões ausentes na coleta atual
não são preenchidos artificialmente: ficam pretos no mapa, assim como o fundo.
Zero corresponde à cor central da paleta; preto não significa ausência de variação. Quando as
coordenadas e máscaras já coincidem, preserva-se a comparação direta; uma edição
somente de máscara em um mesmo campo térmico não cria aquecimento artificial.

Esse alinhamento é **aproximado**, baseado nos limites revisados pelo usuário,
e não corresponde a registro anatômico por pontos ósseos, detecção de postura
ou fluxo óptico. Mudanças de pose, oclusões e divisões incorretas ainda afetam a
comparação. As temperaturas são estimadas de JPEG, não medições radiométricas
originais, e as diferenças não são um diagnóstico de alteração muscular.

### Cores e escala dinâmica do par

A comparação reutiliza a paleta extraída da barra térmica do basal de frente,
compartilhada nas duas pernas e nas vistas de frente e costas. Seu extremo frio
representa diferenças negativas, a cor central representa zero e o extremo
quente representa diferenças positivas. A legenda mostra diferenças em °C,
não temperaturas absolutas. Registros sem imagem/barra basal disponível usam
um gradiente azul–verde–vermelho como alternativa. Essa escolha de cores não
altera o alinhamento nem a escala dinâmica calculada para cada vista.

A escala é calculada **somente entre a imagem basal e a atual da vista aberta**,
compartilhada pelas duas pernas. Seu limite é a maior diferença absoluta válida
após alinhamento, antes da redução da prévia, arredondada para cima em décimos
de °C. Por exemplo, diferenças de −4 a +5 °C usam uma escala de −5 a +5 °C.
Frente e verso podem ter escalas diferentes; nenhuma outra coleta participa do
cálculo. Ao trocar a data ou o basal, a legenda acompanha o novo par. Uma mesma
cor pode representar diferenças distintas em pares diferentes: consulte a legenda.
Sem variação ou sem correspondência, a faixa mínima é ±0,1 °C para manter uma
legenda válida; as mensagens distinguem esses dois casos.

Não é necessária configuração no `.env`: a antiga variável
`MAC_THERMOGRAPHY_DELTA_LIMIT_C` não é mais utilizada. O limite explícito opcional
da operação da API permanece disponível, mas a timeline não o envia. A escala
é uma referência visual, não um limiar clínico.

### Contraste visual com gamma

A timeline inicia com **gamma 0,5**. O controle **Ajuste de contraste (gama)**
fica abaixo da paleta do mapa comparativo em cada aba; os dois controles mantêm
o mesmo valor. Permite ajustar de 0,2 a 1: valores menores afastam diferenças
pequenas da cor
central; 1 restaura o mapeamento linear. O backend aplica a curva simétrica
`sign(ΔT) × (abs(ΔT) / limite)^gamma` somente na busca da cor na paleta. Zero,
o sinal e os extremos permanecem nas mesmas posições de referência. A legenda
usa a mesma transformação e continua rotulada em diferenças reais de °C.
O valor de gamma aparece no próprio controle de contraste.

Não há alteração das temperaturas, diferenças numéricas, segmentação, escala
dinâmica, limiares ou percentuais de área quente. Não há gravação de novas
temperaturas nem migração dos arquivos existentes. Isso é contraste visual,
não tolerância térmica: a amplificação também pode realçar ruído e artefatos
de alinhamento. O ajuste é implementado com NumPy, mantendo as imagens Pillow
e os previews do Streamlit, sem Matplotlib ou outra dependência adicional.
A operação `compare_temperature_maps` aceita `gamma` opcional e preserva 1
como padrão para clientes da API; a timeline envia explicitamente o valor do
controle, incluído na chave de cache de cada comparação.

O critério salvo no basal (zona térmica, ou limiar nas análises legadas) é
aplicado às duas coletas para os percentuais de área selecionada. Esses indicadores
usam os pixels nativos de cada coleta, não os pixels interpolados do mapa;
as zonas e os limiares originais permanecem
nos arquivos salvos, sem descrições auxiliares na tela. O gradiente de diferenças
não depende desses limiares. Cálculos e
carregamentos são armazenados em cache por até 60 segundos para cada par.

A timeline apresenta os percentuais da zona (ou área quente legada) por perna e
por coxa, joelho, canela e pé, nas vistas de frente e costas. Cada região mostra
o percentual atual, o basal e a diferença em pontos percentuais. Regiões sem
pixels válidos são identificadas sem ocultar as demais. As divisões e métricas
são as calculadas pelo backend a partir de cada análise salva; não há novo
alinhamento nem alteração do denominador. A comparação não modifica os arquivos
salvos e não exige migração.
Os indicadores aparecem na coluna à direita das imagens em dois cartões compactos,
um por perna. Cada cartão contém linhas para total, coxa, joelho, canela e pé,
com colunas fixas de Atual, Basal e Δ p.p. A tipografia é reduzida para exibir
os números completos, sem o truncamento dos widgets de métricas em colunas
estreitas. Em painéis muito estreitos, os cartões se empilham para preservar a leitura.
Os deltas usam cor neutra, sem sugerir avaliação clínica automática de melhora
ou piora. Uma região sem dados mostra um traço e mantém as outras visíveis.
Na etapa 7, as duas gravações fazem parte de uma única operação da API. As rotas
antigas de gravação independente continuam disponíveis por compatibilidade,
mas não são usadas pelo novo botão. Análises antigas continuam na timeline sem
criar medidas SQL retroativamente.

O armazenamento pertence à máquina do **backend**, não ao navegador. O frontend
não grava diretamente em disco. Faça backup dessa pasta; ela está fora do Git
e do contexto de build Docker por conter dados e imagens dos atletas.
Arquivos antigos não são migrados da memória: análises ainda abertas precisam
ser confirmadas em **Salvar análise** para persistir ambos os conjuntos de dados.

No Compose, `./data/thermography` do computador é montada diretamente em
`/app/data/thermography` do backend. Crie a pasta antes de iniciar:

```bash
mkdir -p data/thermography
```

Os arquivos aparecem no repositório local e continuam fora do Git. Parar ou
recriar containers não remove essa pasta. No Linux, ela deve ser gravável pelo
UID 1000 utilizado pela API; se seu usuário tiver outro UID, ajuste as permissões
da pasta antes de executar. Ao trocar `MAC_ANALYSES_DIR` no Docker, ajuste também
o ponto de montagem. Os testes removem essa montagem e usam um diretório isolado.

A timeline possui o seletor **Jogador da timeline**, independente da Nova análise.
Iniciar outra análise não limpa esse filtro. Adicionar uma análise à timeline
seleciona o respectivo jogador automaticamente.

Instalações que usavam o volume `thermal-analyses` precisam copiar seus arquivos
para a pasta do host antes de trocar a montagem. Mantenha esse volume antigo como
backup até conferir a migração; não o remova com `docker volume rm` ou `down -v`.

Contratos de imagens, matrizes e rotação: [API térmica](api.md#contrato-de-termografia).

## Timeline em página própria

A consulta das análises locais e a comparação Basal × Atual ficam na página
**Timeline térmica**, acessível pelo menu lateral. A etapa 7 da Termografia
oferece **Salvar análise**, mantendo o mesmo formato de armazenamento completo local.
Na etapa 6, cada perna é apresentada com o percentual de pixels quentes e a
área total (pixels), por perna e por região anatômica; a esquerda aparece primeiro.

Na interface, a vista posterior é identificada como **Costas**. Chaves da API,
colunas existentes (`Verso`, `SOMA_VERSO` etc.) e a pasta local `verso/` são
preservadas para manter compatibilidade com o banco e as análises já salvas.

## Registro unificado

Jogador e massa são obrigatórios; observações continuam opcionais. O EVA usa o diagrama regional, não um campo geral. A data
confirmada vale tanto para as medidas quanto para os arquivos da timeline. A API
usa o nome do cadastro do atleta e recalcula os pixels quentes de cada perna com
as matrizes térmicas e máscaras recebidas, na mesma precisão do arquivo salvo.
São gravadas as medidas por perna, as somas de frente/costas, massa, EVA e, quando
preenchidas, observações. Nenhuma coluna ou tabela adicional é criada.

A operação aceita somente `MAC_DB_TARGET=local`. Se já existir coleta térmica
para o jogador/data, retorna conflito e exige confirmação antes de substituí-la.
Após sucesso, o assistente já fica limpo para um novo registro e a confirmação
aparece em toast. Para editar a coleta recém-salva, abra-a em **Ver análises
anteriores**; salvar essa edição atualiza a mesma análise, sem duplicá-la.
Os caches do histórico térmico e mural de jogadores são
invalidados, e o jogador salvo fica selecionado na timeline.

As medidas são inseridas em uma transação SQL, e os arquivos são preparados
antes do commit. Uma falha de arquivos causa rollback SQL; uma falha normal de
commit remove somente a pasta criada nessa tentativa, preservando análises
anteriores. Não há transação distribuída entre PostgreSQL e filesystem: uma
interrupção abrupta do processo/máquina ou falha na própria limpeza pode exigir
conferência manual. Erros não são apresentados como sucesso; em caso de resposta
incerta, consulte o registro antes de reenviar.
