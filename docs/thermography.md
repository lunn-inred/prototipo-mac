# Termografia

[← Voltar ao README](../README.md)

## Fluxo da página

A página `frontend/streamlit/pages/Termografia.py` registra uma nova análise a partir das imagens
de frente e verso. Os componentes aparecem na ordem **Nova análise térmica** e
**Envio de Formulário**, este último sempre aberto para importar fichas manuscritas.
A consulta e a comparação de análises ficam na página separada **Timeline Termo**.
Ao adicionar a análise à timeline ou
registrá-la no banco, uma janela solicita a data da coleta e apresenta a data
atual de São Paulo como padrão. Quando omitida em uma chamada à API, a mesma
data padrão é aplicada pelo serviço.

A nova análise utiliza um assistente com **Continuar** e **Voltar**, apresentando
somente uma etapa por vez:

1. Jogador, massa, EVA Dor e observações opcionais.
2. Upload de frente/verso, prévia e botão para girar 90° para a direita.
3. Caixas das pernas e barra de cores.
4. Divisão de cada perna em coxa, joelho, canela e pé, com uma prévia anatômica por vista.
5. Segmentação automática por GrabCut e correção manual das máscaras.
6. Cálculo da termografia: Tmin/Tmax, limiar abaixo da escala e métricas.
   Cada vista apresenta a imagem
   com divisões e nomes das áreas anatômicas, as pernas segmentadas sem fundo
   e os pixels quentes.
7. Resumo da coleta: totais de frente/verso e tabela revisável no mesmo componente.
   Adicionar à timeline fica à esquerda de registrar no banco; Voltar e iniciar
   outra análise aparecem abaixo, sem repetir as prévias.

As correções de caixas, máscaras e divisões são feitas em pop-ups. Na divisão
anatômica, o GrabCut ainda não é executado: os limites são definidos sobre as
caixas das pernas e mantêm suas coordenadas depois da segmentação. Os canvases
dos pop-ups são centralizados.

Os diálogos de edição ocupam até 96% da largura da janela, limitados a 1600 px,
e seu conteúdo usa 100% dessa área. Um componente mede a altura útil da janela
e a posição do editor, reservando espaço para controles, toolbar e botões.
O canvas reduz ou amplia sua prévia para caber nessa área, sem scroll do diálogo;
a medição é repetida após a montagem/transição da janela, e a última dimensão
válida é preservada para evitar reabrir com uma prévia pequena. Na primeira
abertura, o editor aguarda uma medição estável; não desenha uma prévia provisória
menor. A medição continua disponível mesmo quando a montagem do navegador é tardia.
Os botões têm
uma margem inferior reservada. **Concluir** é a ação destacada; aplicar,
restaurar e confirmar registros são ações secundárias. As barras cinzas do canvas
(Undo, Redo, Clear e botões de zoom) ficam ocultas; o zoom pela roda do mouse
permanece disponível nos editores de caixas e máscaras. Nos diálogos de registro,
**Concluir** apenas fecha: a gravação exige clicar explicitamente em confirmar.
a roda do mouse fica reservada ao zoom da imagem. A página usa 90%
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
As vistas de frente e verso são apresentadas lado a lado, com as prévias
centralizadas e botões que ocupam a largura disponível de suas colunas.
Na divisão anatômica, aparece somente a prévia com nomes e limites das áreas.
Na segmentação, a segunda prévia mostra a área completa das pernas sem fundo.
A filtragem de pixels quentes aparece
somente na etapa de cálculo, após a definição da escala e do limiar.

O botão **Adicionar à timeline** salva localmente as
imagens, matrizes de temperatura, caixas e segmentações anatômicas. A máscara de
pixels quentes e as métricas não são congeladas: elas são recalculadas em tempo
real pelos controles das coletas basal e atual. Os cartões da timeline permitem
marcar independentemente uma coleta **Basal** e uma coleta **Atual** do mesmo
jogador. A interface alerta quando a Atual antecede a Basal, sem bloquear a
comparação. Nas abas de
frente e verso, a comparação exibe as duas imagens, mapas normalizados por perna
e as métricas atuais com deltas em relação à basal. Vermelho identifica pixels que
ficaram quentes, amarelo os persistentes e azul os resolvidos.

