# Chemin logiciel de référence vs FPGA (étape P6)

> **À lire avant tout chiffre.** Les latences CPU sont **mesurées** sur le portable de développement (Intel Core Ultra 7 155H, HP Spectre x360 16", Docker sur WSL2, 1 thread épinglé). La latence FPGA est un **nombre de cycles simulés** (Verilator) à 156,25 MHz, pas une mesure sur carte. Les deux périmètres ne sont pas identiques (voir « Ce que la comparaison ne dit pas »).

Date : 2026-10-21 · Données : NASDAQ TotalView-ITCH 5.0, échantillon public du 30/01/2019, 20 000 000 premiers messages (04:00 → ~10:11).

## 1. Ce qui a été construit

`software/ref_pipeline/` : programme C++20 (g++ 13, `-O3 -march=native`), sans dépendance, qui rejoue un fichier ITCH brut (préfixe de longueur 2 octets) avec la même logique que le chemin de référence RTL :

| Étape | RTL | C++ |
| :-- | :-- | :-- |
| Parse ITCH 5.0 A/F/E/C/X/D/U + annuaire `R` | `itch_parser_fsm.sv` | `Pipeline::on_message` (filtre par *stock locate*) |
| Carnet pleine profondeur, top 5 exact | `depth_book.sv` | `std::map` par côté + `unordered_map` des ordres |
| Signal OBI sans division, Q1.31 | `obi_signal.sv` : (Vb−Va)·2³¹ ≥ T·(Vb+Va) | `obi_signal()` en entiers 128 bits (exact) |
| Intention d'ordre | `risk_ouch_top.sv` : achat prioritaire au bid, vente à l'ask, 100 actions | identique |
| Risque pré-trade | `pre_trade_risk.sv` : kill switch, disjoncteur, taille, collar, notionnel, cumul **saturant 65 bits** | `PreTradeRisk` (même ordre de priorité, même saturation) |

Écart assumé : le RTL bloque une intention tant que l'émetteur OUCH est occupé (`tx_busy`, ~12 cycles) ; le chemin logiciel n'a pas de sérialiseur et évalue chaque mise à jour du carnet.

## 2. Validation bit-exacte contre le modèle doré

`software/ref_pipeline/validate.py` compare, événement par événement, la trace C++ à un pipeline Python indépendant (carnet `sim/golden_model`, règle et risque de `research/obi_backtest/model.py`) : horodatage, type, 5 niveaux × 2 côtés (prix, quantité), bits du signal, décision, motif de rejet, notionnel cumulé.

Configuration : seuils ±0,40 (Q1.31 = ±858 993 459), 100 actions, max 1 000 actions, collar 0,50 $, notionnel max 50 000 $, **cumul max 2 M$** (atteint sur données réelles, donc exercé).

| Symbole | Événements carnet | Intentions | Approuvées | Rejet cumul | Divergences |
| :-- | --: | --: | --: | --: | --: |
| AAPL | 125 232 | 72 134 | 123 | 72 011 | **0** |
| MSFT | 58 888 | 25 445 | 189 | 25 256 | **0** |
| TSLA | 31 554 | 16 832 | 67 | 16 765 | **0** |
| QQQ | 210 287 | 92 649 | 123 | 92 526 | **0** |

Total : **426 961 événements, 0 divergence**. Les cas limites non atteints par les données (collar, débordement 64 bits du cumul, seuils exacts, valeurs 32 bits extrêmes) sont couverts par `tests/test_ref_pipeline.cpp`.

## 3. Latence CPU mesurée

Méthode : fichier chargé en mémoire, une passe de chauffe, puis `std::chrono::steady_clock::now()` autour de chaque message qui modifie le carnet du symbole suivi (parse + carnet + OBI + risque). Thread épinglé (`sched_setaffinity`, CPU 2). Coût de deux appels d'horloge consécutifs : 19–20 ns (inclus dans les chiffres, non soustrait). Histogramme HDR log-linéaire (16 sous-intervalles par puissance de 2, erreur relative < 6,25 %) ; percentiles exacts calculés sur l'échantillon trié.

| Symbole | Événements | p50 | p99 | p99,9 | moyenne | max |
| :-- | --: | --: | --: | --: | --: | --: |
| AAPL | 125 232 | 180 ns | 1 056 ns | 3 502 ns | 234 ns | 1,09 ms |
| MSFT | 58 888 | 176 ns | 1 308 ns | 3 244 ns | 225 ns | 149 µs |
| TSLA | 31 554 | 189 ns | 1 609 ns | 8 784 ns | 278 ns | 130 µs |
| QQQ | 210 287 | 126 ns | 524 ns | 1 631 ns | 164 ns | 185 µs |

Répartition (histogramme HDR regroupé) :

| Symbole | < 100 ns | 100–200 ns | 200–500 ns | 0,5–1 µs | 1–5 µs | > 5 µs |
| :-- | --: | --: | --: | --: | --: | --: |
| AAPL | 14,6 % | 49,5 % | 32,0 % | 3,0 % | 1,0 % | 0,07 % |
| MSFT | 25,2 % | 40,0 % | 28,6 % | 4,4 % | 1,8 % | 0,04 % |
| TSLA | 16,5 % | 41,3 % | 35,0 % | 4,8 % | 2,3 % | 0,16 % |
| QQQ | 24,0 % | 52,6 % | 22,3 % | 0,9 % | 0,2 % | 0,02 % |

Débit (sans minuterie par message, meilleure de 2 passes chaudes) : **183 à 242 M messages/s** sur le flux entier, un seul symbole suivi (les messages des autres symboles sont écartés après lecture du *stock locate*, ce qui domine ce chiffre).

Données brutes : `reports/software_latency/<SYMBOLE>.json` (servies par `GET /api/latency`).

## 4. Face au FPGA (simulé)

| | FPGA (`aura_hft_top`) | CPU (ce portable) |
| :-- | :-- | :-- |
| Nature du chiffre | **simulé** (Verilator, scénario synthétique) | **mesuré** (données NASDAQ réelles) |
| Latence | 29 cycles = **185,6 ns**, déterministe | p50 126–189 ns, p99 0,5–1,6 µs, p99,9 1,6–8,8 µs |
| Gigue | 0 cycle en simulation (pas de mesure silicium) | queue longue : max 130 µs – 1,1 ms (préemption, WSL2) |
| Périmètre | AXI-Stream d'entrée → trame OUCH de sortie | message déjà en mémoire → décision de risque |

Lecture honnête : en médiane, le cœur logiciel est du même ordre que le FPGA simulé, **parce que le chemin logiciel mesuré exclut tout le réseau**. L'avantage revendicable du FPGA ici est la **queue** (p99,9 et max) et le déterminisme, pas la médiane.

## 5. Ce que la comparaison ne dit pas

- Côté CPU : ni carte réseau, ni pile noyau/UDP, ni copie vers l'espace utilisateur, ni sérialisation OUCH, ni envoi. Un vrai système CPU ajoute typiquement plusieurs µs (ou ~1–2 µs en contournement noyau) ; **non mesuré ici**.
- Côté FPGA : MAC/PCS 10GbE et SFP+ hors périmètre, aucun chiffre sur carte (étape P7). 29 cycles proviennent d'un scénario synthétique.
- Un seul portable, sous Docker/WSL2, sans isolation de cœur ni réglage du gouverneur : la queue CPU est pessimiste par rapport à un serveur dédié.
- Le carnet C++ (`std::map`) n'est pas optimisé (pas de tableau par prix, pas d'allocateur dédié).

