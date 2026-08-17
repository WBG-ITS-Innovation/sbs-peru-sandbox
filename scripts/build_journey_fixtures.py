#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Generate the demo-journey complaint fixture — fully synthetic.

Output:  app/src/lib/journey-emails.json — 80 rows, mixed
         LARGE_ENTITIES / SMALL_ENTITIES, in a shape the Next.js
         pages render directly.

This script *generates*. It reads no workbook and needs no external
data: a fresh clone reproduces the committed fixture byte-for-byte with
``python scripts/build_journey_fixtures.py``. That is deliberate.

An earlier version of this script extracted rows from a sample workbook
shared under a private arrangement and committed the extract. The PII
substitution it ran was real and it worked — but it swapped *entities*,
not prose. The 80 narrative bodies were real consumer-complaint free
text, carrying the dates, amounts, card terminals and circumstances of
real disputes, and the substitution then wrote four named real banks
into that text. Nothing derived from that workbook survives here. Every
narrative below is generated from the taxonomy; every name, date,
amount, document number and terminal is drawn from the seed.

Determinism follows the house convention of
``scripts/generate-synthetic-corpus.py`` (ADR 0036): a ``--seed`` and a
fixed date anchor, so the same inputs give byte-identical output on any
machine.

Three properties of the old fixture are kept on purpose, because
downstream code exists to handle them and would otherwise go untested:

* **Surface-form variance.** The two sheets spell the same logical
  value differently — ``Página web de la empresa`` against
  ``PAG. WEB DE LA EMPRESA`` — which is the whole reason
  ``sbs_api.taxonomy.dictionary_v1`` exists. Forms are drawn from that
  dictionary's own key set, plus a few terms deliberately absent from
  it so the ``taxonomy-unknown-term`` warning path still fires.
* **Dirty ubigeo, and document numbers that do not match their declared
  type.** Blank, zero-padded, three- and four-digit ubigeos, one stored
  as a number rather than a string; and a small-entity sheet whose
  twelve-digit client numbers are declared as eight-digit DNIs.
  ``DQ-A1A-009`` and ``DQ-A1A-011`` exist to catch exactly these, and a
  clean fixture gives them nothing to find. The old fixture had these
  faults by accident; here they are deliberate and bounded.
* **Raw-looking PII.** The FI side of the demo must *show* unredacted
  document numbers and names so the SBS receive step has something to
  redact. These are generated and fictional.
