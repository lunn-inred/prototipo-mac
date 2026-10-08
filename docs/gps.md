# Monitoramento de GPS

[← Voltar ao README](../README.md)

## Monitoramento de GPS

### Extração de relatórios GPS

O botão **Adicionar novos arquivos**, no topo da página **Monitoramento GPS**,
permite enviar um ou vários relatórios PDF diretamente pelo navegador. Para cada
relatório, o extrator renderiza e analisa por OCR as duas últimas páginas (ou a
única página disponível), mostra uma prévia das tabelas reconhecidas e permite
corrigir os valores diretamente em uma grade editável. A grade e o CSV usam as
mesmas colunas e a mesma ordem de `public.vw_medidas_gps`. Equipe, adversário e
data são lidos da primeira linha da página das métricas e ficam bloqueados;
o grupo é sempre GPS. Os campos técnicos de
origem, página, tabela e linha não aparecem. Um único CSV consolidado é gerado
com os dados revisados, em UTF-8 com BOM e usando ponto e vírgula como separador.

O processamento requer as bibliotecas Python declaradas em `requirements.txt` e
o executável Tesseract com o idioma português. No Streamlit Community Cloud, os
pacotes de sistema necessários estão declarados em `packages.txt`. Em uma
instalação local no Windows, instale o Tesseract, inclua o executável no `PATH` e
confirme com:

```powershell
tesseract --list-langs
```

O idioma `por` deve aparecer na lista; se ele não estiver disponível, o extrator
usa `eng` como alternativa. Upload, OCR e edição não gravam no Supabase; os dados
só podem ser enviados após a validação e a confirmação descritas abaixo. O
painel continua consultando a view somente leitura `public.vw_medidas_gps`.

#### Conflito entre OpenCV e img2table

O `img2table` requer a distribuição contrib do OpenCV. Não mantenha
`opencv-python` ou `opencv-python-headless` instalados junto com
`opencv-contrib-python-headless`, pois esses pacotes compartilham o mesmo módulo
`cv2` e podem remover `cv2.ximgproc.niBlackThreshold`. Para recuperar um ambiente
local que apresente esse erro, execute com o ambiente virtual ativado:

```bash
python -m pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python opencv-contrib-python-headless
python -m pip install -r requirements.txt
python -c "import cv2; print(cv2.__version__); print(hasattr(cv2.ximgproc, 'niBlackThreshold'))"
```

A última linha deve mostrar `True`. As linhas impressas pelo Tesseract com versão,
bibliotecas e instruções de CPU (`AVX`, `FMA` e `SSE`) são apenas informativas e
não indicam falha.

### Envio dos dados revisados ao banco

Depois da conferência na grade, o botão **Validar para envio** verifica os dados
dos cabeçalhos, os valores numéricos, os cadastros auxiliares e as medições
já existentes. O nome do PDF é livre e serve apenas para identificar a origem.
Exemplo de primeira linha reconhecida na página:

```text
RELATÓRIO DE ATIVIDADES MAC X IAPE (MD) DOMINGO, MARÇO 1, 2026 - 03:06:22 PM PÁGINA 5/6
```

A gravação só acontece após **Confirmar envio ao banco**. Cada PDF usa uma
transação independente e as medições duplicadas são ignoradas. O timestamp do
cabeçalho da página é gravado em `partida.data` e `medida_valor.data`.
A primeira linha acima produz `MAC`, `IAPE` e `2026-03-01 15:06:22`.
O leitor aceita meses por extenso em português e horários AM/PM, preservando
os segundos. Também aceita datas numéricas com `/`, `.` ou `-`; sem horário,
usa-se `00:00`.
O texto do PDF é utilizado quando disponível; páginas digitalizadas usam OCR.
Cabeçalhos ausentes, inválidos ou divergentes entre páginas bloqueiam o envio,
sem usar o nome do arquivo como alternativa. Extrações de sessões antigas devem
ser refeitas para obter os metadados da página.
Os resultados guardam a versão do extrator. Quando ela muda, a aplicação solicita
nova extração e bloqueia validação e envio dos resultados antigos. Os dados e as
edições anteriores são preservados até a substituição por uma nova extração;
uma tentativa que falhe não apaga esses dados. Ao modificar a lógica de extração
de forma incompatível, incremente `EXTRACTION_VERSION` em `gps_extraction.py`.

O nome reconhecido no PDF permanece visível e bloqueado para conferência. O
sistema tenta associá-lo a um jogador existente por `nome`, `apelido` ou
`nome_alternativo`, ignorando caixa, acentos e pontuação. A grade aceita apenas a
seleção de jogadores cadastrados, usa a posição do cadastro e bloqueia validação
e envio enquanto houver linhas sem associação única. A importação GPS nunca cria
jogadores automaticamente.

As operações de escrita reutilizam as credenciais `SUPABASE_DB_*` já configuradas
para as consultas do painel. A separação continua existindo nas conexões: o
painel abre transações somente leitura, enquanto a confirmação da importação abre
uma transação de escrita. O usuário configurado precisa de `USAGE` no schema
`public`, `SELECT` e `INSERT` em `atleta`, `partida`, `grupo_medida`, `medida` e
`medida_valor`, além de acesso às sequências `serial` correspondentes.

A página `frontend/streamlit/pages/Monitoramento_GPS.py` utiliza dados reais da view
`public.vw_medidas_gps`, carregados por `gps_data.py` e mantidos em cache por
cinco minutos. O seletor dos gráficos disponibiliza todas as medidas numéricas
presentes na view:

- `accel_de_cel_efforts`;
- `accel_de_cel_efforts_per_minute`;
- `distance_km`: distância total em quilômetros;
- `high_speed_distance`: distância HSR, convertida de quilômetros para metros;
- `high_speed_efforts`;
- `max_acceleration`;
- `max_deceleration`;
- `maximum_velocity_km_h`;
- `meterage_per_minute`;
- `player_load_per_minute`;
- `sprint_efforts`: número de sprints.

Os filtros de atletas, posição e período são compartilhados com a página de
saltos. A posição limita as opções do seletor múltiplo de atletas. Os cartões
apresentam a média e o desvio padrão populacional dos registros filtrados no
período completo. Nos gráficos, os valores são agrupados por data de coleta e
cada série de atleta, posição e elenco recebe uma faixa sombreada entre
`média diária − DP diário` e `média diária + DP diário`. O hover informa a média
e o DP de cada data, além do nome do time adversário; com uma única medição
válida no dia, o DP diário é zero. Quando houver mais de um adversário registrado
na mesma data, o hover apresenta os nomes juntos. Quando `adversario` for `MAC`,
o nome exibido é obtido da coluna `equipe`, cobrindo partidas cadastradas com a
orientação invertida. Se `adversario` estiver vazio e `equipe` seguir o formato
`Nome X MAC`, o trecho `Nome` é usado como adversário.

Foram removidos os componentes de distância em sprint, acelerações e
desacelerações separadas, player load total e zonas de velocidade, pois essas
métricas não estão disponíveis na view no formato exigido pelo protótipo.
