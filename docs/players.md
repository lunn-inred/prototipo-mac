# Jogadores

[← Voltar ao README](../README.md)

## Cadastro e mural

A página inicial lista o elenco e resume CMJ, distância GPS e a EVA Dor mais
recente. O gerenciador permite cadastrar, editar, desativar e reativar atletas. Somente o
nome é obrigatório; `nome_alternativo` não é exposto no CRUD e permanece
inalterado nas edições. A desativação muda `public.atleta.status` de `ativo` para `inativo`, sem apagar
o cadastro ou suas medições. Novos cadastros recebem `ativo` por padrão.
O calendário de nascimento aceita de 01/01/1900 até hoje no cadastro e na edição,
sem idade mínima; o preenchimento continua opcional. Uma data anterior a 1900
já cadastrada permanece acessível na edição. O seletor não oferece datas futuras.
O status é exibido no mural; jogadores inativos continuam disponíveis para
consulta ao histórico. Não há mais endpoint de exclusão de jogadores.

Sem atletas cadastrados, o gerenciador continua disponível e abre expandido para
o primeiro cadastro. Editar e alterar status só ficam disponíveis após existir
um jogador. O cadastro local não depende de já ter sincronizado com o Drive.

O EVA exibido é o maior dos 16 valores regionais da última coleta térmica,
calculado pela view. Não existe medida geral `EVA_DOR`. Uma última coleta sem
avaliação regional exibe **Sem EVA**, sem herdar o valor de coletas anteriores.

O mural é dividido em **Ativos** e, logo abaixo, **Inativos**, com os mesmos
cards. Os filtros e a ordenação se aplicam às duas seções. Desativar ou reativar
um jogador o move para a seção correspondente, sem alterar suas medições.
A ordenação padrão é alfabética pelo nome de exibição (apelido, quando preenchido;
caso contrário, nome). A opção de ordenar por risco continua disponível no filtro.

Na aba **Desativar/reativar jogador**, selecione o jogador e clique em
**Desativar jogador** ou **Reativar jogador**, conforme o status atual.
Não é necessário digitar o nome nem confirmar em outro formulário.

Rotas e regras de autenticação: [API HTTP](api.md#endpoints).
