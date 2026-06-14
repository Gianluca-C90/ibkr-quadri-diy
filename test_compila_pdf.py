import unittest
import os
from decimal import Decimal
import compila_pdf as C
import genera_quadri as G

PF2 = "PF2_modello_2026_agg 13 05 2026.pdf"


def _res_esempio():
    class FakeIBKR:
        period = "Gennaio 1, 2025 - Dicembre 31, 2025"
        vpn_iniziale = Decimal("500")
        vpn_finale = Decimal("100000")
        instruments = {}
        realized = [
            {"symbol":"WRT","asset_class":"Warrant","prof":Decimal("1000"),"loss":Decimal("0"),"tot":Decimal("1000")},
            {"symbol":"EUR.USD","asset_class":"Forex","prof":Decimal("0.50"),"loss":Decimal("-2.00"),"tot":Decimal("-1.50")},
        ]
        realized_tot_all = Decimal("998.50")
        dividendi = [{"ccy":"USD","descr":"ADRX","lordo_native":Decimal("1000")}]
        dividendi_eur_tot = Decimal("1000")
        interessi_eur_tot = Decimal("0")
    ans = G.Answers(data={"quota":"100","cod_stato_broker":"040","giorni_ivafe":"365",
        "anno_imposta":"2025","includi_forex_auto":"no","cod_stato_dividendi":"211"},
        interactive=False)
    return G.genera(FakeIBKR(), ans), ans


class TestHelper(unittest.TestCase):
    def test_formatta_importo_euro_intero(self):
        self.assertEqual(C.formatta_valore(Decimal("12"), "euro"), "12")
        self.assertEqual(C.formatta_valore(Decimal("0"), "euro"), "0")
        self.assertEqual(C.formatta_valore(Decimal("1234"), "euro"), "1.234")  # migliaia con punto

    def test_formatta_codice_stringa(self):
        self.assertEqual(C.formatta_valore("040", "codice"), "040")
        self.assertEqual(C.formatta_valore(4, "codice"), "4")

    def test_sha256_file_stabile(self):
        import tempfile, os
        p = os.path.join(tempfile.gettempdir(), "x.bin")
        open(p, "wb").write(b"abc")
        self.assertEqual(C.sha256_file(p),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


class TestValori(unittest.TestCase):
    def test_rw_e_rm_presenti_con_origine(self):
        res, ans = _res_esempio()
        v = C.valori_da_risultati(res, ans)
        self.assertEqual(v[("RW","col4")]["valore"], "040")
        self.assertEqual(v[("RW","col8")]["valore"], "100.000")
        self.assertEqual(v[("RM","r1_stato")]["valore"], "211")
        self.assertEqual(v[("RM","r1_imposta")]["valore"], "260")
        self.assertEqual(v[("RT","RT72")]["valore"], "1.000")
        # ogni voce ha una norma citata (audit)
        for k, voce in v.items():
            self.assertTrue(voce["norma"], f"manca norma per {k}")


class TestAncore(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(PF2), "PF2 assente")
    def test_ancore_pagine_attese(self):
        anc = C.carica_ancore(PF2)
        self.assertEqual(anc["RW1"]["pagina"], 9)
        self.assertEqual(anc["RM31"]["pagina"], 4)
        self.assertEqual(anc["RT11"]["pagina"], 6)
        self.assertEqual(anc["RL1"]["pagina"], 2)
        # coordinate plausibili dentro A4 (595x842)
        for k, a in anc.items():
            self.assertTrue(0 <= a["x"] <= 595 and 0 <= a["y"] <= 842, k)


class TestCopertura(unittest.TestCase):
    def test_ogni_valore_ha_un_campo_mappato(self):
        res, ans = _res_esempio()
        valori = C.valori_da_risultati(res, ans)
        # non deve sollevare: copertura completa per i campi presenti
        C.verifica_copertura(C.FIELD_MAP, valori)

    def test_valore_senza_campo_solleva(self):
        valori = {("RW", "campo_inesistente"): {"valore":"1","origine":"x","norma":"y"}}
        with self.assertRaises(C.CoperturaError):
            C.verifica_copertura(C.FIELD_MAP, valori)


class TestComponi(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(PF2), "PF2 assente")
    def test_genera_pdf_con_pagine_attese(self):
        import tempfile
        res, ans = _res_esempio()
        out = os.path.join(tempfile.gettempdir(), "quadri_test.pdf")
        C.componi_pdf(PF2, res, ans, out, filigrana=False)
        self.assertTrue(os.path.exists(out))
        from pypdf import PdfReader
        r = PdfReader(out)
        # RW + RM + RT (RL assente) + >=1 pagina audit + 1 registro
        self.assertGreaterEqual(len(r.pages), 5)
        testo_audit = (r.pages[-1].extract_text() or "") + (r.pages[-2].extract_text() or "")
        self.assertIn("AUDIT", testo_audit.upper() + "REGISTRO")


class TestRegistroDecisioni(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(PF2), "PF2 assente")
    def test_registro_elenca_decisioni(self):
        res, ans = _res_esempio()
        valori = C.valori_da_risultati(res, ans)
        pagine = C._pagine_audit(valori, res, ans, PF2)
        testo = "".join((p.extract_text() or "") for p in pagine)
        # decisione Stato Cayman per i dividendi
        self.assertIn("211", testo)
        # nota di esclusione auto-FX
        self.assertTrue("auto-FX" in testo or "forex" in testo.lower(),
                        "manca riferimento forex/auto-FX nel registro")
        # impronta del modello
        self.assertIn("SHA-256", testo)

    @unittest.skipUnless(os.path.exists(PF2), "PF2 assente")
    def test_registro_motiva_codice_stato_211(self):
        # La decisione Stato 211 deve portare la motivazione normativa:
        # esclusione del 069 e norme sul black-list/mercato regolamentato.
        res, ans = _res_esempio()
        valori = C.valori_da_risultati(res, ans)
        pagine = C._pagine_audit(valori, res, ans, PF2)
        testo = "".join((p.extract_text() or "") for p in pagine)
        self.assertIn("069", testo)              # USA escluso
        self.assertIn("600/1973", testo)         # art. 27 c.4 DPR 600/1973
        self.assertIn("regolamentato", testo)    # carve-out titoli quotati


class TestFiligrana(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(PF2), "PF2 assente")
    def test_filigrana_presente(self):
        import tempfile
        res, ans = _res_esempio()
        out = os.path.join(tempfile.gettempdir(), "quadri_filigrana.pdf")
        C.componi_pdf(PF2, res, ans, out, filigrana=True)
        from pypdf import PdfReader
        r = PdfReader(out)
        self.assertIn("FAC-SIMILE", r.pages[0].extract_text() or "")

    @unittest.skipUnless(os.path.exists(PF2), "PF2 assente")
    def test_filigrana_assente_default(self):
        import tempfile
        res, ans = _res_esempio()
        out = os.path.join(tempfile.gettempdir(), "quadri_no_filigrana.pdf")
        C.componi_pdf(PF2, res, ans, out, filigrana=False)
        from pypdf import PdfReader
        r = PdfReader(out)
        self.assertNotIn("FAC-SIMILE", r.pages[0].extract_text() or "")


if __name__ == "__main__":
    unittest.main()
