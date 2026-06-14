#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generatore Quadri Fiscali (RW / RM / RL / RT) da Activity Statement IBKR.

- Input : il file CSV "Rendiconto di attivita'" di Interactive Brokers.
- Chiede allo user solo le informazioni non ricavabili dal report.
- Calcoli ESATTI (Decimal), arrotondamento all'euro solo sui valori finali,
  riconciliazione contro i totali IBKR, nessuna inferenza fiscale implicita.

Uso:
    python genera_quadri.py "conto_2025.csv"
    python genera_quadri.py "...csv" --answers risposte.json   # non interattivo

Vedi GENERATORE_QUADRI_PSEUDOCODICE.md per la specifica.
ATTENZIONE: strumento di supporto. Le scelte fiscali marcate [DECISIONE] vanno
validate da un commercialista. I numeri DERIVATI sono certi dal file.
"""

import argparse, csv, json, re, sys
from decimal import Decimal, ROUND_HALF_UP, getcontext

getcontext().prec = 40

# --------------------------- costanti -------------------------------------
ALIQ_SOST  = Decimal("0.26")    # 26% RM e RT
ALIQ_IVAFE = Decimal("0.002")   # 2 per mille
GG_ANNO    = Decimal("365")     # default storico; vedi giorni_nell_anno()
D0 = Decimal("0")


class ReconciliationError(Exception):
    """La somma dei realizzi distribuiti non coincide col totale IBKR.

    E' un errore FATALE: significa che il programma ha estratto o classificato
    male i dati. Non si prosegue con quadri potenzialmente sbagliati.
    """


def giorni_nell_anno(anno):
    """Giorni dell'anno solare: 366 se bisestile, 365 altrimenti.

    Serve come divisore IVAFE: l'imposta va rapportata ai giorni di possesso
    sul totale dei giorni dell'anno d'imposta (366 nei bisestili 2024, 2028...).
    """
    bisestile = (anno % 4 == 0) and (anno % 100 != 0 or anno % 400 == 0)
    return 366 if bisestile else 365


def anno_da_periodo(period, default=None):
    """Estrae l'anno d'imposta dall'ultimo numero a 4 cifre del periodo IBKR."""
    anni = re.findall(r"(\d{4})", period or "")
    return int(anni[-1]) if anni else default

def D(x):
    if x is None: return D0
    s = str(x).strip().replace("−", "-")
    if s == "" or s == "--": return D0
    return Decimal(s)

