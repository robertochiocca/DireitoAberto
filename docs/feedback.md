# Feedback controlado

> Rodada 9.0, ciclo P4. Código: `backend/app/feedback.py` (API), `backend/scripts/feedback.py`
> (triagem), `web/components/FeedbackDispositivo.tsx` (interface). O frontend estático não tem o
> formulário.

## O fluxo

1. Em cada dispositivo citado numa resposta, "Informar um problema neste dispositivo" abre um formulário
   curto: o tipo de problema (texto não confere, norma revogada ou alterada, dispositivo não se aplica,
   explicação confusa, outro) e, se a pessoa quiser, um comentário de até 600 caracteres.
2. `POST /api/v1/feedback` grava o feedback como `novo`. A resposta diz que uma pessoa vai conferir e que
   o retorno não muda a resposta na hora.
3. Quem mantém a base faz a triagem:

```bash
cd backend
python scripts/feedback.py resumo                  # fila por dispositivo e tipo (só prioriza)
python scripts/feedback.py listar --estado novo
python scripts/feedback.py triar --id 12 --resultado procedente --responsavel "Nome" \
    --nota "o que foi conferido" --abrir-revisao
# resultados: procedente · improcedente · duplicado
```

4. Com `--abrir-revisao` (só se procedente), a entrada do corpus fica **em revisão**: a resposta passa a
   avisar que o dispositivo está sendo conferido. Isso é registrado no histórico do corpus
   (`corpus.py abrir-revisao`), com responsável, motivo e a evidência `feedback:<id>`. **O texto da lei
   não muda.** Corrigir o texto continua sendo edição por pessoa mais `corpus.py registrar`.

## O que o feedback nunca faz

- Não muda o corpus, a vigência, os limiares de confiança, a calibração da busca nem a política de
  resposta. Nenhum módulo de busca, validação ou geração lê a tabela de feedback; há teste que manda dez
  relatos de "norma revogada" sobre o mesmo dispositivo e confere que a resposta e o arquivo do corpus
  continuam idênticos.
- Muitos relatos iguais não viram correção automática: viram prioridade na fila de triagem.
- Não é usado para treinar modelo nem enviado a terceiros.

## Dados pessoais

- Guarda-se o mínimo: dispositivo, tipo, comentário e, se houver conta, a conta. A pergunta não é
  copiada.
- CPF, e-mail, telefone e número de processo escritos no comentário são **mascarados antes de gravar**
  (o formulário também pede para não escrevê-los). A máscara é por padrão de texto: nome de pessoa e
  outros dados livres não são detectados.
- Com conta, o feedback sai em "Baixar meus dados" e é apagado com a conta. Sem conta, não fica ligado a
  ninguém; o limite de 5 envios a cada 10 minutos por endereço é contado em memória e não grava o
  endereço. A trilha de auditoria registra `feedback_enviado` com pseudônimo e prefixo de rede, sem
  conteúdo.
- Retenção: apagado depois de `DIREITO_ABERTO_RETENCAO_FEEDBACK_DIAS` (padrão 365). O que a triagem
  decidiu sobre o corpus fica no histórico do corpus, sem o comentário.

## Limitações

- A triagem é só por linha de comando; não há painel de revisão.
- A máscara de dados pessoais não pega nomes, endereços ou descrições do caso.
- Não há retorno para quem enviou (a pessoa não é avisada do resultado da triagem).
