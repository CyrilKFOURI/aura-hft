# Registre des affirmations (CLAIMS)

> Chaque chiffre public d'AURA-HFT doit apparaître ici avec sa preuve. Audit initial : 2026-10-20 (étape P0).
>
> **Statuts :**
> ✅ **Prouvé** — artefact reproductible dans le repo ·
> 🟡 **Simulé** — observé en simulation, mais sans assertion stricte ou sans environnement reproductible ·
> 🔴 **Non prouvé** — aucune preuve dans le repo ; retiré ou reformulé ·
> 🧪 **Expérimental** — module testé seul, non intégré au pipeline de référence

## Architecture de référence

Pipeline de référence : `rtl/top/aura_hft_top.sv`, **mono-horloge 156,25 MHz (période 6,4 ns)**.
La variante double horloge 156,25 ↔ 312,5 MHz (`rtl/top/aura_hft_dual_clock_top.sv`) est 🧪 tant qu'aucun rapport Vivado ne prouve qu'elle ferme le timing.

## Constat transverse (bloquant pour tout ✅)

- ~~Les bancs RTL ne se lancent pas sur un environnement neuf.~~ Corrigé en P1 : `Dockerfile` + `Makefile` + CI GitHub Actions. Les bancs exigent cocotb 2.x et Verilator ≥ 5.036.
- Aucun rapport Vivado (timing, ressources, puissance) ni bitstream dans le repo.
- ~~Aucune donnée de marché réelle.~~ P2 : golden model validé sur 20 M messages NASDAQ réels contre MeatPy. P3 : le **RTL** rejoué sur ces données réelles diverge (capacité du carnet insuffisante) — voir C1.

→ À l'issue de P0, **aucun chiffre RTL n'est ✅**. Ils le deviendront en P1 (CI), P3 (co-sim données réelles) et P5 (Vivado).

## Registre