## 6. Flux live crypto (chemin logiciel Python)

`server/live/` s'abonne à un flux L2 public sans authentification (Coinbase Exchange `level2_batch` BTC-USD par défaut, ou Binance `btcusdt@depth20@100ms`), normalise vers un carnet interne, applique la même règle OBI Q1.31 (tailles converties en unités entières de 10⁻⁸) et pousse le résultat au dashboard via `/ws/live`. **Paper uniquement : aucun ordre n'est envoyé.** Client WebSocket écrit sur la bibliothèque standard (asyncio + ssl), aucune dépendance ajoutée.

Essai du 2026-10-21, 30 s par flux, depuis ce portable (Python 3.12 Windows, temps normalisation + carnet + OBI, `time.perf_counter_ns`) :

| Flux | Mises à jour | p50 | p99 | p99,9 |
| :-- | --: | --: | --: | --: |
| Coinbase BTC-USD level2_batch | 461 | 116 µs | 1,1 ms | 63 ms (snapshot initial) |
| Binance BTCUSDT depth20@100ms | 287 | 128 µs | 283 µs | 298 µs |

Ce chemin Python est ~1 000× plus lent que le C++ : il sert à la démonstration live, pas à la comparaison de latence. La stabilité « 24 h sans crash » demandée par P6 **n'a pas été testée**.

## Reproduire

```sh
# image aura-hft-ci, depuis la racine, fichier ITCH dans data/cache/
sh software/ref_pipeline/run_bench.sh data/cache/01302019.NASDAQ_ITCH50.first20000000.itch 20000000 AAPL MSFT TSLA QQQ
```
