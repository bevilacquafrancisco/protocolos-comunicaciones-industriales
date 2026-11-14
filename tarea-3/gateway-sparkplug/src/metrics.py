"""
metrics.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Definicion declarativa de las metricas Sparkplug B del dispositivo 3, LEIDA del diccionario de
datos (docs/diccionario-de-datos.md). No hay ninguna metrica escrita a mano en el codigo: si el
diccionario cambia, cambia el Edge Node (invariante I-06). Bloque [DF-3.1] de
docs/diagramas/flujo-edge-node.mmd.

De cada tabla del diccionario se toman, por NOMBRE de columna (no por posicion):

    §1 (dispositivo 1)   NodeId OPC UA · Metrica Sparkplug B · Tipo Sparkplug · Alias ·
                         FC lectura / escritura (una FC de escritura => metrica escribible)
    §2 (estado, nodo)    Metrica Sparkplug · Tipo · NodeId OPC UA · Alias · Origen en el dispositivo 3

y se valida lo que la especificacion Sparkplug 3.0 exige de un conjunto de metricas:
nombres unicos, alias unicos en todo el Edge Node (payloads-alias-uniqueness), tipos validos,
'bdSeq' Int64 y 'Node Control/Rebirth' Boolean sin alias (data-commands-rebirth-name-aliases).

Dependencias externas: ninguna (solo biblioteca estandar).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Diccionario por defecto: tarea-3/docs/diccionario-de-datos.md (relativo a este archivo).
DICCIONARIO_POR_DEFECTO = Path(__file__).resolve().parents[2] / "docs" / "diccionario-de-datos.md"

#: Tipos Sparkplug que el Edge Node sabe codificar (nombres de DataType en sparkplug_b.proto).
TIPOS_SOPORTADOS = frozenset({"Boolean", "UInt16", "UInt32", "Int64", "Float", "String"})

NOMBRE_BDSEQ = "bdSeq"
NOMBRE_REBIRTH = "Node Control/Rebirth"


class ErrorDiccionario(ValueError):
    """El diccionario de datos no tiene la forma esperada o viola una regla de Sparkplug."""


@dataclass(frozen=True)
class Metrica:
    """
    Una metrica Sparkplug B.

    Atributos:
        nombre (str): nombre Sparkplug, p. ej. 'Inputs/Pulsador' (= BrowsePath OPC UA, I-06).
        tipo (str): tipo Sparkplug ('Boolean', 'UInt16', ...).
        alias (int | None): alias numerico; None si la especificacion lo prohibe o no aplica.
        ambito (str): 'nodo' (NBIRTH/NDATA) o 'dispositivo' (DBIRTH/DDATA).
        origen (str): 'opcua' (se suscribe al NodeId) o 'interno' (lo calcula el dispositivo 3).
        node_id (str | None): NodeId OPC UA completo ('ns=1;s=...') si origen == 'opcua'.
        escribible (bool): acepta DCMD (solo Outputs/* del dispositivo).
    """

    nombre: str
    tipo: str
    alias: int | None
    ambito: str
    origen: str
    node_id: str | None
    escribible: bool


@dataclass(frozen=True)
class ConjuntoMetricas:
    """
    Todas las metricas del Edge Node, con busqueda por nombre, alias y NodeId.

    Atributos:
        nodo (tuple[Metrica, ...]): metricas del Edge Node, en el orden del diccionario.
        dispositivo (tuple[Metrica, ...]): metricas del dispositivo 1.
    """

    nodo: tuple[Metrica, ...]
    dispositivo: tuple[Metrica, ...]

    def todas(self) -> tuple[Metrica, ...]:
        return self.nodo + self.dispositivo

    def por_nombre(self, nombre: str) -> Metrica | None:
        return next((m for m in self.todas() if m.nombre == nombre), None)

    def por_alias(self, alias: int) -> Metrica | None:
        return next((m for m in self.todas() if m.alias == alias), None)

    def por_node_id(self, node_id: str) -> Metrica | None:
        return next((m for m in self.todas() if m.node_id == node_id), None)

    def suscriptas(self) -> tuple[Metrica, ...]:
        """Metricas que el cliente OPC UA debe monitorear (origen 'opcua')."""
        return tuple(m for m in self.todas() if m.origen == "opcua")


# =============================================================================
# Lectura de las tablas Markdown
# =============================================================================

def _celda_codigo(celda: str) -> str | None:
    """Contenido del primer `codigo` de una celda, o None si la celda es un guion."""
    encontrado = re.search(r"`([^`]+)`", celda)
    if encontrado:
        return encontrado.group(1).strip()
    return None


def _partir_fila(linea: str) -> list[str]:
    """Divide una fila Markdown en celdas, respetando los '\\|' escapados dentro de una celda."""
    interior = linea.strip()[1:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", interior)]


def _tablas(texto: str) -> list[list[dict[str, str]]]:
    """Todas las tablas del Markdown como listas de filas {encabezado: celda}."""
    tablas, lineas = [], texto.splitlines()
    i = 0
    while i < len(lineas) - 1:
        if lineas[i].lstrip().startswith("|") and re.match(r"^\s*\|(\s*:?-+:?\s*\|)+\s*$", lineas[i + 1]):
            encabezado = _partir_fila(lineas[i])
            filas, i = [], i + 2
            while i < len(lineas) and lineas[i].lstrip().startswith("|"):
                celdas = _partir_fila(lineas[i])
                if len(celdas) == len(encabezado):
                    filas.append(dict(zip(encabezado, celdas)))
                i += 1
            tablas.append(filas)
        else:
            i += 1
    return tablas


def _buscar_tabla(tablas, columnas: tuple[str, ...]) -> list[dict[str, str]]:
    """La UNICA tabla cuyos encabezados contienen todas las columnas pedidas (prefijo)."""
    candidatas = [t for t in tablas if t and all(any(h.startswith(c) for h in t[0]) for c in columnas)]
    if len(candidatas) != 1:
        raise ErrorDiccionario(f"se esperaba una tabla con las columnas {columnas}, hay {len(candidatas)}")
    return candidatas[0]


def _columna(fila: dict[str, str], prefijo: str) -> str:
    return next(v for h, v in fila.items() if h.startswith(prefijo))


def _node_id(celda: str) -> str | None:
    """`s=Dispositivo1.Inputs.Pulsador` -> 'ns=1;s=Dispositivo1.Inputs.Pulsador' (el diccionario fija ns=1)."""
    codigo = _celda_codigo(celda)
    if codigo is None:
        return None
    if not codigo.startswith("s="):
        raise ErrorDiccionario(f"NodeId con formato inesperado: {codigo!r}")
    return f"ns=1;{codigo}"


def _alias(celda: str) -> int | None:
    texto = celda.strip()
    if texto in ("—", "-", ""):
        return None
    if not texto.isdigit():
        raise ErrorDiccionario(f"alias no numerico: {texto!r}")
    return int(texto)


# =============================================================================
# API
# =============================================================================

def cargar_metricas(ruta: Path | str = DICCIONARIO_POR_DEFECTO) -> ConjuntoMetricas:
    """
    Lee y valida las metricas del diccionario de datos.

    Parametros:
        ruta (Path | str): archivo Markdown del diccionario.
    Retorna:
        ConjuntoMetricas
    Excepciones:
        ErrorDiccionario: falta una tabla o columna, tipo desconocido, nombre o alias repetido,
            o una regla de Sparkplug 3.0 incumplida.
        OSError: el archivo no se puede leer.
    """
    tablas = _tablas(Path(ruta).read_text(encoding="utf-8"))

    dispositivo = []
    for fila in _buscar_tabla(tablas, ("NodeId OPC UA", "Métrica Sparkplug B", "Tipo Sparkplug", "Alias", "FC lectura")):
        escritura = _columna(fila, "FC lectura").split("/")[-1].strip()
        dispositivo.append(Metrica(
            nombre=_celda_codigo(_columna(fila, "Métrica Sparkplug B")), tipo=_celda_codigo(_columna(fila, "Tipo Sparkplug")),
            alias=_alias(_columna(fila, "Alias")), ambito="dispositivo", origen="opcua",
            node_id=_node_id(_columna(fila, "NodeId OPC UA")), escribible=escritura.startswith("FC")))

    nodo = []
    for fila in _buscar_tabla(tablas, ("Métrica Sparkplug", "Tipo", "NodeId OPC UA", "Alias", "Origen en el dispositivo 3")):
        origen = "opcua" if _columna(fila, "Origen").strip().upper() == "OPC UA" else "interno"
        node_id = _node_id(_columna(fila, "NodeId OPC UA"))
        nodo.append(Metrica(
            nombre=_celda_codigo(_columna(fila, "Métrica Sparkplug")), tipo=_celda_codigo(_columna(fila, "Tipo")),
            alias=_alias(_columna(fila, "Alias")), ambito="nodo", origen=origen,
            # Un NodeId con origen 'interno' (Status/OPCUA/Estado) NO se suscribe: se descarta aca.
            node_id=node_id if origen == "opcua" else None, escribible=False))

    conjunto = ConjuntoMetricas(nodo=tuple(nodo), dispositivo=tuple(dispositivo))
    _validar(conjunto)
    return conjunto


def _validar(c: ConjuntoMetricas) -> None:
    """Reglas de consistencia y de la especificacion Sparkplug 3.0."""
    todas = c.todas()
    for m in todas:
        if not m.nombre or not m.tipo:
            raise ErrorDiccionario(f"metrica sin nombre o sin tipo: {m}")
        if m.tipo not in TIPOS_SOPORTADOS:
            raise ErrorDiccionario(f"{m.nombre}: tipo {m.tipo!r} no soportado ({sorted(TIPOS_SOPORTADOS)})")
        if m.origen == "opcua" and not m.node_id:
            raise ErrorDiccionario(f"{m.nombre}: origen OPC UA sin NodeId")
    nombres = [m.nombre for m in todas]
    repetidos = {n for n in nombres if nombres.count(n) > 1}
    if repetidos:
        raise ErrorDiccionario(f"nombres repetidos: {sorted(repetidos)}")
    alias = [m.alias for m in todas if m.alias is not None]
    if len(alias) != len(set(alias)):
        raise ErrorDiccionario(f"alias repetidos: {sorted(a for a in alias if alias.count(a) > 1)}")
    bdseq, rebirth = c.por_nombre(NOMBRE_BDSEQ), c.por_nombre(NOMBRE_REBIRTH)
    if bdseq is None or bdseq.tipo != "Int64" or bdseq.ambito != "nodo":
        raise ErrorDiccionario("falta 'bdSeq' Int64 del nodo (Sparkplug 3.0, tck-id-topics-nbirth-bdseq-included)")
    if rebirth is None or rebirth.tipo != "Boolean" or rebirth.alias is not None:
        raise ErrorDiccionario("'Node Control/Rebirth' debe ser Boolean y SIN alias "
                               "(tck-id-operational-behavior-data-commands-rebirth-name-aliases)")
    if not c.dispositivo:
        raise ErrorDiccionario("el dispositivo no tiene metricas")
    sin_alias = [m.nombre for m in todas if m.alias is None and m.nombre not in (NOMBRE_BDSEQ, NOMBRE_REBIRTH)]
    if sin_alias:
        # Sin alias, un DATA tendria que llevar el nombre, y la especificacion pide que lleven SOLO
        # el alias cuando se usan alias (tck-id-payloads-alias-data-cmd-requirement).
        raise ErrorDiccionario(f"metricas que pueden viajar en un DATA sin alias: {sin_alias}")
