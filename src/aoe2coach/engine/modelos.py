"""Contrato de entrada y salida del motor.

La pieza central es `Evidencia`: ningún número sale del motor sin ella. Si algo no tiene n,
intervalo y fuente, no es un dato — es una opinión, y va en otro campo.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confianza = Literal["alta", "media", "baja", "sin_datos"]


class Contexto(BaseModel):
    civ: str | None = None
    mapa: str
    elo: int
    civ_rival: str | None = None
    modo: Literal["rm_1v1"] = "rm_1v1"


class Evidencia(BaseModel):
    """Un número con todo lo necesario para auditarlo."""

    valor: float | None = None
    n: int | None = None
    ci: tuple[float, float] | None = None
    fuente: str
    fecha_dato: str | None = None
    confianza: Confianza = "sin_datos"
    nota: str | None = None
    """Aclaración obligatoria cuando el dato no es exactamente el pedido (p. ej. se cayó al
    agregado de todos los mapas porque el mapa puntual no tenía muestra)."""

    @property
    def pct(self) -> str:
        if self.valor is None:
            return "sin datos"
        margen = f" ±{(self.ci[1] - self.ci[0]) / 2 * 100:.1f}" if self.ci else ""
        return f"{self.valor * 100:.1f}%{margen}"

    def texto(self) -> str:
        partes = [self.pct]
        if self.n:
            partes.append("n=" + f"{self.n:,}".replace(",", "."))
        partes.append(self.fuente)
        if self.nota:
            partes.append(self.nota)
        return " · ".join(partes)


class Componente(BaseModel):
    """Un sumando del score, con su explicación. El puntaje no es una caja negra."""

    nombre: str
    puntos: float
    detalle: str
    evidencia: Evidencia | None = None


class EstrategiaPuntuada(BaseModel):
    id: str
    nombre: str
    descripcion: str
    score: float
    componentes: list[Componente]
    apertura_pulse: str
    dificultad: int
    advertencias: list[str] = Field(default_factory=list)


class PasoBuild(BaseModel):
    paso: int
    villager_count: int | None = None
    age: int | None = None
    food: int | None = None
    wood: int | None = None
    gold: int | None = None
    stone: int | None = None
    tiempo: str | None = None
    notas: str = ""
    ajuste_civ: str | None = None
    """Anotación por bonificación de la civ, con la cita del bono que la justifica."""


class BuildOrder(BaseModel):
    build_id: str
    nombre: str
    civ: str
    autor: str
    fuente: str
    pasos: list[PasoBuild]
    uptime_esperado: Evidencia | None = None
    nota_seleccion: str


class Calculo(BaseModel):
    """Una cuenta con su fórmula a la vista."""

    titulo: str
    resultado: str
    formula: str
    fuente: str
    supuestos: list[str] = Field(default_factory=list)


class Senal(BaseModel):
    si_ves: str
    transicionar_a: str
    motivo: str
    respaldo: str | None = None


class Reporte(BaseModel):
    contexto: Contexto
    elo_bucket: str
    advertencias: list[str]
    perfil_mapa: dict
    analisis_matchup: dict[str, Evidencia]
    civ_bonos: list[str]
    estrategia: EstrategiaPuntuada | None
    alternativas: list[EstrategiaPuntuada]
    civs_sugeridas: list["CivSugerida"] = Field(default_factory=list)
    build: BuildOrder | None
    calculos: list[Calculo]
    plan_b: list[Senal]


class CivSugerida(BaseModel):
    """Una civ candidata cuando no fijás la tuya, con el porqué a la vista."""

    civ: str
    score: float
    componentes: list[Componente]
    bonos: list[str] = Field(default_factory=list)


# `Reporte` referencia `CivSugerida`, que se define más abajo: hay que rearmarlo.
Reporte.model_rebuild()
