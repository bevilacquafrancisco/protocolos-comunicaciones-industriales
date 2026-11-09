#!/usr/bin/env python3
"""
construir_pdf.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Genera el PDF de un informe de la Tarea 3 a partir de su fuente Markdown y verifica
que cumpla el formato que exige la consigna (CLAUDE.md §8):
Arial 11, interlineado 1,5, margenes laterales 3 cm y superior/inferior 2,5 cm,
texto justificado, A4.

Cadena: Markdown --pandoc + citeproc (APA 7)--> HTML autocontenido
        --Chrome/Edge sin interfaz--> PDF --pdfplumber--> verificacion.

Se usa Chrome como motor de PDF porque no requiere instalar LaTeX y respeta @page
del CSS (margenes exactos y numero de pagina).

Dependencias externas
---------------------
- pandoc >= 3.1 en el PATH, o la variable de entorno PANDOC con su ruta
  (alternativa sin instalador: pip install pypandoc_binary, que lo trae).
- Google Chrome o Microsoft Edge; se busca en las ubicaciones estandar o en la
  variable de entorno CHROME.
- pdfplumber (pip install pdfplumber) para la verificacion.

Uso
---
    python informe/construir_pdf.py informe/preliminar.md
    python informe/construir_pdf.py informe/preliminar.md --salida informe/build/X.pdf

Retorna codigo de salida 1 si la construccion o alguna verificacion de formato falla.
"""

import argparse
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

#: Margenes exigidos, en centimetros (consigna: laterales 3, superior e inferior 2,5).
MARGEN_LATERAL_CM = 3.0
MARGEN_VERTICAL_CM = 2.5
#: Tamano de letra exigido, en puntos.
TAMANO_PT = 11.0
#: Tolerancia de las verificaciones geometricas, en centimetros. 0,15 cm cubre el
#: redondeo de Chrome y la sangria de la ultima linea de un parrafo justificado.
TOLERANCIA_CM = 0.15
PT_POR_CM = 72 / 2.54

DIRECTORIO = Path(__file__).resolve().parent


# =============================================================================
# Localizacion de herramientas
# =============================================================================

def buscar_pandoc():
    """
    Ubica el ejecutable de pandoc.

    Retorna:
        str: ruta del ejecutable.
    Excepciones:
        SystemExit: si no se encuentra.
    """
    candidatos = [os.environ.get("PANDOC"), shutil.which("pandoc")]
    try:
        import pypandoc  # opcional: pypandoc_binary trae pandoc empaquetado
        candidatos.append(pypandoc.get_pandoc_path())
    except Exception:
        pass
    for ruta in filter(None, candidatos):
        # En Windows, pypandoc informa la ruta sin la extension .exe.
        for variante in (Path(ruta), Path(str(ruta) + ".exe")):
            if variante.is_file():
                return str(variante)
    raise SystemExit("No se encontro pandoc: instalarlo, definir PANDOC o "
                     "'pip install pypandoc_binary'.")


def buscar_chrome():
    """
    Ubica Chrome o Edge (cualquier navegador Chromium sirve).

    Retorna:
        str: ruta del ejecutable.
    Excepciones:
        SystemExit: si no se encuentra.
    """
    programas = [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""),
                 os.environ.get("LOCALAPPDATA", "")]
    candidatos = [os.environ.get("CHROME")]
    for base in filter(None, programas):
        candidatos += [Path(base) / "Google/Chrome/Application/chrome.exe",
                       Path(base) / "Microsoft/Edge/Application/msedge.exe"]
    candidatos += [shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser",
                                             "microsoft-edge")]
    for ruta in candidatos:
        if ruta and Path(ruta).exists():
            return str(ruta)
    raise SystemExit("No se encontro Chrome ni Edge: definir la variable CHROME.")


# =============================================================================
# Construccion
# =============================================================================

def markdown_a_html(fuente, html):
    """
    Convierte la fuente Markdown a un HTML autocontenido con las citas resueltas.

    Parametros:
        fuente (Path): archivo .md con su bloque YAML (bibliography, csl).
        html (Path): archivo HTML a generar.
    Excepciones:
        subprocess.CalledProcessError: si pandoc falla.
    """
    subprocess.run(
        [buscar_pandoc(), fuente.name, "--from", "markdown", "--to", "html5",
         "--standalone", "--embed-resources", "--citeproc",
         "--css", str(DIRECTORIO / "estilo-informe.css"),
         "--resource-path", ".", "--output", str(html)],
        cwd=fuente.parent, check=True)


