# Quadri IBKR — Generatore di quadri fiscali da report Interactive Brokers

Legge l'**Activity Statement (CSV)** di Interactive Brokers e genera i quadri
**RW / RM / RT / RL** del Modello Redditi PF, con calcoli esatti (`Decimal`),
riconciliazione contro i totali IBKR, e — opzionale — la **sovrastampa dei valori
sul modulo PDF ufficiale** dell'Agenzia delle Entrate, con audit trail e registro
delle decisioni.

> ## ⚠️ AVVERTENZA — leggere prima di usare
> Progetto **gratuito e a scopo esclusivamente di studio/dimostrativo**. È uno
> **strumento di supporto**, **non** una dichiarazione ufficiale e **non**
> sostituisce un commercialista. La **responsabilità fiscale resta del
> contribuente** (firmi tu, rispondi tu all'Agenzia delle Entrate). Le scelte
> marcate `[DECISIONE]` sono **interpretazioni** da validare. Il software è
> fornito "così com'è", **senza alcuna garanzia e senza alcuna responsabilità
> dell'autore**. **Verifica sempre i risultati** e falli validare da un
> professionista. → Leggi le avvertenze legali complete in **[DISCLAIMER.md](DISCLAIMER.md)**.

---

## Cosa fa (e cosa non fa)

La correttezza si divide in tre livelli — è importante capirli:

| Livello | Cosa garantisce | Certezza |
|---|---|---|
| **A. Parsing + aritmetica** | i numeri sono estratti e calcolati esattamente dal file | **dimostrabile** (test + riconciliazione che blocca) |
| **B. Classificazione fiscale** | il valore va nel quadro/casella giusto | **tracciata**: regola esplicita + fonte citata; sui casi ambigui *chiede o blocca*, non indovina |
| **C. Completezza dei dati** | hai dichiarato *tutti* i conti/attività estere | **resta a te**: il software vede solo il file che gli dai |

Quando un dato non è ricavabile o una scelta è interpretativa, il programma
**chiede** (o **blocca**): non inventa mai una classificazione fiscale.

## Requisiti

- **Python 3.9+**
- Per il solo calcolo (`genera_quadri.py`): **nessuna dipendenza** (solo stdlib).
- Per la sovrastampa sul PDF (`compila_pdf.py`): `pip install -r requirements.txt`
  (`pypdf`, `reportlab`).
- Il **modulo PDF ufficiale** (Fascicolo 2 "PF2") va **scaricato da te** dal sito
  dell'Agenzia delle Entrate — non è incluso nel repo. Le coordinate di
  sovrastampa sono calibrate sul PF2 *Redditi PF 2026*; se l'AdE cambia il layout
  il programma se ne accorge (errore esplicito sull'àncora non trovata).

## Uso

**1) Calcolo dei quadri (a video + file di testo):**

```bash
# interattivo: il programma chiede le info esterne
python genera_quadri.py "TUOCONTO_2025.csv"

# non interattivo: risposte da file JSON (copia risposte.esempio.json)
python genera_quadri.py "TUOCONTO_2025.csv" --answers risposte_TUOCONTO.json
```

**2) Sovrastampa sul modulo PDF ufficiale:**

```bash
python compila_pdf.py "TUOCONTO_2025.csv" "PF2_modello_2026...pdf" \
    --answers risposte_TUOCONTO.json --out quadri_compilati.pdf
# opzione --filigrana per stampare "FAC-SIMILE — NON PER L'INVIO" sulle pagine
```

Il PDF prodotto contiene i quadri compilati + le pagine di **audit trail**
(ogni valore → dato di origine → norma) e di **registro decisioni** (con le
motivazioni normative delle scelte interpretative).

## Garanzie di calcolo

- Solo `Decimal`; arrotondamento all'euro (`ROUND_HALF_UP`) solo sui valori finali.
- **Riconciliazione che BLOCCA**: se la somma dei realizzi non coincide col totale
  IBKR (tolleranza 0,01) il programma si ferma (exit 2), non produce quadri errati.
- IVAFE rapportata ai giorni reali dell'anno (366 nei bisestili) e soglia minima 12 €.
- Metodo allineato alle istruzioni AdE 2026 (TUIR artt. 18/44/67/68; DL 201/2011;
  art. 27 c.4 DPR 600/1973) — riferimenti nel registro decisioni del PDF generato.

## Test

```bash
python -m unittest -v
```

Suite a zero dipendenze (`unittest`): motore (RW/RM/RT/RL, IVAFE, riconciliazione,
ETF armonizzati, dividendi capitale/CFD, forex) e sovrastampa PDF.

## Limiti noti

- Le coordinate PDF sono calibrate su una specifica versione del PF2; con un
  layout diverso vanno ritarate (il programma segnala l'àncora mancante).
- Dividendi da CFD in **più valute diverse contemporaneamente**: la ripartizione
  in EUR non è ricavabile dal solo totale → il programma **segnala e non sposta**
  automaticamente (gestione manuale).
- Casi B/C (interpretazione e completezza) restano responsabilità dell'utente.

## ❤️ Ti è stato utile? Offrimi un caffè

Questo progetto è gratuito. Se ti ha fatto risparmiare tempo, puoi sostenerlo con
una piccola donazione:

**👉 https://ko-fi.com/camarcagianluca**

## Licenza

**PolyForm Noncommercial License 1.0.0** — vedi [`LICENSE`](LICENSE).
Uso libero per scopi **non commerciali** (studio, uso personale, no-profit),
mantenendo l'attribuzione all'autore. Nessuna garanzia, nessuna responsabilità
(vedi [`DISCLAIMER.md`](DISCLAIMER.md)).

© 2026 Gianluca Camarca.