Na nova análise, o usuário informa jogador, massa, data da coleta, EVA Dor e,
opcionalmente, observações. O sistema tenta identificar automaticamente as duas
caixas R1/R2; quando elas não existem ou estão incorretas, cria regiões iniciais
que podem ser redesenhadas pelo usuário. A lateralidade é invertida entre frente
e verso e o OCR é aplicado às regiões superior e inferior
do canto direito para preencher automaticamente Tmax e Tmin. Os campos continuam
editáveis e usam 20–40 °C como valores iniciais quando o OCR não reconhece uma
escala válida. Em seguida, o sistema estima a temperatura dos pixels pela barra
térmica lateral e conta como quentes os pixels a partir de 90% da escala por
padrão: `Tmin + 0,90 × (Tmax − Tmin)`. O usuário ainda pode ajustar esse limiar
no slider antes do cálculo. Em cada imagem, um seletor
permite controlar o limiar pela porcentagem da escala (modo padrão) ou
diretamente pela temperatura em °C. Ao alternar o modo, o sistema preserva o
limiar equivalente; a análise e os resultados continuam usando a temperatura
convertida em °C.

Dentro de cada região, o GrabCut separa os pixels da perna do fundo. A prévia
exibe a máscara sobre a imagem e oferece dois ajustes manuais: **Corrigir Áreas**, para redesenhar o retângulo de cada perna, e **Corrigir segmentação**,
com pincel verde para incluir área e vermelho para excluir área. Os controles
Perna, Pincel e Tamanho do pincel ficam lado a lado no diálogo. Cada ajuste
recalcula as métricas. A barra térmica vertical também é localizada
automaticamente e destacada na prévia. Dentro de **Corrigir Áreas**, a opção
**Barra de cores** permite redesenhar sua caixa; a paleta extraída dessa região é a fonte usada
para converter as cores da imagem em temperaturas aproximadas. Para cada perna
e para os totais de frente/verso, a tela
apresenta a quantidade de pixels quentes, a área total segmentada e o percentual
`pixels quentes ÷ área segmentada × 100`. A área do retângulo não é usada como
denominador. Ao lado da máscara, uma segunda prévia usa fundo preto e mantém
visíveis somente os pixels que pertencem às pernas segmentadas e alcançam o
limiar térmico selecionado.

Cada perna também pode ser dividida em coxa, joelho, canela e pé. Na seção
**Divisão anatômica**, arraste os três limites no pop-up **Editar divisões na imagem**.
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
medidas `MASSA`, `EVA_DOR`, `PERNA_DIREITA_FRENTE`,
`PERNA_ESQUERDA_FRENTE`, `PERNA_DIREITA_VERSO`,
`PERNA_ESQUERDA_VERSO`, `SOMA_FRENTE`, `SOMA_VERSO` e, quando preenchida,
`OBSERVACOES`. Todas recebem o mesmo jogador e timestamp. Uma coleta já
existente para o mesmo jogador e data é rejeitada para evitar duplicidade.

As fichas legadas em PDF, PNG ou JPEG são enviadas ao LlamaParse Cloud, usando
o modo `agentic`, e apresentadas em uma grade editável. Configure
`LLAMA_CLOUD_API_KEY` no ambiente da API ou no `.env` da raiz. Se a chave estiver ausente, a
API falhar ou a resposta não contiver a tabela esperada, o sistema utiliza
automaticamente o extrator local com OpenCV e Tesseract e informa o fallback na
tela. O nome reconhecido é preservado para conferência e a coluna Jogador aceita
somente cadastros existentes, sugeridos pelas mesmas regras de correspondência
de nome usadas no GPS. Após revisão, as fichas podem ser gravadas em lote usando
`MASSA`, `EVA_DOR`, `SOMA_FRENTE`, `SOMA_VERSO` e `OBSERVACOES`; as quatro
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

Cada confirmação cria um UUID diferente, inclusive na mesma data. A gravação
é preparada em diretório temporário e publicada por renomeação somente após
concluir todos os arquivos. Ao selecionar um jogador, a timeline lê suas análises
salvas; **Limpar seleção** não apaga arquivos. Para visualizar Basal/Atual, as
matrizes são carregadas pela API e as métricas recalculadas com os limiares escolhidos.
Não é necessário registrar a coleta no banco para salvar na timeline, nem salvar
na timeline para enviar somente medidas ao banco.

O armazenamento pertence à máquina do **backend**, não ao navegador. O frontend
não grava diretamente em disco. Faça backup dessa pasta; ela está fora do Git
e do contexto de build Docker por conter dados e imagens dos atletas.
Arquivos antigos não são migrados da memória: análises ainda abertas precisam
ser confirmadas novamente em **Adicionar à timeline**.

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
**Timeline Termo**, acessível pelo menu lateral. A etapa 7 da Termografia
continua oferecendo **Adicionar à timeline**, com o mesmo armazenamento local.
Na etapa 6, cada perna é apresentada com o percentual de pixels quentes e a
área total (pixels), por perna e por região anatômica; a esquerda aparece primeiro.