"""

from __future__ import annotations

import argparse
import json
import random
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "app" / "src" / "lib" / "journey-emails.json"

DEFAULT_SEED = 2026
ROWS_PER_SHEET = 40

# The reporting year the fixture describes. Fixed, not derived from the
# wall clock — a moving window would churn the fixture in every diff.
YEAR = 2025

COLS = [
    "COD_REC", "TID_CLI", "NRO_CLI", "NCL_CLI", "COD_CLI", "FEC_ING",
    "CNL_ING", "CNL_OPE", "FEC_AMP", "CNL_AMP", "FEC_RES", "CNL_PAC",
    "UBI_REC", "PRD_SBS", "MOT_SBS", "SUB_SBS", "DET_REC", "TIP_RES",
    "DET_RES", "PRD_EMP", "EST_REC", "COD_PRV", "BAN_SEG", "PRD_SBS_SEG",
    "MOT_SBS_SEG", "SUB_SBS_SEG", "MNT_PEN_REC", "EMPRESA",
]


# ---------------------------------------------------------------------------
# Fictional people, places and institutions
# ---------------------------------------------------------------------------
#
# Names are assembled from given-name and surname pools, so a name in the
# fixture is a combination rather than a person. Institutions are the
# fictional entities of scripts/dev-seed.sql and
# scripts/build_rr1_fixture.py — the sandbox names one consistent
# fiction. Zero real financial institutions appear anywhere in this
# file; tests/cleanup/test_no_real_entities.py enforces that.

# Two pools, so a two-given-name combination stays internally coherent
# instead of pairing names that never appear together.
GIVEN_NAMES: tuple[tuple[str, ...], ...] = (
    (
        "ANA", "BEATRIZ", "CARMEN", "CECILIA", "DANIELA", "ELENA", "FLOR",
        "GLORIA", "ISABEL", "JULIA", "LUCÍA", "MARIANA", "NORMA", "PATRICIA",
        "RENATA", "ROSA", "SILVIA", "SOFÍA", "TERESA", "VALERIA",
    ),
    (
        "ANDRÉS", "CARLOS", "DIEGO", "ERNESTO", "FELIPE", "GUSTAVO", "HÉCTOR",
        "IVÁN", "JAVIER", "JORGE", "LUIS", "MANUEL", "MIGUEL", "OSCAR",
        "PEDRO", "RAÚL", "ROBERTO", "SERGIO", "TOMÁS", "VÍCTOR",
    ),
)

SURNAMES: tuple[str, ...] = (
    "ALIAGA", "BRAVO", "CABRERA", "CÁRDENAS", "CASTILLO", "CHÁVEZ",
    "CORDERO", "ESPINOZA", "FLORES", "GUTIÉRREZ", "HUAMÁN", "HUAMANÍ",
    "LEÓN", "LOAYZA", "MENDOZA", "NÚÑEZ", "ORTIZ", "PACHECO", "PAZ",
    "PÉREZ", "PINO", "QUISPE", "REYES", "RÍOS", "RODRÍGUEZ", "ROMERO",
    "SALAZAR", "SÁNCHEZ", "SILVA", "TELLO", "TORRES", "VARGAS",
    "VÁSQUEZ", "VEGA", "VELÁSQUEZ", "YUPANQUI", "ZAMBRANO",
)

# Districts and cities. Places are places — naming Miraflores attributes
# nothing to anyone.
LOCATIONS: tuple[str, ...] = (
    "Lima Centro", "Miraflores", "San Isidro", "Surco", "Arequipa",
    "Trujillo", "Cusco", "Piura", "Chiclayo", "Iquitos", "Huancayo",
    "Tacna",
)

# Invented street addresses.
ADDRESSES: tuple[str, ...] = (
    "Av. Los Álamos 1240", "Jr. Las Gaviotas 318", "Av. El Mirador 2075",
    "Calle Los Cedros 415", "Av. Las Palmeras 860", "Jr. San Marcos 522",
    "Av. Los Robles 1130",
)

# Fictional institutions, consistent with dev-seed.sql and the RR1
# fixture. The narratives name these or nothing.
ENTITIES: tuple[str, ...] = (
    "Banco Nuevo Horizonte del Perú",
    "Cooperativa de Ahorro Coopac Andes Centro",
    "Financiera Surandina del Perú",
    "BANCO_DEMO_001",
)

# Internal areas a complaint gets routed through. Generic function
# names, not brands.
DEPARTMENTS: tuple[str, ...] = (
    "Atención al Cliente", "Defensoría del Cliente",
    "Servicio al Usuario", "Área de Reclamos",
)

# Institution-internal product names — invented, in the ALL-CAPS style
# core-banking systems export.
PRODUCTOS_INTERNOS: tuple[str, ...] = (
    "CUENTA AHORRO", "AHORRO FLEXIBLE", "AHORRO RENTABLE", "PLAN DE AHORRO",
    "CUENTA DIGITAL", "CTA.CTE.P.JURIDICA (PEN)", "LINEA DE CREDITO",
    "CAPITAL DE TRABAJO", "CREDITO LIBRE DISPONIBILIDAD",
    "MASIVO CENTRALIZADO DESCUENTO", "TARJETA CLASICA", "DEPOSITO PLAZO FIJO",
)


# ---------------------------------------------------------------------------
# Surface forms
# ---------------------------------------------------------------------------
#
# Keyed by sheet. LARGE_ENTITIES exports mixed case with accents;
# SMALL_ENTITIES exports ALL-CAPS and drops accents. Both spellings of
# each value are in sbs_api.taxonomy.dictionary_v1, except the handful
# marked below, which are there to exercise the unknown-term path.

CANALES: dict[str, tuple[str, ...]] = {
    "LARGE_ENTITIES": (
        "Vía telefónica", "Página web de la empresa", "Oficina",
        "Aplicativo Móvil", "Correo Electrónico", "Cajero Automático",
        "Billeteras digitales",
        "Plataforma online de terceros",  # not in the dictionary — by design
    ),
    "SMALL_ENTITIES": (
        "VIA TELEFONICA", "PAG. WEB DE LA EMPRESA", "OFICINA",
        "APLICATIVO MÓVIL", "CORREO ELECTRONICO", "CAJERO AUTOMÁTICO",
        "BILLETERAS DIGITALES",
        "PLATAFORMA ONLINE DE TERCEROS",  # not in the dictionary — by design
    ),
}

# "No existe canal asociado" is the canal_operacion value for a complaint
# about no operation in particular. Two spellings, one of them unknown to
# the dictionary.
SIN_CANAL: dict[str, tuple[str, ...]] = {
    "LARGE_ENTITIES": ("No existe canal asociado", "No existe un canal asociado"),
    "SMALL_ENTITIES": ("NO EXISTE CANAL ASOCIADO",),
}

CANALES_PAGO: dict[str, tuple[str, ...]] = {
    "LARGE_ENTITIES": (
        "Por correo", "Correo Electrónico", "Correo electrónico",
        "Plataforma online de terceros", "Agencia/Oficina Especial",
        "Domicilio",
    ),
    "SMALL_ENTITIES": ("CORREO ELECTRONICO", "RECOJO EN AGENCIA", "OFICINA"),
}

# Document-type surface forms, including the raw numeric code an export
# occasionally leaks instead of a label.
TIPOS_DOC: dict[str, tuple[str, ...]] = {
    "LARGE_ENTITIES": (
        "DNI", "DNI", "DNI", "DNI", "Documento Nacional de Identidad",
        "CE", "RUC",
    ),
    "SMALL_ENTITIES": (
        "DNI", "DNI", "DNI", "DNI", "DOCUMENTO DE IDENTIDAD", "21", "RUC",
    ),
}

ESTADOS: dict[str, str] = {
    "LARGE_ENTITIES": "Atendido",
    "SMALL_ENTITIES": "ATENDIDO",
}

TIPOS_RESOLUCION: dict[str, dict[str, tuple[str, ...]]] = {
    "LARGE_ENTITIES": {
        "usuario": ("A favor del usuario", "A favor del Usuario", "Usuario"),
        "empresa": ("A favor de la empresa", "A favor de la entidad", "Empresa"),
    },
    "SMALL_ENTITIES": {
        "usuario": ("A FAVOR DEL USUARIO",),
        "empresa": ("A FAVOR DE LA ENTIDAD", "A FAVOR DE LA EMPRESA"),
    },
}

# Ubigeo, deliberately dirty — see the module docstring. One is an int.
UBIGEOS: tuple[object | None, ...] = (
    "150101", "150140", "040101", "080108", "130101", "200101", "110101",
    "150100", 150100, "1501", "401", "000000", "0", None, None, None,
)


# ---------------------------------------------------------------------------
# Case taxonomy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseType:
    """A producto/motivo pairing with the prose that goes with it.

    ``claims`` are what the customer writes; ``resolutions`` are what the
    institution writes back. Both are templates — the substituted values
    are drawn per row, so two rows of the same case type share a shape
    and nothing else.

    Templates are hand-written rather than model-generated, following the
    reasoning recorded at the top of
    ``data/synthetic-corpus-templates.yaml``: it keeps the corpus
    deterministic, reviewable in a diff, and auditable.
    """

    producto: str
    motivo: str
    submotivos: tuple[str | None, ...]
    claims: tuple[str, ...]
    resolutions: tuple[str, ...]
    weight: float
    monetary: bool = True
    bancaseguros: bool = False


CASE_TYPES: tuple[CaseType, ...] = (
    CaseType(
        producto="Tarjeta de crédito",
        motivo="Operaciones no reconocidas sin abono temporal",
        submotivos=("Consumo", "Operación ejecutada con errores", None),
        weight=0.16,
        claims=(
            "Solicito el desconocimiento de un cargo no reconocido por S/ {monto} "
            "aplicado el {fecha} a mi tarjeta terminada en {terminal}. No autoricé "
            "esa operación ni compartí mis claves con nadie. Adjunto el detalle del "
            "estado de cuenta donde figura el consumo.",
            "El {fecha} revisé mi estado de cuenta y encontré tres consumos que no "
            "reconozco, por un total de S/ {monto}, todos en la tarjeta terminada en "
            "{terminal}. Reporté el bloqueo por {canal} el mismo día. Pido la "
            "reversa de los cargos y que no se generen intereses sobre ese monto.",
            "Un cargo no reconocido de S/ {monto} figura en mi tarjeta terminada en "
            "{terminal} con fecha {fecha}. Nunca he realizado compras por ese canal y "
            "la tarjeta estuvo en mi poder todo el día. Solicito la anulación del "
            "consumo y la reposición del plástico.",
        ),
        resolutions=(
            "Hemos revisado el consumo observado del {fecha} por S/ {monto} en la "
            "tarjeta terminada en {terminal}. La operación se registró sin las "
            "validaciones de seguridad que corresponden a una compra presencial, por "
            "lo que procede su desconocimiento. El extorno se aplicó a su línea y los "
            "intereses generados sobre ese importe fueron anulados. La reposición de "
            "la tarjeta se encuentra disponible en la oficina {oficina}.",
            "Concluida la investigación del consumo del {fecha} por S/ {monto}, los "
            "registros del comercio muestran autenticación con clave y con el segundo "
            "factor enviado al teléfono registrado en su cuenta. Por ese motivo la "
            "operación se mantiene como reconocida y el cargo no será extornado. "
            "Queda a su disposición el detalle técnico de la autenticación en {canal}.",
        ),
    ),
    CaseType(
        producto="Cuenta de ahorro con tarjeta de débito",
        motivo="Transacciones no procesadas / mal realizadas",
        submotivos=("Operación no ejecutada", "Operación ejecutada con errores"),
        weight=0.14,
        claims=(
            "El {fecha} a las {hora} intenté retirar S/ {monto} en el cajero de la "
            "agencia de {lugar}. El equipo retuvo mi tarjeta y no entregó el dinero, "
            "pero el importe salió de mi cuenta. Necesito la devolución y la "
            "liberación de mi tarjeta.",
            "Realicé un depósito de S/ {monto} el {fecha} por {canal_op} y hasta hoy "
            "no se refleja en mi cuenta. Cuento con el voucher de la operación. "
            "Solicito que se regularice el abono a la brevedad.",
            "El {fecha} el sistema falló a mitad de una operación por S/ {monto} en "
            "{canal_op}. La pantalla mostró un error, la operación no se completó y "
            "sin embargo el monto fue descontado de mi cuenta de ahorros.",
        ),
        resolutions=(
            "Verificamos la operación del {fecha} en el cajero de {lugar}. El arqueo "
            "del equipo confirma un sobrante equivalente a S/ {monto}, por lo que el "
            "abono se aplicó a su cuenta con fecha valor del día de la operación. Su "
            "tarjeta fue destruida por seguridad y la reposición está disponible en la "
            "oficina {oficina}.",
            "Su operación del {fecha} por S/ {monto} quedó registrada como no "
            "concluida en nuestros sistemas y el importe fue devuelto a su cuenta el "
            "mismo día hábil siguiente. Puede verificar el extorno en su estado de "
            "cuenta con la glosa de regularización.",
            "Revisada la operación observada del {fecha}, los registros muestran que "
            "el importe de S/ {monto} sí fue entregado y la transacción se cerró "
            "correctamente. Por ello su reclamo se declara no procedente. El detalle "
            "de la operación queda a su disposición en la oficina {oficina}.",
        ),
    ),
    CaseType(
        producto="Cuenta de ahorro con tarjeta de débito",
        motivo="Operaciones no reconocidas sin abono temporal",
        submotivos=("Operación ejecutada con errores", None),
        weight=0.11,
        claims=(
            "Desconozco {dias} transferencias hechas desde mi cuenta el {fecha} por un "
            "total de S/ {monto}. No realicé esas operaciones y no he entregado mis "
            "claves. Presenté la denuncia correspondiente y solicito la devolución del "
            "dinero.",
            "El {fecha} recibí alertas de operaciones que no hice, por S/ {monto} en "
            "total. Bloqueé la cuenta por {canal} de inmediato. Pido el extorno y que "
            "se revise cómo se autorizaron esos movimientos.",
        ),
        resolutions=(
            "Las operaciones desconocidas del {fecha} por S/ {monto} se ejecutaron "
            "desde un dispositivo no afiliado a su banca digital. Al no acreditarse la "
            "autenticación que corresponde, el importe fue restituido íntegramente a su "
            "cuenta y su acceso digital fue re-enrolado.",
            "Concluido el análisis de las operaciones del {fecha} por S/ {monto}, se "
            "verificó que fueron autorizadas desde el dispositivo afiliado a su banca "
            "digital y con la clave de un solo uso enviada a su número registrado. En "
            "consecuencia el reclamo se declara no procedente.",
        ),
    ),
    CaseType(
        producto="Tarjeta de crédito",
        motivo="Cobros indebidos de intereses, comisiones, gastos y tributos (tales "
               "como seguros, ITF, entre otros cargos, según corresponda)",
        submotivos=("Comisiones", "Gastos", "Consumo"),
        weight=0.10,
        claims=(
            "En mi último estado de cuenta figura una comisión de S/ {monto} por "
            "membresía anual que nunca acordé. Al contratar la tarjeta se me informó "
            "que era libre de membresía. Solicito la devolución del cobro y la "
            "corrección de las condiciones.",
            "El {fecha} me cobraron S/ {monto} por concepto de mantenimiento en la "
            "tarjeta terminada en {terminal}. Ese cargo no aparece en el tarifario que "
            "me entregaron al firmar el contrato. Pido el extorno.",
            "Se aplicaron intereses por S/ {monto} sobre un consumo que pagué dentro "
            "de la fecha de vencimiento. Cuento con la constancia del pago del {fecha}. "
            "Solicito que se anulen los intereses y se rectifique mi estado de cuenta.",
        ),
        resolutions=(
            "Revisado su contrato, la exoneración de membresía aplicaba solo al primer "
            "año, condición que figura en la cláusula de comisiones de la hoja resumen. "
            "No obstante, en atención a su reclamo se extornó el cobro de S/ {monto} "
            "por excepción y se registró su solicitud de no renovación.",
            "El cargo de S/ {monto} del {fecha} corresponde a una comisión que no fue "
            "informada en su hoja resumen. Procede su devolución: el extorno se aplicó "
            "a su estado de cuenta y el concepto fue desactivado para su producto.",
            "Su pago del {fecha} ingresó a nuestros sistemas después del cierre del "
            "ciclo de facturación, lo que generó los intereses observados de S/ {monto}. "
            "Al tratarse de un pago realizado en la fecha de vencimiento, los intereses "
            "fueron anulados y regularizados en el siguiente estado de cuenta.",
        ),
    ),
    CaseType(
        producto="Crédito de consumo",
        motivo="Cobros indebidos de intereses, comisiones, gastos y tributos (tales "
               "como seguros, ITF, entre otros cargos, según corresponda)",
        submotivos=("Comisiones", "Gastos", None),
        weight=0.09,
        claims=(
            "Cancelé anticipadamente mi préstamo con contrato N° {contrato} a inicios "
            "de {mes}, y aun así se me descontó S/ {monto} por planilla ese mes. "
            "Adjunto la constancia de no adeudo y solicito la devolución del importe "
            "descontado.",
            "Solicito la devolución de S/ {monto} cobrados el {fecha} por un seguro "
            "asociado al crédito con contrato N° {contrato} que nunca contraté. En "
            "ningún momento firmé la solicitud de ese seguro.",
            "Mi préstamo con contrato N° {contrato} registra un cobro de S/ {monto} "
            "por gastos administrativos que no figuran en el cronograma que me "
            "entregaron. Pido la rectificación del cronograma y la devolución.",
        ),
        resolutions=(
            "Validamos que con fecha {fecha} se realizó la cancelación anticipada del "
            "crédito con contrato N° {contrato}. En los préstamos con descuento por "
            "planilla el cargo se genera con un mes de anticipación al vencimiento, por "
            "lo que la cuota siguiente ya había sido remitida por su empleador. La "
            "devolución de S/ {monto} se encuentra a su disposición en la oficina "
            "{oficina}, previa coordinación con {departamento}.",
            "El seguro observado en el contrato N° {contrato} no cuenta con la "
            "constancia de contratación firmada por usted. Procede su reclamo: el "
            "importe de S/ {monto} fue devuelto y la cobertura quedó anulada desde su "
            "origen, sin efecto sobre el cronograma del crédito.",
            "Los gastos administrativos de S/ {monto} corresponden al concepto "
            "informado en la cláusula de comisiones y gastos de su hoja resumen, "
            "documento que forma parte del contrato N° {contrato}. Su reclamo se "
            "declara no procedente y el cronograma se mantiene sin modificación.",
        ),
    ),
    CaseType(
        producto="Transferencias de fondos (interbancarias o intrabancario)",
        motivo="Transacciones no procesadas / mal realizadas",
        submotivos=("Operación no ejecutada", "Operación ejecutada con errores"),
        weight=0.08,
        claims=(
            "El {fecha} realicé una transferencia de S/ {monto} por {canal_op}. El dinero "
            "salió de mi cuenta pero nunca llegó a la cuenta de destino. Han pasado "
            "{dias} días y no obtengo respuesta.",
            "Una transferencia interbancaria por S/ {monto} enviada el {fecha} fue "
            "rechazada por el banco destino, pero el importe no ha vuelto a mi cuenta. "
            "Solicito la devolución inmediata.",
        ),
        resolutions=(
            "La transferencia del {fecha} por S/ {monto} fue rechazada en la entidad "
            "de destino por diferencia en el titular de la cuenta. El importe retornó a "
            "su cuenta de origen con fecha valor del día de la operación; puede "
            "verificarlo en su estado de cuenta.",
            "Su transferencia del {fecha} por S/ {monto} se encontraba retenida en el "
            "proceso de compensación interbancaria. Regularizada la operación, el abono "
            "se aplicó en la cuenta de destino y se le comunicó por {canal}.",
        ),
    ),
    CaseType(
        producto="Cuenta de ahorro sin tarjeta de débito",
        motivo="Problemas relacionados con cajeros automáticos",
        submotivos=("ATM propio", "Operación ejecutada con errores"),
        weight=0.07,
        claims=(
            "El {fecha} a las {hora} el cajero de {lugar} me entregó S/ {monto} menos "
            "de lo que solicité, y el comprobante salió por el monto completo. "
            "Solicito la revisión del arqueo del equipo.",
            "El cajero automático de {lugar} descontó S/ {monto} de mi cuenta el "
            "{fecha} sin entregar el dinero. El equipo mostró un mensaje de error y no "
            "emitió comprobante.",
        ),
        resolutions=(
            "El arqueo del cajero de {lugar} correspondiente al {fecha} presentó un "
            "sobrante de S/ {monto}, consistente con lo que usted informa. El abono fue "
            "aplicado a su cuenta con fecha valor del día de la operación.",
            "El arqueo del equipo de {lugar} del {fecha} cerró sin diferencias y los "
            "registros muestran la dispensación completa de S/ {monto}. Por ello su "
            "reclamo se declara no procedente; el detalle del arqueo queda a su "
            "disposición.",
        ),
    ),
    CaseType(
        producto="Crédito de consumo",
        motivo="Inadecuada o insuficiente información sobre operaciones, productos y "
               "servicios",
        submotivos=(None, "Comisiones"),
        weight=0.07,
        monetary=False,
        claims=(
            "Solicité información sobre las comisiones de mi crédito con contrato N° "
            "{contrato} el {fecha} y lo que me informaron por {canal} no coincide con "
            "lo que figura en el contrato firmado. Pido una respuesta por escrito.",
            "Al contratar mi crédito se me informó una tasa distinta a la que aparece "
            "en el cronograma del contrato N° {contrato}. Nadie me explicó el cambio y "
            "llevo {dias} días pidiendo una aclaración.",
        ),
        resolutions=(
            "Contrastada la información brindada por {canal} con su contrato N° "
            "{contrato}, se confirma que la atención recibida fue imprecisa respecto de "
            "las comisiones aplicables. Su reclamo procede: le remitimos el tarifario "
            "vigente y el detalle de los conceptos, y el caso fue derivado a "
            "{departamento} para retroalimentación del canal.",
            "La tasa consignada en el cronograma del contrato N° {contrato} coincide "
            "con la de su hoja resumen, documento suscrito por usted al momento del "
            "desembolso. No se acredita información distinta, por lo que el reclamo se "
            "declara no procedente. Se adjunta copia de la hoja resumen.",
        ),
    ),
    CaseType(
        producto="Cuenta corriente",
        motivo="Retenciones indebidas (incluye retenciones judiciales o de cobranza "
               "coactiva)",
        submotivos=(None,),
        weight=0.06,
        claims=(
            "Mi cuenta registra una retención de S/ {monto} desde el {fecha} que no "
            "corresponde: el proceso al que se refiere no está a mi nombre. Solicito el "
            "levantamiento de la retención y la devolución de los fondos.",
            "El {fecha} se retuvieron S/ {monto} de mi cuenta corriente sin "
            "notificación previa. No tengo ningún proceso judicial en curso y necesito "
            "esos fondos para el pago de planillas.",
        ),
        resolutions=(
            "La retención aplicada el {fecha} por S/ {monto} respondió a una homonimia "
            "en el documento de identidad consignado en el oficio recibido. Verificada "
            "la diferencia, la retención fue levantada y los fondos liberados en su "
            "cuenta el mismo día.",
            "La retención de S/ {monto} del {fecha} se ejecutó en cumplimiento de un "
            "mandato de autoridad competente, que la entidad está obligada a atender. "
            "El levantamiento corresponde al órgano que la ordenó. Su reclamo se declara "
            "no procedente y le remitimos copia del oficio.",
        ),
    ),
    CaseType(
        producto="Créditos a pequeñas empresas y microempresas",
        motivo="Modificación indebida de las tasas de interés, comisiones u otras "
               "condiciones pactadas",
        submotivos=(None, "Comisiones"),
        weight=0.05,
        claims=(
            "La tasa de mi crédito con contrato N° {contrato} subió sin que se me "
            "comunicara. La cuota pasó a S/ {monto} y no recibí ninguna notificación en "
            "los plazos que exige la norma. Solicito que se restituya la condición "
            "pactada.",
            "Se modificaron las condiciones de mi línea de capital de trabajo el "
            "{fecha}, elevando la cuota a S/ {monto}. Nunca acepté esa modificación.",
        ),
        resolutions=(
            "No se acredita la comunicación previa de la modificación aplicada al "
            "contrato N° {contrato} en los plazos establecidos. Procede su reclamo: se "
            "restituyó la condición pactada, se recalculó el cronograma y la diferencia "
            "cobrada de S/ {monto} fue devuelta a su cuenta.",
            "La modificación de condiciones del contrato N° {contrato} fue comunicada "
            "el {fecha} por {canal}, con la anticipación que corresponde y en el medio "
            "que usted registró como preferente. Su reclamo se declara no procedente.",
        ),
    ),
    CaseType(
        producto="Banca - Seguros (seguros vendidos en canales del sistema financiero)",
        motivo="Contratación o cargo indebido de seguros",
        submotivos=(None, "Comisiones"),
        weight=0.05,
        bancaseguros=True,
        claims=(
            "En mi estado de cuenta aparece el cobro de un seguro de protección de "
            "tarjeta por S/ {monto} desde el {fecha}. Nunca contraté esa cobertura ni "
            "firmé una solicitud. Solicito la anulación y la devolución de todo lo "
            "cobrado.",
            "Al abrir mi cuenta en la oficina {oficina} me incluyeron un seguro que no "
            "pedí, con una prima de S/ {monto}. Solicito la baja de la cobertura y la "
            "devolución de las primas cobradas.",
        ),
        resolutions=(
            "La cobertura observada no cuenta con la constancia de contratación firmada "
            "por usted, requisito exigible para su comercialización. Procede su reclamo: "
            "la póliza fue anulada desde su origen y las primas cobradas, S/ {monto} en "
            "total, fueron devueltas a su cuenta.",
            "La contratación del seguro se acredita con la solicitud suscrita el "
            "{fecha}, cuya copia se adjunta. La cobertura estuvo vigente durante el "
            "periodo cobrado, por lo que no corresponde la devolución de la prima de "
            "S/ {monto}. Registramos su solicitud de baja, efectiva al término de la "
            "vigencia.",
        ),
    ),
    CaseType(
        producto="Crédito de consumo",
        motivo="Reporte indebido en la central de riesgos",
        submotivos=(None,),
        weight=0.04,
        monetary=False,
        claims=(
            "Aparezco reportado con calificación deficiente por una deuda de S/ {monto} "
            "que cancelé el {fecha}. Cuento con la constancia de no adeudo. Solicito la "
            "rectificación del reporte en la central de riesgos.",
            "Fui reportado en la central de riesgos por el crédito con contrato N° "
            "{contrato}, que nunca solicité. Presenté mi denuncia por suplantación y "
            "llevo {dias} días esperando la corrección.",
        ),
        resolutions=(
            "Confirmada la cancelación del {fecha}, se remitió la rectificación del "
            "reporte a la central de riesgos dentro del plazo normativo. La "
            "actualización se refleja en el siguiente reporte mensual y le remitimos la "
            "constancia por {canal}.",
            "El crédito con contrato N° {contrato} presenta indicios de contratación "
            "fraudulenta. Se anuló la operación, se rectificó su reporte en la central "
            "de riesgos y el caso fue derivado a {departamento} para las acciones "
            "correspondientes.",
        ),
    ),
    CaseType(
        producto="Servicios varios (cambios, cobranzas, pagos judiciales, pago de "
                 "planillas, entre otros similares)",
        motivo="Disconformidad por notificaciones dirigidas a terceras personas",
        submotivos=(None,),
        weight=0.04,
        monetary=False,
        claims=(
            "El {fecha} a las {hora} un representante de cobranzas se presentó en "
            "{direccion} y trató el asunto de mi deuda con una tercera persona que no "
            "tiene relación con el crédito. Exijo que las comunicaciones se dirijan "
            "únicamente a mí.",
            "Recibo llamadas de cobranza dirigidas a mis familiares y a mi centro de "
            "trabajo desde el {fecha}. Nunca autoricé el uso de esos contactos. "
            "Solicito el cese inmediato de esas comunicaciones.",
        ),
        resolutions=(
            "Verificada la visita del {fecha} en {direccion}, la gestión no se ajustó a "
            "los lineamientos de trato con terceros. Su reclamo procede: la empresa de "
            "cobranza fue amonestada, los contactos de terceros fueron retirados de su "
            "expediente y {departamento} asumió la gestión directa del caso.",
            "Revisados los registros de contacto desde el {fecha}, las comunicaciones "
            "se dirigieron a los números que usted registró como propios. No se "
            "acredita contacto con terceros, por lo que el reclamo se declara no "
            "procedente. Atendimos su solicitud de actualizar sus datos de contacto.",
        ),
    ),
    CaseType(
        producto="Cuenta a plazo",
        motivo="Liquidaciones erradas de intereses en cuentas de ahorro o depósitos a "
               "plazo fijo",
        submotivos=(None,),
        weight=0.04,
        claims=(
            "Al vencimiento de mi depósito a plazo del {fecha} los intereses "
            "liquidados fueron S/ {monto}, menos de lo que corresponde según la tasa "
            "pactada. Solicito la revisión del cálculo.",
            "Mi depósito a plazo fue renovado automáticamente el {fecha} con una tasa "
            "menor a la pactada, lo que redujo mis intereses en S/ {monto}. No autoricé "
            "esa renovación.",
        ),
        resolutions=(
            "Recalculada la liquidación del {fecha} con la tasa pactada en su "
            "constancia de depósito, se determinó una diferencia a su favor de S/ "
            "{monto}, abonada a su cuenta junto con los intereses correspondientes.",
            "La renovación del {fecha} se aplicó conforme a la instrucción de "
            "renovación automática registrada al momento de la apertura, y a la tasa "
            "vigente para el nuevo periodo. La liquidación es correcta y el reclamo se "
            "declara no procedente.",
        ),
    ),
    CaseType(
        producto="Cuenta de ahorro con tarjeta de débito",
        motivo="Problemas relacionados con la página web de la empresa",
        submotivos=(None, "Operación no ejecutada"),
        weight=0.04,
        monetary=False,
        claims=(
            "Desde el {fecha} no puedo acceder a mi banca por internet ni al "
            "aplicativo. El sistema muestra un error al validar mi clave y he llamado "
            "{dias} veces sin solución. Necesito operar mi cuenta.",
            "La página web no me permite descargar mis estados de cuenta desde el "
            "{fecha}. Los necesito para un trámite y en la oficina {oficina} me "
            "indicaron que debía obtenerlos por el canal digital.",
        ),
        resolutions=(
            "Confirmamos una incidencia en el enrolamiento de su usuario desde el "
            "{fecha}, que impedía la validación de su clave. El acceso fue restablecido "
            "y se le comunicó por {canal}. Lamentamos la afectación durante ese periodo.",
            "Su usuario presentaba un bloqueo por intentos fallidos consecutivos, "
            "medida de seguridad que se activa automáticamente. Regularizado el acceso, "
            "los estados de cuenta del periodo solicitado le fueron remitidos por "
            "{canal} y quedan disponibles en la oficina {oficina}.",
        ),
    ),
)

# Bancaseguros detail, used only when a row is flagged BAN_SEG = SI.
SEGUROS: tuple[str, ...] = (
    "Seguro de protección de tarjeta (crédito o débito)",
    "Desgravamen",
    "Domiciliario",
)

MESES: tuple[str, ...] = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "setiembre", "octubre", "noviembre", "diciembre",
)

# How a complainant opens. Half of them introduce themselves by name and
# document number, which is the point: the redaction step downstream has
# to find PII inside free text, not just in the structured columns.
CLAIM_PREAMBLES: tuple[str, ...] = (
    "Buenas tardes, mi nombre es {nombre} con {tipo_doc} {dni} y me dirijo a "
    "ustedes para presentar el siguiente reclamo.",
    "Estimados señores, quien suscribe, {nombre}, con {tipo_doc} {dni}, "
    "presenta el siguiente reclamo.",
    "Buenos días, soy {nombre} ({tipo_doc} {dni}), cliente de la entidad, y "
    "escribo por lo siguiente.",
    "Por medio de la presente, yo {nombre} con {tipo_doc} {dni} y domicilio en "
    "{direccion}, expongo mi reclamo.",
)

# And how they close. Appending none, one or two of these gives the
# fixture the length spread free text actually has, instead of eighty
# narratives of identical shape.
CLAIM_ADDENDA: tuple[str, ...] = (
    "Adjunto copia de mi documento de identidad y el comprobante de la operación.",
    "Ya presenté este caso por {canal} el {fecha} y no obtuve respuesta.",
    "Solicito respuesta por escrito dentro del plazo que establece la norma.",
    "Es la segunda vez que me ocurre lo mismo con este producto.",
    "Necesito una solución pronta porque ese dinero estaba destinado al pago de "
    "mi alquiler.",
    "Dejo constancia de que atendí todas las llamadas y entregué toda la "
    "documentación que me solicitaron.",
    "De no recibir respuesta acudiré a la instancia que corresponda.",
    "Pido además que se me informe el resultado de la investigación interna.",
    "Mi teléfono de contacto es el que figura registrado en mi cuenta y estoy "
    "disponible de {hora} en adelante.",
)


# ---------------------------------------------------------------------------
# Value generation
# ---------------------------------------------------------------------------


def _caps(text: str) -> str:
    """ALL-CAPS the way the small-entity export does it — accents kept."""
    return text.upper()


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _dni(rng: random.Random) -> str:
    return f"{rng.randint(10_000_000, 79_999_999):08d}"


def _ruc(rng: random.Random) -> str:
    """An 11-digit RUC with the Sunat module-11 check digit.

    Same algorithm the synthetic-corpus generator uses, so a fixture row
    that reaches the API passes the same format validation a generated
    corpus row does.
    """
    body = f"20{rng.randint(10_000_000, 59_999_999):08d}"
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(d) * w for d, w in zip(body, weights))
    check = 11 - (total % 11)
    return body + str({10: 0, 11: 1}.get(check, check))


def _client_number(rng: random.Random) -> str:
    """A twelve-digit internal client number.

    The small-entity sheet identifies people by the core-banking client
    number while still declaring the document type as ``DNI``. That is a
    genuine data-quality fault and ``DQ-A1A-009`` is the rule that
    catches it — the fixture keeps a bounded number of these on purpose.
    """
    return f"{rng.randint(100_000_000_000, 999_999_999_999):012d}"


def _amount(rng: random.Random) -> float:
    """A monetary amount over the range Peruvian retail disputes fall in.

    Log-normal, so the fixture has many three-figure disputes and the
    occasional five-figure one, and no amount is a round number unless
    the draw made it so.
    """
    value = rng.lognormvariate(6.0, 1.05)
    return round(min(max(value, 18.0), 48_000.0), 2)


def _name(rng: random.Random) -> str:
    """A client name, assembled — a combination, not a person.

    Surname-first, the way a complaints register lists people. Both
    given names come from the same pool when there are two.
    """
    pool = rng.choice(GIVEN_NAMES)
    count = 2 if rng.random() < 0.35 else 1
    given = " ".join(rng.sample(pool, count))
    return f"{' '.join(rng.sample(SURNAMES, 2))}, {given}"


def _spanish_date(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _prose_name(register_name: str) -> str:
    """``TORRES QUISPE, ELENA`` → ``Elena Torres Quispe``.

    The register lists people surname-first in capitals; a complainant
    writing about themselves does not.
    """
    surnames, _, given = register_name.partition(", ")
    return " ".join(part.capitalize() for part in f"{given} {surnames}".split())


def _prose_doc_type(doc_type: str) -> str:
    """The document type as a complainant writes it in a sentence.

    The register's surface forms include a bare numeric code, which
    nobody writes in prose.
    """
    return {
        "DNI": "DNI",
        "RUC": "RUC",
        "CE": "carné de extranjería",
    }.get(doc_type, "documento de identidad")


def _substitutions(rng: random.Random, ingreso: date, amount: float,
                   name: str, doc_type: str, doc_number: str) -> dict[str, str]:
    """Every placeholder a template can reference, drawn for one row."""
    return {
        "nombre": _prose_name(name),
        "tipo_doc": _prose_doc_type(doc_type),
        "dni": doc_number,
        "monto": f"{amount:,.2f}",
        "fecha": _spanish_date(ingreso - timedelta(days=rng.randint(1, 20))),
        "mes": MESES[ingreso.month - 1],
        "hora": f"{rng.randint(8, 20):02d}:{rng.choice(('05', '15', '22', '30', '41', '56'))}",
        "terminal": f"{rng.randint(1000, 9999)}",
        "contrato": f"{rng.randint(1, 9)}****{rng.randint(100, 999)}",
        "dias": str(rng.randint(2, 45)),
        # Every form carries its article, so a template can put "por",
        # "en" or "registrado por" in front of it and still read.
        "canal": rng.choice((
            "la línea telefónica", "la banca por internet", "el aplicativo móvil",
            "el correo electrónico", "la página web",
        )),
        # Where an operation was performed, as opposed to where the
        # complaint was raised. Nobody transfers money by email.
        "canal_op": rng.choice((
            "la banca por internet", "el aplicativo móvil", "el cajero automático",
            "la agencia", "la billetera digital",
        )),
        "lugar": rng.choice(LOCATIONS),
        "direccion": f"{rng.choice(ADDRESSES)}, {rng.choice(LOCATIONS)}",
        "oficina": f"N° {rng.randint(100, 899):04d} - {rng.choice(LOCATIONS)}",
        "departamento": rng.choice(DEPARTMENTS),
        "entidad": rng.choice(ENTITIES),
    }


def _resolution_letter(body: str, codigo: str, ingreso: date,
                       canal: str) -> str:
    """Wrap a resolution body in the formal letter register.

    Institutions answer complaints in a fixed formula — greeting,
    reference to the complaint code and date, findings, close. The
    register is a format, and reproducing it is what makes the demo's
    triage screen look like the document a supervisor actually reads.
    """
    opening = (
        f"Mediante la presente le hacemos llegar nuestro cordial saludo y "
        f"damos respuesta a su reclamo N° {codigo} de fecha "
        f"{_spanish_date(ingreso)}, registrado por {canal}. Al respecto le "
        f"informamos: "
    )
    closing = (
        " Agradecemos su comunicación y quedamos a su disposición para "
        "cualquier consulta adicional. Atentamente, el área de atención al "
        "usuario."
    )
    return opening + body + closing


def _claim_text(rng: random.Random, case: CaseType,
                subs: dict[str, str]) -> str:
    """Assemble one complainant's free text.

    A preamble on some, the case narrative always, nothing to two
    closing sentences after it — which is what gives the eighty rows a
    length spread rather than eighty paragraphs of the same size. Free
    text is then roughed up the way free text arrives: about a third of
    complainants type without accents, and some never reach for the
    shift key.
    """
    parts: list[str] = []
    if rng.random() < 0.5:
        parts.append(rng.choice(CLAIM_PREAMBLES).format(**subs))
    parts.append(case.claims[rng.randrange(len(case.claims))].format(**subs))
    for addendum in rng.sample(CLAIM_ADDENDA, rng.choices((0, 1, 2, 3),
                                                          weights=(3, 4, 3, 2))[0]):
        parts.append(addendum.format(**subs))

    text = " ".join(parts)
    roll = rng.random()
    if roll < 0.30:
        text = _strip_accents(text)
    elif roll < 0.38:
        text = text[0].lower() + text[1:]
    return text


def _pick_case(rng: random.Random) -> CaseType:
    return rng.choices(CASE_TYPES, weights=[c.weight for c in CASE_TYPES])[0]


def _row(rng: random.Random, sheet: str, index: int) -> dict:
    """One fixture row — all 28 report columns plus the three demo hints."""
    large = sheet == "LARGE_ENTITIES"

    # The first row of the large sheet is the demo's recommended case:
    # an unrecognised credit-card charge. FIInbox pins the first row
    # whose narrative says "cargo no reconocido" or whose product is a
    # card, so the star row has to be one of those by construction.
    case = CASE_TYPES[0] if index == 0 and large else _pick_case(rng)

    ingreso = date(YEAR, 1, 1) + timedelta(days=rng.randint(0, 357))
    resolucion = ingreso + timedelta(days=rng.randint(5, 28))
    amount = _amount(rng)

    doc_type = rng.choice(TIPOS_DOC[sheet])
    # Large-entity rows carry a document number that matches its declared
    # type. Small-entity rows carry the core-banking client number
    # instead — see _client_number, and DQ-A1A-009.
    if doc_type == "RUC":
        doc_number = _ruc(rng)
    elif large:
        doc_number = _dni(rng)
    else:
        doc_number = _client_number(rng)

    name = _name(rng)
    subs = _substitutions(rng, ingreso, amount, name, doc_type, doc_number)

    codigo = (
        f"{ingreso.day:02d}{ingreso.month:02d}{YEAR % 100:02d}"
        f"{rng.randint(1, 99_999):05d}"
        if large
        else f"R{rng.randint(1, 9):01d}0490{YEAR}{rng.randint(1, 99_999):05d}"
    )

    canal_ingreso = rng.choice(CANALES[sheet])
    # A complaint about no operation in particular has no operation channel.
    canal_operacion = (
        rng.choice(SIN_CANAL[sheet]) if not case.monetary and rng.random() < 0.5
        else rng.choice(CANALES[sheet])
    )

    favours_user = rng.random() < 0.42
    outcome = "usuario" if favours_user else "empresa"
    claim = _claim_text(rng, case, subs)
    # Resolution templates are ordered: the ones that uphold the
    # complaint first, the one that rejects it last.
    resolutions = case.resolutions
    body = (
        resolutions[rng.randrange(max(1, len(resolutions) - 1))]
        if favours_user else resolutions[-1]
    ).format(**subs)

    # An ampliación is a request for more time. Common, and usually
    # recorded as a date with no channel against it.
    has_ampliacion = rng.random() < 0.42
    fecha_ampliacion = (
        (ingreso + timedelta(days=rng.randint(2, 12))).isoformat()
        if has_ampliacion else None
    )

    bancaseguros = case.bancaseguros and rng.random() < 0.5

    row = {
        "COD_REC": codigo,
        "TID_CLI": doc_type,
        "NRO_CLI": doc_number,
        "NCL_CLI": name,
        "COD_CLI": f"CLI{doc_number}",
        "FEC_ING": ingreso.isoformat(),
        "CNL_ING": canal_ingreso,
        "CNL_OPE": canal_operacion,
        "FEC_AMP": fecha_ampliacion,
        "CNL_AMP": rng.choice(CANALES[sheet]) if has_ampliacion and rng.random() < 0.1 else None,
        "FEC_RES": resolucion.isoformat(),
        "CNL_PAC": rng.choice(CANALES_PAGO[sheet]),
        "UBI_REC": rng.choice(UBIGEOS),
        "PRD_SBS": case.producto if large else _caps(case.producto),
        "MOT_SBS": case.motivo if large else _caps(case.motivo),
        "SUB_SBS": None,
        "DET_REC": claim,
        "TIP_RES": rng.choice(TIPOS_RESOLUCION[sheet][outcome]),
        "DET_RES": _resolution_letter(body, codigo, ingreso, subs["canal"]),
        "PRD_EMP": rng.choice(PRODUCTOS_INTERNOS),
        "EST_REC": ESTADOS[sheet],
        # A prior complaint on the same matter. Rare.
        "COD_PRV": (
            f"R{rng.randint(1, 9):01d}0490{YEAR}{rng.randint(1, 99_999):05d}"
            if rng.random() < 0.08 else None
        ),
        "BAN_SEG": "SI" if bancaseguros else "NO",
        "PRD_SBS_SEG": rng.choice(SEGUROS) if bancaseguros else None,
        "MOT_SBS_SEG": case.motivo if bancaseguros else None,
        "SUB_SBS_SEG": None,
        # Monto pendiente — what is still owed to the user once the case
        # closed. Zero on anything resolved in the institution's favour.
        "MNT_PEN_REC": amount if (favours_user and case.monetary) else 0,
        "EMPRESA": f"Banco{1 if large else 2}" if index % 2 == 0 else f"Banco{3 if large else 4}",
    }

    submotivo = case.submotivos[rng.randrange(len(case.submotivos))]
    if submotivo is not None:
        row["SUB_SBS"] = submotivo if large else _caps(submotivo)

    row["__sheet"] = sheet
    row["__institution"] = "BANCO_DEMO_001" if large else "COOPAC_DEMO_002"
    row["__institution_id"] = "SBS-001234" if large else "SBS-005678"

    assert set(row) == set(COLS) | {"__sheet", "__institution", "__institution_id"}
    return row


def build(seed: int, rows_per_sheet: int) -> list[dict]:
    """The fixture: both sheets, interleaved so the inbox visibly mixes them."""
    large_rng = random.Random(seed)
    small_rng = random.Random(seed + 1)
    large = [_row(large_rng, "LARGE_ENTITIES", i) for i in range(rows_per_sheet)]
    small = [_row(small_rng, "SMALL_ENTITIES", i) for i in range(rows_per_sheet)]

    interleaved: list[dict] = []
    for i in range(rows_per_sheet):
        interleaved.append(large[i])
        interleaved.append(small[i])
    return interleaved


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seed", type=int, default=DEFAULT_SEED,
                   help=f"generation seed (default {DEFAULT_SEED})")
    p.add_argument("--rows-per-sheet", type=int, default=ROWS_PER_SHEET,
                   help=f"rows per sheet (default {ROWS_PER_SHEET}; the "
                        f"fixture is twice this)")
    p.add_argument("--out", type=Path, default=OUT,
                   help="output path (default app/src/lib/journey-emails.json)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = build(args.seed, args.rows_per_sheet)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Trailing newline, so the committed fixture and a fresh regeneration
    # are byte-identical and end-of-file-fixer has nothing to do.
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"wrote {len(rows)} rows → {args.out}  (synthetic, seed={args.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
