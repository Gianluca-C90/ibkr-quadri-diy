#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compilazione PDF dei quadri: sovrastampa dei valori sul Modello AdE PF2."""

import hashlib
import io
from decimal import Decimal

import genera_quadri as G
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blocco in iter(lambda: f.read(65536), b""):
            h.update(blocco)
    return h.hexdigest()


def formatta_valore(valore, tipo):
    if tipo == "euro":
        n = int(Decimal(str(valore)).quantize(Decimal("1")))
        return f"{n:,}".replace(",", ".")   # 1162 -> "1.162"
    return str(valore)


def _voce(valore, tipo, origine, norma):
    return {"valore": formatta_valore(valore, tipo), "origine": origine, "norma": norma}


def valori_da_risultati(res, ans):
    """Appiattisce il dict di genera() in {(quadro, campo): voce}.
    Ogni voce porta valore formattato + origine dato + norma (per l'audit)."""
    v = {}
    rw = res["rw"]
    NORMA_RW = "Istr. Redditi PF 2026, Quadro RW; DL 201/2011 art.19 (IVAFE)"
    for campo, tipo, org in [
        ("col1","codice","titolo possesso=proprietà"),
        ("col3","codice","conto deposito titoli estero (cod.20)"),
        ("col4","codice","Stato broker (CSV: valuta di base/sede)"),
        ("col5","codice","quota di possesso (risposta utente)"),
        ("col6","codice","criterio valore di mercato"),
        ("col7","euro","VPN iniziale (CSV)"),
        ("col8","euro","VPN finale (CSV) = base IVAFE"),
        ("col10","euro","giorni di possesso"),
        ("col14","codice","collegamento col reddito"),
        ("col29_ivafe","euro","IVAFE = val.fin × gg/anno × quota × 0,20%"),
        ("col30","euro","IVAFE dovuta"),
    ]:
        v[("RW", campo)] = _voce(rw[campo], tipo, org, NORMA_RW)

    NORMA_RM = "Istr. Redditi PF 2026, Quadro RM (RM31); TUIR art.18/44"
    for i, riga in enumerate(res["rm_div"] + res["rm_int"], start=1):
        v[("RM", f"r{i}_tipo")]   = _voce(riga["tipo"], "codice", "tipo reddito estero", NORMA_RM)
        v[("RM", f"r{i}_stato")]  = _voce(riga["stato"], "codice", "Stato emittente (decisione utente)", NORMA_RM)
        v[("RM", f"r{i}_reddito")]= _voce(G.euro(riga["reddito"]), "euro", "dividendi/interessi EUR (CSV)", NORMA_RM)
        v[("RM", f"r{i}_aliquota")]= _voce(26, "codice", "aliquota imposta sostitutiva 26%", NORMA_RM)
        v[("RM", f"r{i}_imposta")]= _voce(G.euro(riga["imposta"]), "euro", "26% del reddito", NORMA_RM)

    rt = res["rt"]
    NORMA_RT = "Istr. Redditi PF 2026, Quadro RT Sez. II; TUIR art.67/68"
    for campo, org in [
        ("RT11_1","totale corrispettivi"), ("RT11_2","totale costi"),
        ("RT52_2_plus","plusvalenza"), ("RT52_1_minus","minusvalenza"),
        ("RT13","minus. pregresse usate"), ("RT72","differenza imponibile"),
        ("RT73_imposta","imposta sostitutiva 26%"), ("RT74","imposta sostitutiva dovuta"),
        ("RT102_5","minus. residua"),
    ]:
        v[("RT", campo)] = _voce(rt[campo], "euro", org, NORMA_RT)

    if res.get("rl"):
        v[("RL","RL2_reddito")] = _voce(res["rl"], "euro", "OICR non armonizzato",
                                        "Istr. Redditi PF 2026, Quadro RL (RL2)")
    return v


