# Mapa corporal experimental — Body Muscles

[← Voltar ao README](../README.md)

## Exploração

Abra **Mapa corporal (experimental)** no menu após o login normal do aplicativo.
Para testar somente a página, sem API, banco ou autorização Google:

```bash
python -m streamlit run frontend/streamlit/pages/Mapa_Corporal_Lab.py
```

A página temporária permite explorar as **89 regiões originais** do
`@emmorts/body-muscles` 2.1.1 ou ativar **Agrupamento personalizado**, com 16 áreas.
Selecione frente, costas ou ambas; clique numa região e altere sua intensidade
inteira de 0 a 10 pelo campo numérico ou controle deslizante ao lado do mapa.
Também é possível selecionar pelo teclado e ativar/desativar nomes e animações.
Os lados são os do atleta, não os do observador.
Nos dois modos, somente uma região/grupo fica selecionado para edição por vez.
Selecionar outra parte remove o destaque anterior, mas preserva sua intensidade
e coloração. Clicar novamente na parte ativa mantém a seleção.

**Valores recebidos no Python** mostra o estado recebido do JavaScript. O botão
**Limpar exploração** zera somente este laboratório. Trocar de vista ou navegar
entre páginas preserva o estado na mesma sessão; não há persistência após
encerrar a sessão/reiniciar a aplicação. Nenhum atleta é associado e nenhuma
medida é enviada à API, banco, termografia ou Drive. A paleta é demonstrativa,
não uma escala clínica aprovada para o projeto.

## Integração e distribuição

A opção **Agrupamento personalizado** vem desmarcada. Ao ativá-la, cada grupo
recebe um único valor/seleção e colore juntas suas regiões originais. Os nomes
passam a ser em português; outras regiões ficam esmaecidas e não são editáveis.
As divisões internas do SVG permanecem: não houve fusão geométrica dos paths.

Definição em `components/body_muscles_groups.py`, espelhada para esquerda/direita:

| Área | Frente | Costas |
|---|---|---|
| Coxa | quads + adductors + hip-flexor | hamstrings-lateral + hamstrings-medial |
| Joelho | knee | knee-back |
| Canela | tibialis-anterior | calves-gastroc-medial + calves-gastroc-lateral + calves-soleus |
| Pé | foot | foot-back |

As regiões são identificadas por vista/parte/lado, como `front-coxa-right`.
Frente/costas e esquerda/direita são independentes. O modo original e o modo
personalizado mantêm estados separados na sessão; alternar não converte valores
por média/máximo nem os descarta. **Limpar exploração** limpa ambos os modos.

- Componente: `frontend/streamlit/components/body_muscles.py`.
- Página: `frontend/streamlit/pages/Mapa_Corporal_Lab.py`.
- Assets: `frontend/streamlit/assets/vendor/body-muscles/2.1.1/`.
- O JavaScript oficial é incorporado ao componente Streamlit v2, sem CDN,
  `eval`, instalação npm em runtime ou dependência de React.
- O evento transporta `{active, bodyState}`; cada região contém intensidade e
  seleção. O Python confere identificadores e intensidades antes de apresentar
  o resultado. Isso não substitui a futura validação de domínio na API.
- Um espelho de sessão preserva o estado ao desmontar a página. O componente
  destrói listeners/instância ao ser desmontado e usa isolamento de estilos.
- Os assets são incluídos no package-data do Python e já são abrangidos pelo
  diretório de assets coletado no spec desktop e pelo COPY do frontend Docker.
  Não exige Node.js nem internet no computador do usuário para renderizar o mapa;
  o login e os demais serviços do aplicativo mantêm suas dependências normais.

A paleta própria e a persistência regional de EVA ainda não foram implementadas.
Este laboratório não modifica o campo EVA existente nem o backend.

## Licença e atribuição

Body Muscles © 2024 Ivan Vulović. Este produto inclui software desenvolvido por
Ivan Vulović, originalmente em https://github.com/vulovix/body-muscles.
A distribuição utilizada é `@emmorts/body-muscles`, mantida por emmorts:
https://github.com/emmorts/body-muscles, sob **Apache License 2.0**.

O texto completo da licença e o NOTICE foram preservados nos assets, junto com
o changelog do fornecedor. A página também apresenta os créditos. Proveniência,
versão, hashes e o aviso de modificação/normalização do JSON estão documentados em
[PROVENANCE.md](../frontend/streamlit/assets/vendor/body-muscles/2.1.1/PROVENANCE.md).
A integração e o agrupamento MAC são separados do fornecedor; os arquivos de
geometria e a paleta originais não foram alterados. Ao redistribuir, preserve LICENSE/NOTICE e identifique futuras
alterações nos arquivos modificados, conforme os termos da licença.
