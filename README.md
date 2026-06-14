<div align="center">

# 🧾 ibkr-quadri-diy

### Genera i quadri fiscali **RW · RM · RT** del Modello Redditi PF dal report di **Interactive Brokers** — e sovrastampali sul **modulo ufficiale** dell'Agenzia delle Entrate.

[![Licenza](https://img.shields.io/badge/licenza-PolyForm%20Noncommercial%201.0.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Test](https://img.shields.io/badge/test-33%20passing-brightgreen)](#-test)
[![Dona](https://img.shields.io/badge/%E2%98%95%20Ko--fi-Sostieni%20il%20progetto-ff5e5b)](https://ko-fi.com/camarcagianluca)

</div>

---

<div align="center">

## ☕ Ti ha fatto risparmiare tempo (o la parcella del commercialista)?

**Questo progetto è gratuito e fatto col cuore. Se ti è stato utile, offrimi un caffè 👇**

<a href="https://ko-fi.com/camarcagianluca">
  <img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Sostieni su Ko-fi" />
</a>

### 👉 **[ko-fi.com/camarcagianluca](https://ko-fi.com/camarcagianluca)** 👈

*Anche 1 € aiuta a tenere vivo il progetto e a lavorare alla V2 con interfaccia grafica.*

</div>

---

> ## ⚠️ AVVERTENZA — leggere prima di usare
> Progetto **gratuito e a scopo esclusivamente di studio/dimostrativo**. È uno
> **strumento di supporto**, **non** una dichiarazione ufficiale e **non**
> sostituisce un commercialista. La **responsabilità fiscale resta del
> contribuente** (firmi tu, rispondi tu all'Agenzia delle Entrate). Le scelte
> marcate `[DECISIONE]` sono **interpretazioni** da validare. Il software è
> fornito "così com'è", **senza alcuna garanzia né responsabilità dell'autore**.
> **Verifica sempre i risultati** e falli validare da un professionista.
> → Avvertenze legali complete in **[DISCLAIMER.md](DISCLAIMER.md)**.

## ✨ Cosa fa

Legge l'**Activity Statement (CSV)** di Interactive Brokers e:

1. **Calcola** i quadri **RW** (monitoraggio + IVAFE), **RM** (redditi di capitale
   esteri), **RT** (plusvalenze) e **RL**, con aritmetica esatta (`Decimal`) e
   **riconciliazione** contro i totali IBKR.
2. **Sovrastampa** i valori sul **modulo PDF ufficiale** (Fascicolo 2 "PF2"),
   aggiungendo pagine di **audit trail** (ogni valore → dato di origine → norma)
   e di **registro decisioni** (con le motivazioni normative delle scelte).

### Le tre "certezze" — è importante capirle

| Livello | Cosa garantisce | Certezza |
|---|---|---|
| **A. Parsing + aritmetica** | i numeri sono estratti e calcolati esattamente dal file | **dimostrabile** (test + riconciliazione che blocca) |
| **B. Classificazione fiscale** | il valore va nel quadro/casella giusto | **tracciata**: regola esplicita + fonte citata; sui casi ambigui *chiede o blocca*, non indovina |
| **C. Completezza dei dati** | hai dichiarato *tutti* i conti/attività estere | **resta a te**: il software vede solo il file che gli dai |

Quando un dato non è ricavabile o una scelta è interpretativa, il programma
**chiede** (o **blocca**): non inventa mai una classificazione fiscale.

## 📦 Requisiti

- **Python 3.9+**
- Solo calcolo (`genera_quadri.py`): **nessuna dipendenza** (solo stdlib).
- Sovrastampa PDF (`compila_pdf.py`): `pip install -r requirements.txt` (`pypdf`, `reportlab`).
- Il **modulo PDF ufficiale** (Fascicolo 2 "PF2") va **scaricato da te** dal sito
  dell'[Agenzia delle Entrate](https://www.agenziaentrate.gov.it/) — non è incluso
  nel repo. Le coordinate sono calibrate sul PF2 *Redditi PF 2026*.

## 🚀 Uso

**1) Calcolo dei quadri (a video + file di testo):**

```bash
# interattivo: il programma chiede le info esterne
python genera_quadri.py "conto_2025.csv"

# non interattivo: risposte da file JSON (copia risposte.esempio.json)
python genera_quadri.py "conto_2025.csv" --answers risposte_TUOCONTO.json
```

**2) Sovrastampa sul modulo PDF ufficiale:**

```bash
python compila_pdf.py "conto_2025.csv" "PF2_modello_2026...pdf" \
    --answers risposte_TUOCONTO.json --out quadri_compilati.pdf
# opzione --filigrana per stampare "FAC-SIMILE — NON PER L'INVIO" sulle pagine
```

## 🔒 Garanzie di calcolo

- Solo `Decimal`; arrotondamento all'euro (`ROUND_HALF_UP`) solo sui valori finali.
- **Riconciliazione che BLOCCA**: se la somma dei realizzi non coincide col totale
  IBKR (tolleranza 0,01) il programma si ferma (exit 2), non produce quadri errati.
- IVAFE rapportata ai giorni reali dell'anno (366 nei bisestili) e soglia minima 12 €.
- Metodo allineato alle istruzioni AdE 2026 (TUIR artt. 18/44/67/68; DL 201/2011;
  art. 27 c.4 DPR 600/1973) — riferimenti nel registro decisioni del PDF.

## 🧪 Test

```bash
python -m unittest -v
```

Suite a zero dipendenze (`unittest`): motore (RW/RM/RT/RL, IVAFE, riconciliazione,
ETF armonizzati, dividendi di capitale/CFD, forex) e sovrastampa PDF. **33 test.**

## ⚠️ Limiti noti

- Le coordinate PDF sono calibrate su una specifica versione del PF2; con un
  layout diverso vanno ritarate (il programma segnala l'àncora mancante).
- Dividendi da CFD in **più valute diverse contemporaneamente**: la ripartizione
  in EUR non è ricavabile dal solo totale → il programma **segnala e non sposta**
  automaticamente (gestione manuale).
- I livelli B/C (interpretazione e completezza) restano responsabilità dell'utente.

---

<div align="center">

## ❤️ Sostieni il progetto

Se ti è stato utile, una piccola donazione fa la differenza:

<a href="https://ko-fi.com/camarcagianluca">
  <img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Sostieni su Ko-fi" />
</a>

### 👉 **[ko-fi.com/camarcagianluca](https://ko-fi.com/camarcagianluca)**

</div>

---

## 📄 Licenza

**PolyForm Noncommercial License 1.0.0** — vedi [`LICENSE`](LICENSE).
Uso libero per scopi **non commerciali** (studio, uso personale, no-profit),
mantenendo l'attribuzione all'autore. Nessuna garanzia, nessuna responsabilità —
vedi [`DISCLAIMER.md`](DISCLAIMER.md).

© 2026 **Gianluca Camarca**
