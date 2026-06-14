#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite di test per genera_quadri.py — STRATO A (parsing + aritmetica).

Obiettivo: rendere DIMOSTRABILE la correttezza matematica e bloccare le
regressioni. Solo libreria standard (unittest), come il programma.

Esecuzione:
    python -m unittest test_quadri -v
"""

import unittest
from decimal import Decimal

import genera_quadri as G


# --------------------------------------------------------------------------
# Stub: un oggetto "IBKR-like" con i soli attributi che genera() legge.
# Permette di testare il motore di calcolo senza un file CSV.
# --------------------------------------------------------------------------
class FakeIBKR:
    def __init__(self, **kw):
        self.account = {}
        self.broker = ""
        self.period = kw.get("period", "Gennaio 1, 2025 - Dicembre 31, 2025")
        self.base_ccy = "EUR"
        self.vpn_iniziale = Decimal(str(kw.get("vpn_iniziale", "0")))
        self.vpn_finale = Decimal(str(kw.get("vpn_finale", "0")))
        self.instruments = kw.get("instruments", {})
        self.realized = kw.get("realized", [])
        self.realized_tot_all = Decimal(str(kw.get("realized_tot_all", "0")))
        self.dividendi = kw.get("dividendi", [])
        self.dividendi_eur_tot = Decimal(str(kw.get("dividendi_eur_tot", "0")))
        self.interessi_eur_tot = Decimal(str(kw.get("interessi_eur_tot", "0")))


def realizzo(symbol, cls, prof="0", loss="0", tot=None):
    p = Decimal(prof)
    l = Decimal(loss)
    return {
        "symbol": symbol, "asset_class": cls,
        "prof": p, "loss": l,
        "tot": Decimal(tot) if tot is not None else (p + l),
    }


def answers(**kw):
    # interactive=False -> usa i default quando la chiave non e' nel dict
    return G.Answers(data={k: str(v) for k, v in kw.items()}, interactive=False)


# ==========================================================================
# BUG 1 (RED): la riconciliazione deve BLOCCARE, non solo annotare.
# ==========================================================================
class TestRiconciliazioneBlocca(unittest.TestCase):
    def test_riconciliazione_non_quadra_solleva_errore(self):
        # realizzo warrant +1.17, ma il "totale IBKR" e' dichiarato 99.00:
        # i conti NON quadrano -> il programma deve fermarsi, non proseguire.
        ibkr = FakeIBKR(
            vpn_iniziale="183", vpn_finale="1162",
            realized=[realizzo("GME WS", "Warrant", prof="1.17")],
            realized_tot_all="99.00",   # incoerente di proposito
        )
        with self.assertRaises(G.ReconciliationError):
            G.genera(ibkr, answers(quota="100", includi_forex_auto="no"))

    def test_riconciliazione_quadra_non_solleva(self):
        ibkr = FakeIBKR(
            vpn_iniziale="183", vpn_finale="1162",
            realized=[realizzo("GME WS", "Warrant", prof="1.17")],
            realized_tot_all="1.17",
        )
        # non deve sollevare
        G.genera(ibkr, answers(quota="100", includi_forex_auto="no"))


# ==========================================================================
# BUG 2 (RED): l'IVAFE in anno bisestile deve rapportarsi a 366 giorni.
# ==========================================================================
class TestIvafeAnnoBisestile(unittest.TestCase):
    def test_anno_bisestile_usa_366_giorni(self):
        # 2024 e' bisestile. Possesso 183 gg su 366 = mezzo anno esatto.
        # IVAFE = 1.000.000 * (183/366) * 100% * 0,002 = 1000,00 -> 1000
        ibkr = FakeIBKR(
            period="Gennaio 1, 2024 - Dicembre 31, 2024",
            vpn_iniziale="0", vpn_finale="1000000",
            realized=[], realized_tot_all="0",
        )
        r = G.genera(ibkr, answers(
            quota="100", giorni_ivafe="183", anno_imposta="2024",
            includi_forex_auto="no"))
        self.assertEqual(r["rw"]["col29_ivafe"], Decimal("1000"))


# ==========================================================================
# CARATTERIZZAZIONE: blinda un caso di esempio end-to-end (dati fittizi).
# Se un domani un calcolo cambia, questi test diventano rossi.
# ==========================================================================
class TestCasoEsempio(unittest.TestCase):
    def setUp(self):
        self.ibkr = FakeIBKR(
            period="Gennaio 1, 2025 - Dicembre 31, 2025",
            vpn_iniziale="500", vpn_finale="100000",
            realized=[
                realizzo("WRT", "Warrant", prof="1000"),
                realizzo("EUR.USD", "Forex", prof="0.50", loss="-2.00", tot="-1.50"),
            ],
            realized_tot_all="998.50",   # 1000 + (-1.50)
            dividendi=[{"ccy": "USD", "descr": "ADRX", "lordo_native": Decimal("1000")}],
            dividendi_eur_tot="1000",
        )
        self.ans = answers(
            quota="100", cod_stato_broker="040", giorni_ivafe="365",
            anno_imposta="2025", includi_forex_auto="no",
            cod_stato_dividendi="211")
        self.r = G.genera(self.ibkr, self.ans)

    def test_ivafe_calcolata(self):
        # 100000 * 365/365 * 100% * 0,002 = 200
        self.assertEqual(self.r["rw"]["col29_ivafe"], Decimal("200"))

    def test_ivafe_da_versare_sopra_soglia(self):
        self.assertEqual(self.r["rw"]["da_versare"], Decimal("200"))

    def test_collegamento_4_piu_quadri(self):
        # RM (dividendi) + RT (warrant) -> codice 4
        self.assertEqual(self.r["rw"]["col14"], 4)

    def test_rm_dividendi(self):
        self.assertEqual(len(self.r["rm_div"]), 1)
        riga = self.r["rm_div"][0]
        self.assertEqual(riga["tipo"], "H")
        self.assertEqual(riga["stato"], "211")
        self.assertEqual(G.euro(riga["reddito"]), Decimal("1000"))
        self.assertEqual(G.euro(riga["imposta"]), Decimal("260"))

    def test_rt_plusvalenza(self):
        self.assertEqual(self.r["rt"]["RT72"], Decimal("1000"))
        self.assertEqual(self.r["rt"]["RT73_imposta"], Decimal("260"))

    def test_forex_escluso_dal_rt(self):
        self.assertFalse(self.r["forex"]["incluso"])

    def test_riconciliazione_quadra(self):
        # se non quadrasse, setUp avrebbe gia' sollevato ReconciliationError
        self.assertTrue(True)


# ==========================================================================
# FUNZIONI PURE: arrotondamento, parsing, mappa collegamento.
# ==========================================================================
class TestFunzioniPure(unittest.TestCase):
    def test_euro_arrotonda_half_up(self):
        self.assertEqual(G.euro("0.50"), Decimal("1"))    # commerciale: 0,5 -> 1
        self.assertEqual(G.euro("0.49"), Decimal("0"))
        self.assertEqual(G.euro("2.3245"), Decimal("2"))
        self.assertEqual(G.euro("12.40"), Decimal("12"))

    def test_D_gestisce_meno_unicode_e_vuoti(self):
        self.assertEqual(G.D("−5.00"), Decimal("-5"))  # meno tipografico
        self.assertEqual(G.D("--"), Decimal("0"))
        self.assertEqual(G.D(""), Decimal("0"))
        self.assertEqual(G.D(None), Decimal("0"))

    def test_collegamento_tutte_le_combinazioni(self):
        self.assertEqual(G.collegamento(False, False, False), 5)
        self.assertEqual(G.collegamento(True, False, False), 1)   # solo RL
        self.assertEqual(G.collegamento(False, True, False), 2)   # solo RM
        self.assertEqual(G.collegamento(False, False, True), 3)   # solo RT
        self.assertEqual(G.collegamento(False, True, True), 4)    # RT + RM
        self.assertEqual(G.collegamento(True, True, True), 4)     # tre quadri

    def test_giorni_nell_anno_bisestili(self):
        self.assertEqual(G.giorni_nell_anno(2024), 366)
        self.assertEqual(G.giorni_nell_anno(2025), 365)
        self.assertEqual(G.giorni_nell_anno(2000), 366)  # divisibile per 400
        self.assertEqual(G.giorni_nell_anno(1900), 365)  # secolo non bisestile

    def test_anno_da_periodo(self):
        self.assertEqual(
            G.anno_da_periodo("Gennaio 1, 2025 - Dicembre 31, 2025"), 2025)
        self.assertEqual(G.anno_da_periodo("", 2030), 2030)


# ==========================================================================
# INVARIANTI: proprieta' che devono valere su QUALSIASI input valido.
# ==========================================================================
class TestInvarianti(unittest.TestCase):
    def test_imposta_sostitutiva_e_26pct_della_base(self):
        # per vari imponibili RT, l'imposta = 26% (arrotondata) della base
        for plus in ["0", "1", "100", "1000.50", "38461.54"]:
            ibkr = FakeIBKR(
                realized=[realizzo("X", "Azioni", prof=plus)],
                realized_tot_all=plus)
            r = G.genera(ibkr, answers(quota="100", anno_imposta="2025",
                                       includi_forex_auto="no"))
            base = r["rt"]["RT72"]
            attesa = G.euro(base * G.ALIQ_SOST)
            self.assertEqual(r["rt"]["RT73_imposta"], attesa,
                             f"base={base}")

    def test_ivafe_sotto_12_non_si_versa_ma_si_dichiara(self):
        # qualsiasi valore finale che produce IVAFE <= 12 -> da_versare 0
        ibkr = FakeIBKR(vpn_finale="5000", realized_tot_all="0")
        r = G.genera(ibkr, answers(quota="100", giorni_ivafe="365",
                                   anno_imposta="2025", includi_forex_auto="no"))
        # 5000 * 0,002 = 10 -> <=12
        self.assertEqual(r["rw"]["col29_ivafe"], Decimal("10"))
        self.assertEqual(r["rw"]["da_versare"], Decimal("0"))

    def test_ivafe_sopra_12_si_versa(self):
        ibkr = FakeIBKR(vpn_finale="100000", realized_tot_all="0")
        r = G.genera(ibkr, answers(quota="100", giorni_ivafe="365",
                                   anno_imposta="2025", includi_forex_auto="no"))
        # 100000 * 0,002 = 200 -> dovuta
        self.assertEqual(r["rw"]["col29_ivafe"], Decimal("200"))
        self.assertEqual(r["rw"]["da_versare"], Decimal("200"))

    def test_minus_pregresse_non_superano_la_plusvalenza(self):
        # minus pregresse enormi: usate solo fino a capienza della plus
        ibkr = FakeIBKR(
            realized=[realizzo("X", "Azioni", prof="100")],
            realized_tot_all="100")
        r = G.genera(ibkr, answers(quota="100", anno_imposta="2025",
                                   minus_pregresse="999999",
                                   includi_forex_auto="no"))
        self.assertEqual(r["rt"]["RT13"], Decimal("100"))   # non oltre la plus
        self.assertEqual(r["rt"]["RT72"], Decimal("0"))     # azzerata
        self.assertEqual(r["rt"]["RT73_imposta"], Decimal("0"))


# ==========================================================================
# DIVIDENDI DA CFD: non sono redditi di capitale -> vanno in RT11.1 (redditi
# diversi), non in RM. Metodo del corso (quadro_rm/quadro_rt).
# ==========================================================================
class TestDividendiCFD(unittest.TestCase):
    def test_dividendi_cfd_in_rt_non_in_rm(self):
        # 50 USD CFD + 50 USD azionari, totale 90 EUR -> rate 0,9:
        # CFD 45 EUR -> RT11.1 ; capitale 45 EUR -> RM.
        ibkr = FakeIBKR(
            dividendi=[
                {"asset_class": "CFD", "ccy": "USD", "lordo_native": Decimal("50"), "descr": "ACFD"},
                {"asset_class": "Azioni", "ccy": "USD", "lordo_native": Decimal("50"), "descr": "BSTK"},
            ],
            dividendi_eur_tot="90",
            realized=[], realized_tot_all="0",
        )
        r = G.genera(ibkr, answers(quota="100", anno_imposta="2025",
                                   includi_forex_auto="no", cod_stato_dividendi="069"))
        self.assertEqual(G.euro(r["rm_div"][0]["reddito"]), Decimal("45"))  # capitale -> RM
        self.assertEqual(r["rt"]["RT11_1"], Decimal("45"))                  # CFD -> RT11.1
        self.assertEqual(r["rt"]["RT72"], Decimal("45"))

    def test_senza_cfd_tutti_i_dividendi_in_rm(self):
        ibkr = FakeIBKR(
            dividendi=[{"asset_class": "Azioni", "ccy": "USD", "lordo_native": Decimal("50"), "descr": "BSTK"}],
            dividendi_eur_tot="45",
            realized=[], realized_tot_all="0",
        )
        r = G.genera(ibkr, answers(quota="100", anno_imposta="2025",
                                   includi_forex_auto="no", cod_stato_dividendi="069"))
        self.assertEqual(G.euro(r["rm_div"][0]["reddito"]), Decimal("45"))
        self.assertEqual(r["rt"]["RT11_1"], Decimal("0"))


if __name__ == "__main__":
    unittest.main()