def euro(x):
    """Arrotonda all'unita' di euro, commerciale (ROUND_HALF_UP)."""
    return D(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

def fmt(x):
    return f"{D(x):.2f}"

# --------------------------- parsing IBKR ----------------------------------
class IBKR:
    def __init__(self, path):
        self.rows = list(csv.reader(open(path, encoding="utf-8-sig")))
        self.account = {}
        self.broker = ""
        self.period = ""
        self.base_ccy = "EUR"
        self.vpn_iniziale = D0
        self.vpn_finale = D0
        self.instruments = {}     # symbol -> dict(asset_class, isin, tipo, descr)
        self.realized = []        # dict(symbol, asset_class, prof, loss, tot)
        self.realized_tot_all = D0
        self.dividendi = []       # dict(descr, ccy, lordo_native, eur)
        self.dividendi_eur_tot = D0
        self.interessi_eur_tot = D0
        self._parse()

    def _sec(self, name):
        return [r for r in self.rows if r and r[0] == name]

    def _parse(self):
        for r in self._sec("Statement"):
            if len(r) >= 4 and r[1] == "Data":
                if r[2] == "BrokerName": self.broker = r[3]
                if r[2] == "Period":     self.period = r[3]
        for r in self._sec("Dati del conto"):
            if len(r) >= 4 and r[1] == "Data":
                self.account[r[2]] = r[3]
        self.base_ccy = self.account.get("Valuta di base", "EUR")

        for r in self._sec("Variazione del VPN"):
            if r[1] == "Data" and len(r) >= 4:
                if r[2] == "Valore iniziale": self.vpn_iniziale = D(r[3])
                if r[2] == "Valore finale":   self.vpn_finale = D(r[3])

        # strumenti: due layout di header (Warrant vs Azioni). Mappo per posizione.
        cur_hdr = None
        for r in self._sec("Informazioni sullo strumento finanziario"):
            if r[1] == "Header":
                cur_hdr = r
            elif r[1] == "Data" and cur_hdr:
                rec = dict(zip(cur_hdr, r))
                sym = rec.get("Simbolo", "")
                self.instruments[sym] = {
                    "asset_class": rec.get("Tipo di attivo", ""),
                    "isin": rec.get("ID titolo", ""),
                    "tipo": rec.get("Tipo", "") or rec.get("Emittente", ""),
                    "descr": rec.get("Descrizione", ""),
                    "mercato": rec.get("Mercato finanziario", ""),
                }

        # realizzati: header riga 45. Colonne per nome.
        hdr = None
        for r in self._sec("Sommario profitti e perdite Realizzati e Non realizzati"):
            if r[1] == "Header":
                hdr = r; continue
            if r[1] != "Data" or not hdr: continue
            rec = dict(zip(hdr, r))
            tipo = rec.get("Tipo di attivo", "")
            sym = rec.get("Simbolo", "")
            if tipo in ("", "Totale"):  # salto i subtotali per-classe
                if rec.get("Tipo di attivo") == "Totale (tutti i prodotti)":
                    self.realized_tot_all = D(rec.get("Realizzato Totale"))
                continue
            if rec.get("Tipo di attivo") == "Totale (tutti i prodotti)":
                self.realized_tot_all = D(rec.get("Realizzato Totale")); continue
            prof = D(rec.get("Realizzato Profitto S/T")) + D(rec.get("Realizzato Profitto L/T"))
            loss = D(rec.get("Realizzato Perdita S/T")) + D(rec.get("Realizzato Perdita L/T"))
            self.realized.append({
                "symbol": sym, "asset_class": tipo,
                "prof": prof, "loss": loss,           # loss e' negativa o zero
                "tot": D(rec.get("Realizzato Totale")),
            })

        # dividendi
        hdr = None
        for r in self._sec("Dividendi"):
            if r[1] == "Header": hdr = r; continue
            if r[1] != "Data": continue
            rec = dict(zip(hdr, r))
            if rec.get("Valuta") == "Totale": continue
            if rec.get("Valuta") == "Totale in EUR":
                self.dividendi_eur_tot = D(rec.get("Importo")); continue
            descr = rec.get("Descrizione", "")
            sym = descr.split("(")[0].strip()   # "TICKER(ISIN) Dividendo..." -> "TICKER"
            self.dividendi.append({
                "ccy": rec.get("Valuta"), "data": rec.get("Data"),
                "descr": descr, "lordo_native": D(rec.get("Importo")),
                "symbol": sym,
                "asset_class": self.instruments.get(sym, {}).get("asset_class", ""),
            })
        # interessi (sezione assente in questo report -> 0)
        for r in self._sec("Interessi"):
            if r[1] == "Data" and r[2] == "Totale in EUR":
                self.interessi_eur_tot = D(r[-1])

# --------------------------- questionario ----------------------------------
class Answers:
    """Raccoglie le risposte: da file JSON (--answers) o interattive."""
    def __init__(self, data=None, interactive=True):
        self.data = data or {}
        self.interactive = interactive
        self.asked = {}

    def get(self, key, prompt, default=None, kind="str", decision=False):
        if key in self.data:
            v = self.data[key]
        elif self.interactive:
            tag = " [DECISIONE fiscale]" if decision else ""
            d = f" [{default}]" if default is not None else ""
            raw = input(f"{prompt}{tag}{d}: ").strip()
            v = raw if raw else default
        else:
            v = default
        self.asked[key] = v
        if v is None: return None
        if kind == "dec": return D(v)
        if kind == "int": return int(v)
        if kind == "bool": return str(v).lower() in ("1","true","si","s","y","yes")
        return v

# --------------------------- calcolo quadri --------------------------------
def collegamento(has_rl, has_rm, has_rt):
    if has_rt and (has_rm or has_rl): return 4
    if has_rt: return 3
    if has_rm: return 2
    if has_rl: return 1
    return 5

def genera(ibkr, ans):
    out = {"note": [], "derivati": {}, "decisioni": {}}

    # ---------- parametri (derivati dal file + conferme utente) ----------
    quota = ans.get("quota", "Quota di possesso % (100 unico, 50 cointestato)",
                     default="100", kind="dec")
    cf = ans.get("cf", "Codice Fiscale contribuente", default="")
    cod_broker = ans.get("cod_stato_broker",
                         "Codice Stato estero del broker", default="040")
    anno = ans.get("anno_imposta", "Anno d'imposta",
                   default=str(anno_da_periodo(ibkr.period, 2025)), kind="int")
    gg_anno = Decimal(giorni_nell_anno(anno))
    giorni = ans.get("giorni_ivafe", "Giorni IVAFE (apertura conto nell'anno)",
                     default=str(giorni_nell_anno(anno)), kind="dec")
    val_iniz = ans.get("valore_iniziale", "Valore iniziale conto EUR",
                       default=str(ibkr.vpn_iniziale), kind="dec")
    val_fin = ans.get("valore_finale", "Valore finale conto EUR (31/12)",
                      default=str(ibkr.vpn_finale), kind="dec")
    ecc_prec = ans.get("ivafe_ecc_prec", "IVAFE eccedenza dich. precedente",
                       default="0", kind="dec")
    ecc_util = ans.get("ivafe_ecc_util", "IVAFE eccedenza utilizzata",
                       default="0", kind="dec")
    acconti = ans.get("ivafe_acconti", "IVAFE acconti versati",
                      default="0", kind="dec")
    minus_preg = ans.get("minus_pregresse",
                         "Minusvalenze pregresse utilizzabili (EUR)",
                         default="0", kind="dec")
    includi_forex = ans.get("includi_forex_auto",
        "Includere il P/L da auto-conversione FX (AFx) nel quadro RT?",
        default="no", kind="bool", decision=True)

    # ---------- classificazione realizzi ----------
    rt_prof = D0; rt_loss = D0
    rm_b = D0; rl_red = D0
    classi_rt = ("Warrant", "Azioni", "Future", "CFD")
    forex_prof = D0; forex_loss = D0
    for rec in ibkr.realized:
        cls = rec["asset_class"]
        sym = rec["symbol"]
        if cls == "Forex":
            forex_prof += rec["prof"]; forex_loss += rec["loss"]
            continue
        if cls in ("ETF", "Fondo"):
            armon = ans.get(f"etf_armon_{sym}",
                f"ETF {sym}: armonizzato (UCITS)? si->RM(B) / no->RL",
                default="si", kind="bool", decision=True)
            if armon:
                if rec["tot"] > 0: rm_b += rec["tot"]
                else: rt_prof += rec["prof"]; rt_loss += rec["loss"]
            else:
                rl_red += rec["tot"]
            continue
        if cls in classi_rt:
            rt_prof += rec["prof"]; rt_loss += rec["loss"]
        else:
            out["note"].append(f"[RESIDUO] realizzo non classificato: {cls} {sym}")

    if includi_forex:
        rt_prof += forex_prof; rt_loss += forex_loss
    else:
        out["note"].append(
            f"[DECISIONE] P/L auto-FX ESCLUSO dal RT: profitti {fmt(forex_prof)} / "
            f"perdite {fmt(forex_loss)} (netto {fmt(forex_prof+forex_loss)}). "
            "Auto-conversione valutaria da regolamento titoli: in genere NON "
            "imponibile come reddito diverso. Confermare col commercialista.")

    # ---------- dividendi: split CFD vs capitale ----------
    # I dividendi da strumenti CFD NON sono redditi di capitale (no RM): vanno
    # come redditi diversi in RT11.1 (metodo del corso). Gli altri -> RM (H).
    cfd_native = sum((d.get("lordo_native", D0) for d in ibkr.dividendi
                      if d.get("asset_class") == "CFD"), D0)
    tot_native = sum((d.get("lordo_native", D0) for d in ibkr.dividendi), D0)
    cfd_div_eur = D0
    cap_div_eur = ibkr.dividendi_eur_tot
    if cfd_native != 0:
        valute = {d.get("ccy") for d in ibkr.dividendi}
        if len(valute) == 1 and tot_native != 0:
            rate = ibkr.dividendi_eur_tot / tot_native     # cambio implicito (valuta unica)
            cfd_div_eur = rate * cfd_native
            cap_div_eur = ibkr.dividendi_eur_tot - cfd_div_eur
            out["note"].append(
                f"[CFD] Dividendi da CFD {fmt(cfd_div_eur)} EUR spostati in RT11.1 "
                "(redditi diversi, non redditi di capitale) come da metodo del corso. "
                f"Dividendi di capitale residui in RM: {fmt(cap_div_eur)} EUR.")
        else:
            out["note"].append(
                "[BLOCCO] Dividendi da CFD presenti ma in piu' valute: la ripartizione "
                "EUR cap/CFD non e' ricavabile dal solo totale. Gestire manualmente; "
                "qui NON spostati automaticamente in RT.")

    # ---------- dividendi di capitale -> RM (H) ----------
    rm_div_rows = []
    if ibkr.dividendi and cap_div_eur > 0:
        cod_stato_div = ans.get("cod_stato_dividendi",
            "Codice Stato estero erogante i dividendi (es. 069=USA, 072=Cina)",
            default=None, decision=True)
        if cod_stato_div is None:
            out["note"].append("[BLOCCO] Manca il Codice Stato dei dividendi: "
                               "riga RM dividendi NON generata.")
        else:
            red = cap_div_eur
            rm_div_rows.append({"tipo": "H", "stato": cod_stato_div,
                                "reddito": red, "imposta": red * ALIQ_SOST})

    rm_int_rows = []
    if ibkr.interessi_eur_tot > 0:
        cod_stato_int = ans.get("cod_stato_interessi",
            "Codice Stato interessi", default=cod_broker)
        red = ibkr.interessi_eur_tot
        rm_int_rows.append({"tipo": "G", "stato": cod_stato_int,
                            "reddito": red, "imposta": red * ALIQ_SOST})

    # ---------- RW ----------
    quota_frac = quota / 100
    ivafe = val_fin * (giorni / gg_anno) * quota_frac * ALIQ_IVAFE
    has_rm = bool(rm_div_rows or rm_int_rows or rm_b)
    has_rl = rl_red != 0
    has_rt = ((rt_prof - rt_loss) + cfd_div_eur) != 0
    rw = {
        "col1": 1, "col3": 20, "col4": cod_broker, "col5": euro(quota),
        "col6": 1, "col7": euro(val_iniz), "col8": euro(val_fin),
        "col10": euro(giorni), "col14": collegamento(has_rl, has_rm, has_rt),
        "col29_ivafe": euro(ivafe), "col30": euro(ivafe),
    }
    saldo = euro(ivafe) - ecc_prec + ecc_util - acconti
    rw["rw6_debito"] = euro(saldo) if saldo >= 0 else D0
    rw["rw6_credito"] = euro(-saldo) if saldo < 0 else D0
    # Soglia minima: l'IVAFE non si versa se l'imposta a debito non supera 12 EUR
    # (istruzioni Redditi PF, Quadro RW6: "non versata se l'importo ... non supera 12 euro").
    rw["da_versare"] = rw["rw6_debito"]
    if 0 < rw["rw6_debito"] <= 12:
        rw["da_versare"] = D0
        out["note"].append(
            f"[REGOLA UFFICIALE] IVAFE a debito {rw['rw6_debito']} EUR <= 12 EUR: "
            "imposta NON dovuta (soglia minima, istruzioni Quadro RW6). Da versare: 0. "
            "Il Quadro RW di monitoraggio va comunque compilato.")

    # ---------- RT ----------
    corrispettivi = rt_prof
    costi = -rt_loss                    # loss e' <=0 -> costi positivi
    etf_gia_tassati = rl_red + rm_b
    # i dividendi da CFD si sommano ai corrispettivi RT (redditi diversi); restano
    # FUORI dalla riconciliazione realizzi (non sono P/L realizzati).
    rt11_1 = corrispettivi + cfd_div_eur - etf_gia_tassati
    rt11_2 = costi
    netto = rt11_1 - rt11_2
    plus = netto if netto > 0 else D0
    minus = -netto if netto < 0 else D0
    rt13 = min(minus_preg, plus)
    rt72 = plus - rt13
    rt73 = (rt72 if rt72 > 0 else D0) * ALIQ_SOST
    rt = {
        "RT11_1": euro(rt11_1), "RT11_2": euro(rt11_2),
        "RT52_2_plus": euro(plus), "RT52_1_minus": euro(minus),
        "RT13": euro(rt13), "RT72": euro(rt72),
        "RT73_imposta": euro(rt73), "RT74": euro(rt73),
        "RT102_5": euro(minus),
        "_raw_netto": netto,
    }

    # ---------- riconciliazione ----------
    distribuito = (corrispettivi - costi) + rm_b + rl_red
    if not includi_forex:
        distribuito += (forex_prof + forex_loss)   # rimesso per quadrare col totale IBKR
    diff = (ibkr.realized_tot_all - distribuito)
    if abs(diff) > Decimal("0.01"):
        raise ReconciliationError(
            f"Riconciliazione realizzi non quadra: "
            f"IBKR={fmt(ibkr.realized_tot_all)} vs "
            f"distribuito={fmt(distribuito)} (diff {fmt(diff)}). "
            "Quadri NON generati: i dati estratti/classificati non tornano.")

    out.update({"rw": rw, "rm_div": rm_div_rows, "rm_int": rm_int_rows,
                "rm_b": euro(rm_b), "rl": euro(rl_red) if has_rl else None, "rt": rt,
                "forex": {"prof": forex_prof, "loss": forex_loss,
                          "incluso": includi_forex}})
    return out

# --------------------------- report ----------------------------------------
def render(ibkr, r, ans):
    L = []
    a = L.append
    a("="*70)
    a("QUADRI FISCALI - generati da report IBKR")
    a(f"Conto: {ibkr.account.get('Conto','?')}  Intestatario: {ibkr.account.get('Nome','?')}")
    a(f"Broker: {ibkr.broker}")
    a(f"Periodo: {ibkr.period}   Valuta base: {ibkr.base_ccy}")
    a("="*70)

    rw = r["rw"]
    a("\n## QUADRO RW (monitoraggio + IVAFE)")
    a(f"  col1  Codice titolo possesso .... {rw['col1']}")
    a(f"  col3  Codice individuazione bene . {rw['col3']}")
    a(f"  col4  Codice Stato estero ........ {rw['col4']}")
    a(f"  col5  Quota di possesso .......... {rw['col5']}")
    a(f"  col6  Criterio valore ............ {rw['col6']} (mercato)")
    a(f"  col7  Valore iniziale ............ {rw['col7']} EUR")
    a(f"  col8  Valore finale .............. {rw['col8']} EUR")
    a(f"  col10 Giorni IVAFE ............... {rw['col10']}")
    a(f"  col14 Collegamento reddituale .... {rw['col14']}")
    a(f"  col29 IVAFE ...................... {rw['col29_ivafe']} EUR")
    a(f"  col30 IVAFE dovuta ............... {rw['col30']} EUR")
    a(f"  RW6   Imposta a debito ........... {rw['rw6_debito']} EUR")
    a(f"        Imposta a credito .......... {rw['rw6_credito']} EUR")
    a(f"        IVAFE da versare ........... {rw['da_versare']} EUR")

    a("\n## QUADRO RM (Sez. V - imposta sostitutiva 26%)")
    if r["rm_div"] or r["rm_int"]:
        for row in r["rm_div"] + r["rm_int"]:
            a(f"  RM31  Tipo {row['tipo']}  Stato {row['stato']}  "
              f"Reddito {euro(row['reddito'])} EUR  -> Imposta {euro(row['imposta'])} EUR")
    if r["rm_b"] > 0:
        a(f"  RM31  Tipo B (ETF armon.)  Reddito {r['rm_b']} EUR -> Imposta {euro(r['rm_b']*ALIQ_SOST)} EUR")
    if not (r["rm_div"] or r["rm_int"] or r["rm_b"] > 0):
        a("  (nessun reddito di capitale RM)")

    a("\n## QUADRO RL")
    a(f"  {'RL2 reddito '+str(r['rl'])+' EUR' if r['rl'] else '(nessun reddito RL)'}")

    rt = r["rt"]
    a("\n## QUADRO RT (Sez. II - plusvalenze 26%)")
    a(f"  RT11.1 Totale corrispettivi ...... {rt['RT11_1']} EUR")
    a(f"  RT11.2 Totale costi .............. {rt['RT11_2']} EUR")
    a(f"  RT52.2 Plusvalenza ............... {rt['RT52_2_plus']} EUR")
    a(f"  RT52.1 Minusvalenza .............. {rt['RT52_1_minus']} EUR")
    a(f"  RT13   Minus. pregresse usate .... {rt['RT13']} EUR")
    a(f"  RT72   Differenza imponibile ..... {rt['RT72']} EUR")
    a(f"  RT73   Imposta sostitutiva ....... {rt['RT73_imposta']} EUR")
    a(f"  RT102.5 Minus. residua (riporto) . {rt['RT102_5']} EUR")

    if r["note"]:
        a("\n## NOTE / DECISIONI / BLOCCHI")
        for n in r["note"]:
            a("  - " + n)

    a("\n## RISPOSTE UTILIZZATE")
    for k, v in ans.asked.items():
        a(f"  {k} = {v}")
    return "\n".join(L)

# --------------------------- main ------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--answers")
    ap.add_argument("--out", default="quadri_output.txt")
    args = ap.parse_args()

    ibkr = IBKR(args.csv)
    data = json.load(open(args.answers, encoding="utf-8")) if args.answers else None
    ans = Answers(data, interactive=(data is None))
    try:
        res = genera(ibkr, ans)
    except ReconciliationError as e:
        sys.stderr.write(f"\n[ERRORE FATALE] {e}\n")
        sys.exit(2)
    report = render(ibkr, res, ans)
    print(report)
    open(args.out, "w", encoding="utf-8").write(report)
    print(f"\n[salvato: {args.out}]")

if __name__ == "__main__":
    main()
