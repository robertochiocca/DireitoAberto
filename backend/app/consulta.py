"""Da pergunta aos dispositivos: busca, abstenção e análise temporal — o mesmo caminho na API e na avaliação.

A API (`main._responder`) e a avaliação (`avaliacao_temporal`) chamam `consultar`; medir outra coisa
que não o caminho real seria medir um sistema que ninguém usa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .retrieval import Retriever, normalizar
from .temporal import Analise, ConsultaTemporal, consulta_sem_tempo, interpretar, linhas_da_resposta, ordenar
from .validacao import evidencia_insuficiente


@dataclass
class Consulta:
    temporal: ConsultaTemporal
    encontrados: list            # o que a busca devolveu (mesmo quando a API se abstém)
    artigos: list                # o que a resposta usa, na ordem da análise temporal
    abstencao: bool
    calibrado: bool
    avisos: list[str] = field(default_factory=list)
    analise: Analise | None = None
    termos_casados: list[str] | None = None   # palavras da pergunta presentes no 1º dispositivo
    termos_da_pergunta: int = 0


def consultar(retriever, pergunta: str, hoje: date, tema: str | None = None,
              contexto_documento: str | None = None) -> Consulta:
    temporal = interpretar(pergunta, hoje)
    pergunta_busca = consulta_sem_tempo(pergunta, temporal)
    # Adaptativa: devolve menos artigos quando os demais são fracos, em vez de completar as vagas com lei
    # de outro assunto.
    so_pergunta = retriever.buscar(pergunta_busca, tema=tema, adaptativo=True)
    calibrado = isinstance(retriever, Retriever)
    termos = list(dict.fromkeys(normalizar(pergunta_busca)))
    if contexto_documento and calibrado:
        # O documento só expande a busca (peso baixo). A abstenção segue a pergunta quando ela tem assunto
        # próprio; pergunta vaga ("o que diz este documento?") deixa o documento decidir.
        encontrados = retriever.buscar(pergunta_busca, tema=tema, adaptativo=True, expansao=contexto_documento)
        vaga = len(termos) < 2
        abstencao = evidencia_insuficiente(encontrados if vaga else so_pergunta, calibrado)
    elif contexto_documento:
        encontrados = retriever.buscar(f"{pergunta_busca} {contexto_documento}", tema=tema, adaptativo=True)
        abstencao = evidencia_insuficiente(encontrados, calibrado)
    else:
        encontrados = so_pergunta
        # Abaixo do limiar calibrado, a base não tem o assunto: melhor dizer isso do que responder com lei
        # de outro assunto. O limiar vale para o BM25; o motor semântico tem outra escala de nota.
        abstencao = evidencia_insuficiente(encontrados, calibrado)
    artigos = [] if abstencao else encontrados
    analise = ordenar(artigos, temporal, hoje)
    avisos = linhas_da_resposta(analise, hoje) if analise.resultados else list(analise.avisos)
    casados = (retriever.termos_casados(pergunta_busca, analise.resultados[0].id)
               if calibrado and analise.resultados else None)
    return Consulta(temporal, encontrados, analise.resultados, abstencao, calibrado, avisos, analise,
                    casados, len(termos))
