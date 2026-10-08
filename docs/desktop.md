# Aplicativo desktop

[← Voltar ao README](../README.md)

## Visão geral

O cliente também pode ser executado em uma janela nativa com
`streamlit-desktop-app`. O conteúdo continua sendo renderizado pelo Streamlit,
mas fica dentro de uma WebView, sem abrir uma aba do navegador. Durante o
desenvolvimento com `python desktop.py`, a FastAPI é iniciada separadamente. No
executável empacotado, API, Streamlit e WebView são iniciados automaticamente.

## 1. Instale as dependências

Com o ambiente virtual ativado, instale as dependências do desktop. Esse arquivo
também instala o conteúdo de `requirements.txt`:

```bash
python -m pip install -r requirements-desktop.txt
```

No Ubuntu/Debian, instale também as bibliotecas do sistema:

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-por libxcb-cursor0
```

No Windows e no macOS essas bibliotecas Linux não são necessárias.

## 2. Configure o `.env`

Use o mesmo `.env` da raiz, compartilhado com a API. Copie `.env.example` e
preencha as credenciais do banco. O [guia de configuração](configuration.md)
contém o modelo semipronto para copiar e colar. Não crie outro `.env` para o desktop.

## 3. Execute em desenvolvimento

No primeiro terminal, inicie a API:

```bash
source .venv/bin/activate
uvicorn backend.mac_api.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

No segundo terminal, inicie Streamlit e WebView:

```bash
source .venv/bin/activate
python desktop.py
```

O `python desktop.py` não inicia nem encerra a API. Ele utiliza a URL configurada
em `MAC_API_BASE_URL`, que no modelo aponta para `http://127.0.0.1:8000`.
Quando a inicialização estiver correta, seu terminal apresentará:

```text
[MAC Desktop] Usando API externa em http://127.0.0.1:8000.
You can now view your Streamlit app in your browser.
URL: http://localhost:56789
```

Valide o backend em `http://127.0.0.1:8000/health` e acesse o Swagger em
`http://127.0.0.1:8000/docs`.

No Windows PowerShell, substitua `source .venv/bin/activate` por:

```powershell
.venv\Scripts\Activate.ps1
```

## 4. Gere um executável

Para gerar o executável da plataforma atual:

```bash
python -m PyInstaller --clean --noconfirm desktop/desktop.spec
```

O resultado fica em `dist/MAC Performance` no Linux. No Windows, o arquivo terá
extensão `.exe`. Antes de executá-lo, copie o mesmo `.env` para o diretório do
binário:

```bash
cp .env "dist/.env"
```

Abra o executável Linux:

```bash
"./dist/MAC Performance"
```

No Windows PowerShell, copie a configuração e abra o `.exe` com:

```powershell
Copy-Item .env "dist\.env"
& ".\dist\MAC Performance.exe"
```

O `.env` não é incluído no pacote nem versionado, evitando que credenciais sejam
gravadas no binário. O executável inicia a API automaticamente usando esse
arquivo único. Diferentemente de `python desktop.py`, não é necessário executar
o comando `uvicorn` antes de abrir o binário. Ao fechar o executável, seus
processos internos da API e do Streamlit são encerrados.

O `.env` concede acesso ao banco e deve ser entregue somente a máquinas
confiáveis. Para distribuição fora de um ambiente controlado, prefira hospedar
a API e não distribuir credenciais do Supabase.

O build é específico do sistema operacional: gere a versão Windows no Windows,
a versão Linux no Linux e a versão macOS no macOS. No Linux, a interface usa
PySide6/Qt6; no Windows, a WebView depende do Microsoft Edge WebView2,
normalmente já instalado. O build inclui o
Tesseract e os dados de idioma quando eles estão instalados na máquina usada
para empacotar, necessários à leitura dos formulários legados.

Arquivos relacionados:

- `desktop/launcher.py`: inicia a interface e, no binário, também a API;
- `desktop.py`: entrada de compatibilidade para o launcher;
- `desktop/desktop.spec`: inclui páginas, assets, dependências dinâmicas e Tesseract;
- `requirements-desktop.txt`: dependências adicionais do cliente desktop;
- `.env.example`: único modelo de configuração da aplicação completa.

O primeiro início do executável único pode demorar alguns segundos enquanto os
arquivos internos são extraídos. A versão web e os comandos existentes não são
alterados por essa modalidade.

## Backend em Docker com janela local

Com as dependências desktop instaladas e o `.env` preenchido:

```bash
docker compose up --build -d backend
python desktop.py
```

Mantenha `MAC_API_BASE_URL=http://127.0.0.1:8000` para acessar a porta publicada
pelo container. A janela WebView roda no sistema operacional local; Docker
executa apenas a API nesse modo. Fechar a janela não encerra o container:

```bash
docker compose stop backend
```

O executável standalone não precisa desse container: ele inicia sua própria API.
Para executar a aplicação inteira no navegador com Docker, veja [web](web.md#docker).
