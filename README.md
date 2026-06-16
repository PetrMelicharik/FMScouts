# FMScouts

Scouting aplikace — data automaticky stahována ze Sofascore 2x týdně přes GitHub Actions.

## Struktura repozitáře

```
fmscouts/
├── .github/
│   └── workflows/
│       └── scrape.yml      ← GitHub Actions cron job
├── data/
│   └── players.json        ← generováno automaticky (commitováno Botem)
├── index.html              ← webová aplikace
├── scraper.py              ← scraper (spouštěn přes GitHub Actions)
├── players.xlsx            ← tvůj seznam hráčů
├── requirements.txt
├── vercel.json
└── README.md
```

## Setup (jednou)

### 1. GitHub repozitář

1. Vytvoř účet na [github.com](https://github.com)
2. Vytvoř nový repozitář (např. `fmscouts`) — **PUBLIC**
3. Nahraj všechny soubory z tohoto zipu

### 2. Přidej players.xlsx

Nahraj svůj `players.xlsx` do kořene repozitáře.

### 3. Povol GitHub Actions

- Jdi na záložku **Actions** ve svém repozitáři
- Klikni "I understand my workflows, go ahead and enable them"

### 4. Vercel deployment

1. Jdi na [vercel.com](https://vercel.com) a přihlas se přes GitHub
2. Klikni "New Project" → vyber svůj repozitář `fmscouts`
3. Framework Preset: **Other**
4. Klikni Deploy

Aplikace je live! Každý commit (včetně automatických updates dat) spustí nový deploy.

### 5. První spuštění scraperu

- Jdi na záložku **Actions** → "Scrape Sofascore" → "Run workflow"
- Scraper stáhne data pro všechny hráče (může trvat 30-60 minut)
- Po dokončení se data automaticky commitnou a Vercel nasadí aktualizaci

## Automatické aktualizace

GitHub Actions spouští scraper:
- **Každé úterý ve 3:00 UTC** (5:00 CET)
- **Každý pátek ve 3:00 UTC** (5:00 CET)

Nebo kdykoli ručně přes záložku Actions → "Run workflow".

## Scraper — anti-detection

- Náhodné pauzy 4–9 sekund mezi requesty
- Delší pauza (~35s) každých 12 requestů
- Rotace User-Agentů (Chrome, Firefox, Safari)
- Rotace Accept-Language (CS, EN, SK, PL)
- Rotace Referer URL
- Retry logika při výpadcích
- Resume: přeskočí hráče aktualizované dnes

## Funkce aplikace

| Záložka | Popis |
|---------|-------|
| Hráči | Přehled všech hráčů, filtry, řazení |
| Tým týdne | Top 20 dle průměrného ratingu |
| Forma | Hráči nejlepší v posledních 3 zápasech |
| Srovnání | Porovnání 2 hráčů vedle sebe |

## Ruční aktualizace dat

Pokud chceš aktualizovat okamžitě:
1. GitHub → Actions → Scrape Sofascore → Run workflow
2. Počkej na dokončení (~30-60 min)
3. Vercel automaticky nasadí aktualizovaná data
