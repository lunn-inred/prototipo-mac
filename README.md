# Protótipo — MAC Performance

Protótipo em Streamlit para estudar a lógica de visualização e cálculo das
métricas de desempenho do MAC. O projeto possui páginas de monitoramento de
saltos e GPS e utiliza Plotly para a construção dos gráficos.

## Sumário

- [Como executar](#como-executar)
- [Monitoramento de Salto](#monitoramento-de-salto)
  - [Instruções SQL](#instruções-sql)
- [Monitoramento de GPS](#monitoramento-de-gps)

## Como executar

Crie e ative um ambiente virtual, instale as dependências e copie o modelo de
configuração:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

No Windows PowerShell, a ativação do ambiente pode ser feita com:

```powershell
.venv\Scripts\Activate.ps1
```


O `.env` contém dados sensíveis e está ignorado pelo Git. O arquivo
`.env.example` contém somente o modelo versionável.

Execute o protótipo com:

```bash
streamlit run app.py
```

O módulo `database.py` centraliza a conexão com o PostgreSQL do Supabase. As
conexões abertas pelo protótipo são configuradas e verificadas como somente
leitura antes de serem disponibilizadas às páginas.

## Monitoramento de Salto


## Monitoramento de GPS

