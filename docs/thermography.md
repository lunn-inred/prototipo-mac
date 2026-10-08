# Termografia

[← Voltar ao README](../README.md)

## Fluxo da página

A página `frontend/streamlit/pages/Termografia.py` registra uma nova análise a partir das imagens
de frente e verso. Os componentes aparecem na ordem **Nova análise térmica**,
**Timeline térmica** (seção independente, com título visível) e **Envio de Formulário**, este último sempre
aberto para importar fichas manuscritas. Ao adicionar a análise à timeline ou
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
6. Cálculo da termografia: Tmin/Tmax, limiar abaixo da escala, métricas,
   tabela do registro e confirmação do envio. Cada vista apresenta a imagem
   original com caixas, as pernas segmentadas sem fundo e os pixels quentes.

As correções de caixas, máscaras e divisões são feitas em pop-ups. Na divisão
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

Durante a sessão, o botão **Adicionar à timeline** mantém temporariamente as
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
Os percentuais internos
crescem da coxa ao pé mesmo em imagens invertidas. As linhas e
os nomes das partes aparecem na prévia; a contagem usa somente pixels da
máscara. A soma das quatro regiões corresponde ao total da perna. Uma região
com área zero indica que ela não está visível na máscara. Essas métricas são
temporárias na interface; não são enviadas ao banco.

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
Somente as medidas revisadas são persistidas pelo protótipo. A conversão
de cor em temperatura e a identificação das caixas ainda são experimentais e
devem ser validadas antes do uso definitivo.

Contratos de imagens, matrizes e rotação: [API térmica](api.md#contrato-de-termografia).