# Etichetta-ancora -> pagina attesa nel PF2. Il Quadro RT e' su DUE pagine:
# RT11/RT13/RT52 in pag.6, RT72/RT73/RT102 in pag.7. Ogni campo si ancora al
# proprio rigo, cosi' nessun campo finisce nella pagina sbagliata o viene perso.
ANCORE = {
    "RW1": 9, "RM31": 4, "RL1": 2,
    "RT11": 6, "RT13": 6, "RT52": 6,
    "RT72": 7, "RT73": 7, "RT74": 7, "RT102": 7,
}


def carica_ancore(pf2_path):
    """Trova (pagina, x, y) dell'etichetta-ancora di ogni rigo nel PF2.
    Usa il visitor di pypdf: y in coordinate PDF (origine in basso-sinistra)."""
    reader = PdfReader(pf2_path)
    risultato = {}
    for etichetta, pag_attesa in ANCORE.items():
        trovato = {}
        def visit(text, cm, tm, fontdict, fontsize, _e=etichetta, _t=trovato):
            if _e in (text or "") and "x" not in _t:
                _t["x"] = tm[4]; _t["y"] = tm[5]
        reader.pages[pag_attesa].extract_text(visitor_text=visit)
        if "x" not in trovato:
            raise RuntimeError(f"Ancora '{etichetta}' non trovata in pagina {pag_attesa} del PF2")
        risultato[etichetta] = {"pagina": pag_attesa, "x": trovato["x"], "y": trovato["y"]}
    return risultato


class CoperturaError(Exception):
    """Disallineamento tra valori calcolati e caselle del modulo."""


# (quadro, campo) -> (ancora_rigo, dx, dy, align, tipo).
# ancora_rigo: etichetta in ANCORE (definisce pagina + origine del campo).
# dx,dy: offset in punti dall'ancora; align 'r' destra / 'l' sinistra.
# Codici left-aligned nella casella; importi right-aligned al ',00' prestampato.
FIELD_MAP = {
    # Quadro RW (ancora RW1 @ x=106.8 y=623.1), pag.9
    ("RW","col1"): ("RW1", 30.2, 54.0, "l", "codice"),
    ("RW","col3"): ("RW1", 115.2, 54.0, "l", "codice"),
    ("RW","col4"): ("RW1", 158.2, 54.0, "l", "codice"),
    ("RW","col5"): ("RW1", 201.2, 54.0, "l", "codice"),
    ("RW","col6"): ("RW1", 244.2, 54.0, "l", "codice"),
    ("RW","col7"): ("RW1", 347.6, 52.5, "r", "euro"),
    ("RW","col8"): ("RW1", 441.7, 52.2, "r", "euro"),
    ("RW","col10"): ("RW1", 108.2, 18.0, "l", "codice"),
    ("RW","col14"): ("RW1", 360.0, 20.0, "l", "codice"),
    ("RW","col29_ivafe"): ("RW1", 74.0, -55.7, "r", "euro"),
    ("RW","col30"): ("RW1", 146.0, -55.7, "r", "euro"),
    # Quadro RM (ancora RM31 @ x=106.8 y=455.0), pag.4
    ("RM","r1_tipo"): ("RM31", 26.2, -5.0, "l", "codice"),
    ("RM","r1_stato"): ("RM31", 63.2, -5.0, "l", "codice"),
    ("RM","r1_reddito"): ("RM31", 167.8, -7.2, "r", "euro"),
    ("RM","r1_aliquota"): ("RM31", 193.2, -5.0, "l", "codice"),
    ("RM","r1_imposta"): ("RM31", 444.3, -6.7, "r", "euro"),
    # Quadro RT — pag.6 (RT11 corrispettivi/costi, RT13, RT52 minus/plus)
    ("RT","RT11_1"): ("RT11", 264.8, -1.0, "r", "euro"),
    ("RT","RT11_2"): ("RT11", 441.4, -1.0, "r", "euro"),
    ("RT","RT13"): ("RT13", 441.4, -1.0, "r", "euro"),
    ("RT","RT52_1_minus"): ("RT52", 329.7, -0.5, "r", "euro"),
    ("RT","RT52_2_plus"): ("RT52", 441.3, 0.1, "r", "euro"),
    # Quadro RT — pag.7 (RT72 imponibile, RT73 imposta, RT102 minus residua)
    ("RT","RT72"): ("RT72", 441.4, -0.2, "r", "euro"),
    ("RT","RT73_imposta"): ("RT73", 441.4, 0.0, "r", "euro"),
    ("RT","RT74"): ("RT74", 441.4, 0.0, "r", "euro"),
    ("RT","RT102_5"): ("RT102", 441.4, 0.0, "r", "euro"),
    # Quadro RL (ancora RL1, pag.2) — non calibrato (assente in questo caso)
    ("RL","RL2_reddito"): ("RL1", 0.0, 0.0, "r", "euro"),
}


