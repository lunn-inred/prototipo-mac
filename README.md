# Protótipo — MAC Performance

Protótipo visual das telas **Análise de Salto** e **Monitoramento GPS**, feito em Streamlit com dados fictícios.

## Como executar

```powershell
python -m pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

Preencha o arquivo `.env` com as credenciais de conexão disponíveis em
**Supabase > Project Settings > Database**. Esse arquivo contém dados sensíveis
e está ignorado pelo Git; `.env.example` contém somente o modelo versionável.

O módulo `database.py` centraliza a configuração e abre exclusivamente conexões
somente leitura. Ele ativa o modo read-only durante o handshake, reforça o modo
na sessão e verifica a configuração antes de entregar a conexão:

```python
from database import database_connection

with database_connection() as connection:
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM public.atleta ORDER BY id_atleta')
        atletas = cursor.fetchall()
```

Os filtros de atleta, posição e período são interativos. Ao selecionar um atleta, os cartões e os gráficos alternam para a visualização individual.

Na página de Monitoramento GPS, as variáveis de carga permitem seleção múltipla. Cada variável selecionada adiciona seu próprio gráfico de evolução ao painel.