def html_a_pdf(html, pdf):
    """
    Imprime el HTML a PDF con el navegador sin interfaz, sin encabezados del navegador.

    Parametros:
        html (Path), pdf (Path).
    Excepciones:
        SystemExit: si el PDF no se genero.
    """
    pdf.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as perfil:   # perfil limpio: no toca el del usuario
        subprocess.run(
            [buscar_chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={perfil}", f"--print-to-pdf={pdf}", html.resolve().as_uri()],
            check=True, capture_output=True, timeout=180)
    if not pdf.is_file() or pdf.stat().st_size == 0:
        raise SystemExit(f"Chrome no genero {pdf}")


# =============================================================================
# Verificacion del formato
# =============================================================================

def verificar(pdf):
    """
    Comprueba fuente, tamano, margenes, interlineado y justificado sobre el PDF real.

    Se mide el TEXTO DE CUERPO: caracteres de 11 pt en Arial, que son los que la
    consigna regula. Titulos, tablas con codigo y pies de figura se excluyen de la
    medicion de interlineado, pero si cuentan para los margenes.

    Parametros:
        pdf (Path).
    Retorna:
        list[tuple[bool, str]]: (aprobado, descripcion) por verificacion.
    """
    import pdfplumber

    resultados = []
    with pdfplumber.open(pdf) as doc:
        paginas = doc.pages
        ancho_cm = paginas[0].width / PT_POR_CM
        alto_cm = paginas[0].height / PT_POR_CM
        resultados.append((abs(ancho_cm - 21.0) < 0.1 and abs(alto_cm - 29.7) < 0.1,
                           f"Pagina A4: {ancho_cm:.2f} x {alto_cm:.2f} cm"))

        fuentes, tamanos = Counter(), Counter()
        izq, der, sup, inf = [], [], [], []
        saltos, bordes_derechos = [], []
        for pagina in paginas[1:]:                 # la caratula tiene su propio diseno
            palabras = pagina.extract_words(extra_attrs=["fontname", "size"])
            for w in palabras:
                fuentes[w["fontname"].split("+")[-1]] += len(w["text"])
                tamanos[round(w["size"], 1)] += len(w["text"])
            numeros_pagina = [w for w in palabras if w["top"] > pagina.height - 2.5 * PT_POR_CM]
            contenido = [w for w in palabras if w not in numeros_pagina]
            if contenido:
                izq.append(min(w["x0"] for w in contenido) / PT_POR_CM)
                der.append((pagina.width - max(w["x1"] for w in contenido)) / PT_POR_CM)
                sup.append(min(w["top"] for w in contenido) / PT_POR_CM)
                inf.append((pagina.height - max(w["bottom"] for w in contenido)) / PT_POR_CM)
            # Lineas de cuerpo: palabras de 11 pt agrupadas por ordenada.
            # Se agrupan por cercania (1 pt) y no por redondeo: redondear la ordenada a
            # enteros distorsiona la medicion de una separacion de 16,5 pt.
            lineas = {}
            cuerpo = sorted((w for w in contenido
                             if abs(w["size"] - TAMANO_PT) < 0.3 and "Arial" in w["fontname"]),
                            key=lambda w: w["top"])
            for w in cuerpo:
                clave = next((t for t in lineas if abs(t - w["top"]) < 1.0), w["top"])
                lineas.setdefault(clave, []).append(w)
            tops = sorted(lineas)
            for a, b in zip(tops, tops[1:]):
                if 10 < b - a < 25:                # consecutivas dentro de un parrafo
                    saltos.append(b - a)
            for top in tops:
                bordes_derechos.append(max(w["x1"] for w in lineas[top]))

    principal = fuentes.most_common(1)[0][0]
    resultados.append(("Arial" in principal, f"Fuente principal: {principal} "
                       f"({fuentes[principal] * 100 // sum(fuentes.values())} % de los caracteres)"))
    tam_principal = tamanos.most_common(1)[0][0]
    resultados.append((abs(tam_principal - TAMANO_PT) < 0.3,
                       f"Tamano principal: {tam_principal} pt"))
    resultados.append((min(izq) >= MARGEN_LATERAL_CM - TOLERANCIA_CM,
                       f"Margen izquierdo minimo: {min(izq):.2f} cm (exigido {MARGEN_LATERAL_CM})"))
    resultados.append((min(der) >= MARGEN_LATERAL_CM - TOLERANCIA_CM,
                       f"Margen derecho minimo: {min(der):.2f} cm (exigido {MARGEN_LATERAL_CM})"))
    resultados.append((min(sup) >= MARGEN_VERTICAL_CM - TOLERANCIA_CM,
                       f"Margen superior minimo: {min(sup):.2f} cm (exigido {MARGEN_VERTICAL_CM})"))
    resultados.append((min(inf) >= MARGEN_VERTICAL_CM - TOLERANCIA_CM,
                       f"Margen inferior minimo: {min(inf):.2f} cm (exigido {MARGEN_VERTICAL_CM})"))
    if saltos:
        moda = statistics.mode(round(s * 2) / 2 for s in saltos)   # a medio punto
        resultados.append((abs(moda / TAMANO_PT - 1.5) < 0.08,
                           f"Interlineado del cuerpo: {moda:.1f} pt = {moda / TAMANO_PT:.2f} x 11 pt"))
    if bordes_derechos:
        # Borde derecho de la caja de texto: ancho A4 menos el margen lateral.
        borde_cm = 21.0 - MARGEN_LATERAL_CM
        al_borde = sum(1 for x in bordes_derechos if abs(x / PT_POR_CM - borde_cm) < 0.1)
        fraccion = al_borde / len(bordes_derechos)
        # Las ultimas lineas de cada parrafo y las de tablas no llegan al borde: por eso
        # se exige mayoria y no totalidad.
        resultados.append((fraccion > 0.5,
                           f"Justificado: {fraccion:.0%} de las lineas de cuerpo terminan en el "
                           f"margen derecho ({borde_cm} cm desde el borde izquierdo)"))
    return resultados


# =============================================================================
# Programa principal
# =============================================================================

def main():
    """Construye y verifica. Retorna 0 si todo pasa, 1 si algo falla."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("fuente", type=Path, help="archivo Markdown del informe")
    parser.add_argument("--salida", type=Path, help="PDF de salida (por defecto informe/build/)")
    args = parser.parse_args()

    fuente = args.fuente.resolve()
    pdf = (args.salida or DIRECTORIO / "build" / (fuente.stem + ".pdf")).resolve()
    html = pdf.with_suffix(".html")

    markdown_a_html(fuente, html)
    html_a_pdf(html, pdf)
    print(f"PDF generado: {pdf}")

    fallos = 0
    for aprobado, texto in verificar(pdf):
        print(("  OK     " if aprobado else "  FALLA  ") + texto)
        fallos += not aprobado
    print("TODO OK" if fallos == 0 else f"{fallos} verificacion(es) fallida(s)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
