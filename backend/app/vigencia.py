"""Situação de vigência na data da consulta, não na data em que o corpus foi editado.

O corpus registra `status` e `entra_em_vigor_em` por dispositivo. O status
gravado envelhece: uma norma `em_vacatio` passa a valer na data marcada,
mesmo que ninguém edite o JSON. Responder "ainda não está em vigor" depois
dessa data é tão errado quanto citar a regra antes da hora — por isso a
situação apresentada ao cidadão é recalculada a cada consulta.

O que muda é só o caso que a própria norma resolve (a data de início que ela
fixa). Revogação, inconstitucionalidade e qualquer outra mudança continuam
dependendo de revisão humana: data passada não revoga nada.

"Hoje" é a data em Brasília. Na hospedagem o relógio é UTC, e entre 21h e
meia-noite o dia UTC já é o seguinte.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FUSO_BRASILIA: tzinfo
try:
    FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # sistema sem base de fusos e sem o pacote tzdata
    # Sem horário de verão desde 2019, o fuso de Brasília é UTC-3 fixo.
    FUSO_BRASILIA = timezone(timedelta(hours=-3))

# Data de referência fixa, para testes e avaliações reproduzíveis ("como a
# base responderia em tal dia"). Sem a variável, vale o dia de hoje.
VARIAVEL_DATA_REFERENCIA = "DIREITO_ABERTO_DATA_REFERENCIA"

# Sem registro, a situação é desconhecida — nunca "vigente" por omissão. Ausência de evidência de
# revogação não é evidência de vigência.
VIGENCIA_PADRAO: dict[str, Any] = {
    "status": "nao_verificada",
    "entra_em_vigor_em": None,
    "alterada_por": [],
    "nota": None,
    "conferida_em": None,
}
STATUS = {
    "vigente": "em vigor na data da consulta",
    "em_vacatio": "publicada, ainda sem efeito",
    "revogada": "revogada",
    "redacao_anterior": "redação anterior, substituída por outra",
    "inconstitucional": "declarada inconstitucional pelo STF",
    "nao_verificada": "situação de vigência não verificada",
}
NOTA_NAO_VERIFICADA = ("A base não tem conferência registrada da vigência deste dispositivo: não o trate como "
                       "certamente em vigor sem consultar a fonte oficial.")


def hoje(instante: datetime | None = None) -> date:
    """Data em Brasília do `instante` (padrão: agora), ou a data de referência configurada."""
    fixa = os.environ.get(VARIAVEL_DATA_REFERENCIA)
    if fixa and instante is None:
        return date.fromisoformat(fixa)
    return (instante or datetime.now(timezone.utc)).astimezone(FUSO_BRASILIA).date()


def data_br(iso: str | None) -> str:
    if not iso:
        return ""
    ano, mes, dia = iso.split("-")
    return f"{dia}/{mes}/{ano}"


def vigencia_efetiva(registrada: dict | None, em: date | None = None) -> dict:
    """Bloco de vigência como vale na data `em` (padrão: hoje em Brasília).

    Quando a data de início de uma norma `em_vacatio` já chegou, o status
    passa a `vigente`, e o bloco guarda o que estava gravado em
    `status_registrado` — sinal para a fila de revisão de que o corpus
    precisa ser atualizado.
    """
    vigencia = {**VIGENCIA_PADRAO, **(registrada or {})}
    if vigencia["status"] not in STATUS or (vigencia["status"] == "vigente" and not vigencia.get("conferida_em")):
        # "vigente" sem data de conferência é afirmação sem evidência; status desconhecido também.
        return {**vigencia, "status": "nao_verificada", "status_registrado": vigencia["status"],
                "nota": vigencia.get("nota") or NOTA_NAO_VERIFICADA}
    if vigencia["status"] == "nao_verificada":
        return {**vigencia, "nota": vigencia.get("nota") or NOTA_NAO_VERIFICADA}
    fim = vigencia.get("vigente_ate")
    if vigencia["status"] == "vigente" and fim and date.fromisoformat(fim) < (em or hoje()):
        # Redação com data final fixada pela própria norma (ex.: a jornada de 44 horas até a etapa da
        # EC 141/2026): passada a data, ela é redação anterior — mesmo antes de alguém editar o corpus.
        return {**vigencia, "status": "redacao_anterior", "status_registrado": "vigente"}
    inicio = vigencia.get("entra_em_vigor_em")
    if vigencia["status"] != "em_vacatio" or not inicio:
        return vigencia
    if date.fromisoformat(inicio) > (em or hoje()):
        return vigencia
    return {
        **vigencia,
        "status": "vigente",
        "status_registrado": "em_vacatio",
        "vigente_desde": inicio,
    }
