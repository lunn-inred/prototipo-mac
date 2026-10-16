# Jogadores

[← Voltar ao README](../README.md)

## Cadastro e mural

A página inicial lista o elenco e resume CMJ, distância GPS e a EVA Dor mais
recente. O gerenciador permite cadastrar, editar, desativar e reativar atletas. Somente o
nome é obrigatório; `nome_alternativo` não é exposto no CRUD e permanece
inalterado nas edições. A desativação muda `public.atleta.status` de `ativo` para `inativo`, sem apagar
o cadastro ou suas medições. Novos cadastros recebem `ativo` por padrão.
O status é exibido no mural; jogadores inativos continuam disponíveis para
consulta ao histórico. Não há mais endpoint de exclusão de jogadores.

Na aba **Desativar/reativar jogador**, selecione o jogador e clique em
**Desativar jogador** ou **Reativar jogador**, conforme o status atual.
Não é necessário digitar o nome nem confirmar em outro formulário.

Rotas e regras de autenticação: [API HTTP](api.md#endpoints).