def verifica_copertura(field_map, valori):
    orfani = [k for k in valori if k not in field_map]
    if orfani:
        raise CoperturaError(f"Valori senza casella nel modulo: {orfani}")


def _disegna_filigrana(c, size):
    """Filigrana diagonale grigio chiaro 'FAC-SIMILE — NON PER L'INVIO'."""
    w, h = size
    c.saveState()
    c.setFillGray(0.8)
    c.setFont("Helvetica-Bold", 42)
    c.translate(w/2, h/2)
    c.rotate(45)
    c.drawCentredString(0, 0, "FAC-SIMILE — NON PER L'INVIO")
    c.restoreState()


def _overlay_pagina(items, size, filigrana=False):
    """items: lista di (x, y, align, testo) in coordinate PDF assolute."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    if filigrana:
        _disegna_filigrana(c, size)
    c.setFont("Helvetica", 8)
    for x, y, align, testo in items:
        if align == "r": c.drawRightString(x, y, testo)
        else: c.drawString(x, y, testo)
    c.save(); buf.seek(0)
    return PdfReader(buf).pages[0]


def _wrap(testo, larghezza, font="Helvetica", size=8):
    """Spezza il testo in righe che stanno entro `larghezza` punti."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    righe, riga = [], ""
    for parola in str(testo).split():
        prova = (riga + " " + parola).strip()
        if stringWidth(prova, font, size) <= larghezza:
            riga = prova
        else:
            if riga: righe.append(riga)
            riga = parola
    if riga: righe.append(riga)
    return righe or [""]


# Motivazione normativa di singole decisioni interpretative, indicizzata per
# (chiave risposta, valore). Stampata nel registro accanto alla decisione.
MOTIVAZIONI = {
    ("cod_stato_dividendi", "211"): (
        "Motivazione: la col.2 di RM31 indica lo Stato di PRODUZIONE del reddito "
        "= residenza dell'emittente, non la borsa di quotazione, la natura di ADR "
        "ne' il prefisso ISIN. Caso tipico: ADR di societa' costituita in un Paese "
        "a fiscalita' privilegiata (es. Isole Cayman), verificabile dai documenti "
        "societari (es. Form 20-F SEC). Il codice 069 (USA) e' ESCLUSO: il prefisso 'US' e' "
        "dell'ADR e nel rendiconto non risulta alcuna ritenuta USA (reddito non di "
        "fonte statunitense). Alternativa solo teorica: 016 (Cina), unicamente "
        "affermando la direzione effettiva in Cina. Black-list: le Cayman sono a "
        "fiscalita' privilegiata, ma la tassazione integrale IRPEF NON si applica "
        "perche' i titoli sono negoziati in mercato regolamentato (NYSE) e la "
        "partecipazione e' non qualificata (art. 27 c.4 DPR 600/1973 e art. 68 c.4 "
        "TUIR): resta l'imposta sostitutiva del 26%."
    ),
}