| # | Affirmation (avant audit) | Où | Statut | Preuve / constat | Action |
| :-- | :-- | :-- | :-- | :-- | :-- |
| C1 | Tick-to-trade **49 cycles = 313,6 ns** → 57 (carnet P4) → **27 cycles = 172,8 ns** (OBI sans division + risque 2 étages, P4) → **29 cycles = 185,6 ns** (mémoires registrées, P5a) | README, dashboard, vidéo | 🟡 latence simulée ; carnet ✅ sur données réelles | `tb_tick_to_trade_top.py` mesure `last_tick_to_trade_cycles` mais n'asserte que `< 60` ; un seul scénario synthétique. **P3 : sur données NASDAQ réelles, le carnet RTL est faux** (BBO divergent dès le message 1 244 à 9 408, puis 83 à 97 % des messages) à cause de la capacité 16 niveaux / 2 048 ordres — [rapport](../reports/rtl_real_cosim_01302019.md) | **P4 :** nouveau carnet pleine profondeur → **0 divergence** sur 215 674 messages réels (AAPL, MSFT, TSLA). Latence mesurée sur le scénario synthétique : 57 cycles. **P4 suite :** décision OBI par multiplication croisée (2 cycles) au lieu du diviseur 32 cycles, risque pipeliné 2 étages → **27 cycles** mesurés de bout en bout (scénario synthétique). **P5a :** mémoires du carnet à lecture registrée (BRAM/URAM) → **29 cycles** (scénario synthétique), toujours 0 divergence sur AAPL/MSFT/TSLA. La vidéo promo v1 affiche encore 49 cycles |
| C2 | **< 280 ns** (parser spéculatif + cœur 312,5 MHz) | README | 🔴 | Combinaison jamais simulée de bout en bout ; parser spéculatif et dual-clock non intégrés au top de référence | Retiré |
| C3 | Horloges 156,25 ↔ 312,5 MHz, **WNS ≥ +0,12 ns** | README (résumé, badge) | 🔴 | Aucun rapport de timing | Retiré ; dual-clock marqué 🧪 |
| C4 | Tableau ressources (14 820 LUT, 18 340 FF, 32 BRAM, 16 DSP, **WNS +0,142 ns, TIMING MET**) | README | 🔴 | Aucun rapport Vivado correspondant dans le repo | Remplacé par « à produire en P5 ». **P5a :** estimation Yosys (pas Vivado, sans timing) du carnet seul : 47 760 LUT + 16 384 LUTRAM, 20 788 FF, 376 RAMB36 (> 144 dispo → URAM requis), 35 DSP — [rapport](../reports/yosys_estimate_lob_engine.md) |
| C5 | Risque pré-trade **1 cycle (6,4 ns)** → **2 étages** (P4) | README | 🟡 | Structure en registres observée ; notionnel 64 bits combinatoire non validé en timing | Formulé « 1 cycle en simulation, timing à valider (P5) » |
| C6 | Coupe-circuit PnL **1 cycle**, « strict compliance SEC 15c3-5 / MiFID II RTS 6 » | README | 🟡 / 🔴 | Cycle : simulé. Conformité : aucune revue réglementaire possible | « Contrôles inspirés de 15c3-5 / RTS 6 » |
| C7 | « In-silicon wire-to-wire latency tracking » | README | 🔴 | Aucune carte ; module `latency_metrology.sv` testé en simulation | « Métrologie PTP simulée ; mesure silicium en P7 » |
| C8 | Arbitrage cross-exchange déclenché en **3,2 ns** | README | 🧪 | Module non instancié dans le top de référence ; 3,2 ns suppose 312,5 MHz non prouvé | « 1 cycle en simulation, module expérimental » |
| C9 | Driver UIO **< 50 ns** d'accès registre sur Cortex-A53 | README | 🔴 | Aucune carte | Retiré (à mesurer en P7) |
| C10 | **37 suites, 100 % passées, 0 divergence** | README, badge | ✅ (P1, 2026-10-20) | Non reproductible (voir constat). Comptage réel : 35 fichiers Python de test/banc dans `sim/tests`, ~140 fonctions de test sim + server ; seules 11 (golden model) vérifiées passantes le 2026-10-20. **Après P1 :** `make test` dans Docker (Verilator 5.040, cocotb 2.0.1) → 18 bancs RTL + 11 golden + 7 API + 1 driver Python + suite C++ driver, tous verts ; il a fallu corriger 2 bancs (accès à un tableau packed, API cocotb 2). Stimuli synthétiques uniquement | Badge CI après le premier run GitHub |
| C11 | Golden model validé « sur un extrait d'une journée réelle NASDAQ ITCH 5.0 » | PLAN Tranche 0 | ✅ extrait (P2, 2026-10-20) | Avant P2 : messages synthétiques uniquement. **Après P2 :** 20 M messages réels NASDAQ du 30/01/2019 (03:04 → 09:36, ouverture incluse), 6 symboles, 786 626 contrôles BBO + profondeur, **0 divergence** vs MeatPy — [rapport](../reports/golden_vs_meatpy_01302019_first20M.md). Bug `U` (ordre fantôme) trouvé et corrigé | Journée complète à faire |
| C12 | Parser **≤ 6 cycles** | README | 🟡 | Banc `tb_itch_parser.py`, environnement non reproductible | Conservé « simulé » |
| C13 | Avellaneda-Stoikov « exact 3-cycle » | README | 🧪 | Non instancié dans le top de référence | Marqué expérimental |
| C14 | Parser spéculatif 1 cycle | README | 🧪 | Non instancié dans le top de référence | Marqué expérimental |
| C15 | Iceberg / TWAP, résilience MoldUDP64 | README | 🧪 | Non instanciés dans le top de référence | Marqués expérimentaux |
| C16 | FCS CRC-32 « 0 cycle » cut-through | README | 🟡 | Combinatoire 64 bits : timing non validé | « Simulé » |
| C18 | Pipeline « robuste » : gaps, doublons, trames corrompues | — | ✅ partiel (P3b, 2026-10-21) | `test_fault_injection.py` : 10 scénarios vs golden model, 10/10 après **4 bugs RTL corrigés** (doublons réappliqués, blocage parser sur trame tronquée / bloc de longueur 0, 741/1 800 requêtes perdues en rafale sans frein, trames non UDP analysées). 5 000 vraies trames IEX HIST réemballant 23 123 messages NASDAQ réels : 0 divergence. **FCS non vérifié** dans `aura_hft_top` (xfail strict). Couverture ligne 61 % / branche 66 % / toggle 32 % — [rapport](../reports/robustness_p3b.md) | FCS + couverture ≥ 90 % à faire |
| C19 | Risque : aucun ordre hors limites, aucun ordre sous kill-switch | — | ✅ prouvé (P3b) avec abstraction | P1–P6 prouvés par k-induction (yosys `sat -tempinduct`, k = 3, **pas** SymbiYosys), multiplicateur abstrait ; 8 mutants réfutés ; bug de débordement 64 bits du notionnel cumulé trouvé et corrigé. Mêmes assertions sous Verilator `--assert` dans 2 bancs | Ajouter en CI |
| C17 | Valeurs par défaut `313.6` / `49 cyc` codées en dur dans le dashboard | `client/src/components/AnalyticsView.tsx`, `Launcher.tsx` | ✅ corrigé (P6, 2026-10-21) | Plus aucune valeur par défaut : « — » sans donnée. Latence FPGA lue depuis `GET /api/latency` (29 cycles, marquée « simulated »), latences CPU mesurées depuis `reports/software_latency/`, provenance affichée. Le runner de démo n’invente plus de gigue (49 ± 1 cycles aléatoires) et l’état AXI-Lite n’invente plus de télémétrie (`total_orders_approved: 128` → 0, champ `telemetry_source`) | — |
| C20 | Rentabilité de la stratégie OBI | (nouveau, P8) | ✅ mesuré (P8, 2026-10-21) | Backtest sur ITCH réel 30/01/2019 (04:00–10:11), règle Q1.31 du RTL, fill par priorité FIFO, frais Nasdaq/SEC/FINRA : PnL net négatif dans les 36 configurations seuil × horizon × latence ; seuil 0.4 / 10 s / 1 µs en séance régulière : 544 trades, −0,038 $/action, IC 95 % [−2 442 ; −1 565] $ — [rapport](../research/obi_backtest.md) | Ne revendiquer aucun edge ; une demi-journée seulement |
| C21 | Chemin logiciel C++ de référence : même logique que le RTL, latence CPU | (nouveau, P6) | ✅ mesuré (P6, 2026-10-21) | `software/ref_pipeline` bit-exact vs modèle doré sur 426 961 événements réels (AAPL/MSFT/TSLA/QQQ, 20 M messages du 30/01/2019, 0 divergence). **Mesuré sur le portable** (Core Ultra 7 155H, Docker/WSL2, 1 thread épinglé, message déjà en mémoire, sans réseau) : p50 126–189 ns, p99 0,5–1,6 µs, p99,9 1,6–8,8 µs ; débit 183–242 M msg/s (un symbole suivi) — [rapport](../reports/software_vs_fpga.md) | Ne pas comparer à 185,6 ns sans rappeler que le FPGA est simulé et que le CPU exclut la pile réseau |

## Modules : intégration dans le pipeline de référence

| Module | Dans `aura_hft_top.sv` | Statut |
| :-- | :-- | :-- |
| FCS checker, latency metrology, ingress, LOB, quant (OBI/micro-price), AXI-Lite, PnL breaker, risk + OUCH | oui | 🟡 simulé |
| `speculative_itch_parser` | oui (via `ingress_pipeline_top`) | 🟡 simulé |
| `avellaneda_stoikov_engine` | non | 🧪 |
| `cross_exchange_*` | non | 🧪 |
| `iceberg_twap_engine` | non | 🧪 |
| `moldudp64_resilience_engine` | non | 🧪 |
| `multi_symbol_router` / `multi_ticker_pipeline_top` | top séparé | 🧪 |
| `aura_hft_dual_clock_top` (156,25 ↔ 312,5 MHz) | top séparé | 🧪 |

**Depuis P4 :** tous les modules 🧪 sont dans `rtl/experimental/` ; `aura_hft_top` est le seul top de référence, et les scripts Vivado le synthétisent (le script bitstream synthétisait auparavant le top double horloge expérimental).