def _pagine_audit(valori, res, ans, pf2_path):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 27*cm
    c.setFont("Helvetica-Bold", 12); c.drawString(2*cm, y, "AUDIT TRAIL — valore → origine → norma"); y -= 1*cm
    c.setFont("Helvetica", 7)
    for (quadro, campo), voce in sorted(valori.items()):
        if y < 2*cm: c.showPage(); y = 27*cm; c.setFont("Helvetica", 7)
        c.drawString(2*cm, y, f"{quadro} {campo} = {voce['valore']}  ⟵ {voce['origine']}  [{voce['norma']}]")
        y -= 0.5*cm
    c.showPage()

    # ---------- REGISTRO DECISIONI ----------
    larghezza = 17*cm  # larghezza utile (A4 ~21cm meno margini 2cm)
    y = 27*cm
    c.setFont("Helvetica-Bold", 12); c.drawString(2*cm, y, "REGISTRO DECISIONI"); y -= 1*cm

    def riga_blocco(prefisso, testo, font="Helvetica", size=8, indent=0):
        nonlocal y
        for i, linea in enumerate(_wrap(testo, larghezza - indent, font, size)):
            if y < 2*cm:
                c.showPage(); y = 27*cm
                c.setFont("Helvetica-Bold", 12); c.drawString(2*cm, y, "REGISTRO DECISIONI (segue)"); y -= 1*cm
            c.setFont(font, size)
            testo_riga = (prefisso + linea) if i == 0 else linea
            c.drawString(2*cm + indent, y, testo_riga)
            y -= 0.5*cm
        y -= 0.15*cm

    # note di decisione/regola prodotte dal motore
    for nota in res.get("note", []):
        riga_blocco("• ", nota)

    # scelte interpretative dell'utente, con eventuale motivazione normativa
    for chiave in ("cod_stato_dividendi", "includi_forex_auto", "quota"):
        if chiave in ans.asked:
            valore = str(ans.asked[chiave])
            riga_blocco("", f"decisione: {chiave} = {valore}", font="Helvetica-Bold")
            motivazione = MOTIVAZIONI.get((chiave, valore))
            if motivazione:
                riga_blocco("", motivazione, size=7, indent=0.6*cm)

    if y < 2.5*cm:
        c.showPage(); y = 27*cm
    c.setFont("Helvetica", 8)
    c.drawString(2*cm, y, f"PF2 SHA-256: {sha256_file(pf2_path)}")

    c.save(); buf.seek(0)
    return PdfReader(buf).pages


def componi_pdf(pf2_path, res, ans, out_path, filigrana=False):
    valori = valori_da_risultati(res, ans)
    verifica_copertura(FIELD_MAP, valori)
    ancore = carica_ancore(pf2_path)
    reader = PdfReader(pf2_path)
    writer = PdfWriter()
    # Raggruppa i valori per pagina del PF2 risolvendo l'ancora-rigo di ogni
    # campo: un quadro (es. RT) puo' occupare piu' pagine.
    per_pagina = {}
    for (quadro, campo), voce in valori.items():
        ancora_rigo, dx, dy, align, _tipo = FIELD_MAP[(quadro, campo)]
        anc = ancore[ancora_rigo]
        per_pagina.setdefault(anc["pagina"], []).append(
            (anc["x"] + dx, anc["y"] + dy, align, voce["valore"]))
    for pagina in sorted(per_pagina):
        base = reader.pages[pagina]
        over = _overlay_pagina(per_pagina[pagina],
                               (float(base.mediabox.width), float(base.mediabox.height)),
                               filigrana=filigrana)
        base.merge_page(over)
        writer.add_page(base)
    for p in _pagine_audit(valori, res, ans, pf2_path):
        writer.add_page(p)
    with open(out_path, "wb") as f:
        writer.write(f)


def main():
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("pf2")
    ap.add_argument("--answers"); ap.add_argument("--out", default="quadri_compilati.pdf")
    ap.add_argument("--filigrana", action="store_true")
    a = ap.parse_args()
    ibkr = G.IBKR(a.csv)
    data = json.load(open(a.answers, encoding="utf-8")) if a.answers else None
    ans = G.Answers(data, interactive=(data is None))
    res = G.genera(ibkr, ans)   # solleva ReconciliationError se non quadra
    componi_pdf(a.pf2, res, ans, a.out, filigrana=a.filigrana)
    print(f"[salvato: {a.out}]")


if __name__ == "__main__":
    main()
