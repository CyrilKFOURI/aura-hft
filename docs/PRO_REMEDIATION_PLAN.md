# AURA-HFT — Plan de passage « projet pro »

> Objectif : transformer AURA-HFT d'un portfolio impressionnant *sur le papier* en un système **reproductible, vérifié sur données réelles et défendable en entretien** devant une équipe HFT (Jane Street, Optiver, HRT, Citadel Securities, IMC…).
>
> Règle d'or de ce plan : **aucun chiffre n'est publié sans preuve commitée** (log de test, rapport Vivado, fichier de mesure). Ce qui n'est pas prouvé est marqué *simulé*, *estimé* ou *expérimental*.

---

## 0. Cadre honnête

| On peut atteindre | On ne peut pas atteindre (et ce n'est pas grave) |
| :--- | :--- |
| Pipeline RTL vérifié bit-à-bit contre un modèle de référence sur **des journées NASDAQ réelles** | Être « utilisé en prod » par une firme HFT : il faudrait colocation, connectivité exchange, certification, conformité |
| Timing réel issu de Vivado (Fmax, WNS, ressources) sur la cible KR260, **sans carte** | Mesure câble-à-câble sans carte |
| Rejeu de vrais paquets réseau (pcap IEX) dans le RTL simulé | Envoyer de vrais ordres sur un exchange |
| Démo live sur flux crypto réel (Coinbase/Binance) via logiciel, puis via FPGA quand la carte arrive | Accès Bloomberg / flux direct NASDAQ temps réel (payant, licences) |
| Mesures sur carte KR260 dès qu'elle est achetée (Phase 7) | — |

Le but réaliste : **un candidat qui montre ce repo doit pouvoir répondre à toute question d'un ingénieur FPGA HFT avec une preuve dans le repo.**

---

## 1. Sources de données financières réelles (sans Bloomberg)

| Source | Contenu | Format | Coût | Usage dans le projet |
| :--- | :--- | :--- | :--- | :--- |
| **NASDAQ ITCH 5.0 samples** (`emi.nasdaq.com/ITCH/Nasdaq ITCH/`) | Journées complètes TotalView-ITCH (tous symboles, ~5–12 Go compressés) | Binaire ITCH 5.0 (sans entête réseau) | Gratuit | Vérité terrain principale : golden model + RTL |
| **IEX HIST** (`iextrading.com/trading/market-data/`) | Captures DEEP / TOPS de journées réelles | **pcap** (Ethernet/IP/UDP réels) | Gratuit | Seule source gratuite de **vrais paquets réseau** → teste l'ingress complet (FCS, UDP, séquences) |
| **LOBSTER** (lobsterdata.com) | Carnets reconstruits NASDAQ, niveaux 1–N | CSV | Échantillons gratuits | Validation croisée indépendante du carnet reconstruit |
| **Databento** | MBO/ITCH historiques et live, multi-venues | DBN / pcap | Crédits gratuits à l'inscription | Données multi-venues pour l'arbitrage cross-exchange |
| **Coinbase Advanced / Binance** WebSocket | Carnets L2/L3 crypto **live**, 24/7 | JSON | Gratuit | Démo temps réel + pont vers la carte (Phase 7) |

> Les fichiers de données ne sont **jamais** commités : un script `data/fetch.py` les télécharge, vérifie leur SHA-256 et les met en cache hors git.

---

## 2. Étapes

Chaque étape = une tranche `docs/features/NNN-nom/` (`spec.md` + `tasks.md`), une branche, une PR, une CI verte. **On ne passe pas à l'étape suivante tant que les critères de preuve ne sont pas remplis.**

### Étape P0 — Audit & vérité des chiffres *(½ journée)*
- [ ] Recenser toutes les affirmations chiffrées (README, guide IA, PLAN, dashboard, vidéo) dans `docs/CLAIMS.md` avec : valeur, source de preuve, statut (*prouvé / simulé / non prouvé*).
- [ ] Choisir **une** architecture d'horloge de référence et corriger toutes les contradictions (156,25 vs 312,5 MHz ; risque 6,4 vs 3,2 ns).
- [ ] Reformuler les sur-promesses : « strict compliance SEC 15c3-5 / MiFID II » → « contrôles pré-trade inspirés de 15c3-5 » ; « wire-to-wire mesuré » → « simulé au cycle près ».
- [ ] Lister les modules **non intégrés** au top-level (Avellaneda-Stoikov, arbitrage, Iceberg/TWAP, parser spéculatif, résilience MoldUDP64) et les marquer *expérimental* en attendant P4.

**Preuve :** `docs/CLAIMS.md` commité ; plus aucune contradiction entre README et guide.

---

### Étape P1 — Reproductibilité & CI *(1–2 jours)*
- [ ] Environnement figé : `Dockerfile` (Ubuntu + Verilator 5.x épinglé + Python 3.11 + cocotb + cocotb-test) et `requirements.txt` complet (aujourd'hui `cocotb_test` manque → les tests RTL plantent à l'import).
- [ ] Un seul point d'entrée : `make test` (golden + RTL + driver + server + client), `make lint`, `make typecheck`.
- [ ] GitHub Actions : lint Verilator `-Wall`, tous les bancs Cocotb, pytest server, tests driver C++, typecheck + build client. Badge dans le README.
- [ ] Nettoyage repo : `obj_dir/`, `client/dist/`, `data/*.db`, caches → `.gitignore` ; aucun artefact généré versionné.
- [ ] `README` : section « Reproduire en 3 commandes ».

**Preuve :** un clone neuf + `docker run … make test` passe ; badge CI vert sur `main`.

---

### Étape P2 — Données réelles & golden model industriel *(3–5 jours)*
- [ ] `data/fetch.py` : téléchargement NASDAQ ITCH sample + IEX HIST pcap, checksums, cache.
- [ ] Golden model : décoder **tous** les types de messages ITCH 5.0 (pas seulement A/F/E/C/X/D/U : aussi `P`, `Q`, `S`, `R`, `H`, `Y`, `L`, `V`, `W`, `K`, `J`, `h`, `I`, `N`), gérer les cas réels (order replace `U` multiples, exécutions partielles, symbol directory).
- [ ] **Validation croisée externe** : comparer le carnet reconstruit à LOBSTER (ou à un parseur open source reconnu) sur ≥ 5 symboles liquides (AAPL, MSFT, SPY, NVDA, TSLA) → 0 divergence BBO.
- [ ] Statistiques de la journée publiées : messages/s pic, distribution des types, profondeur max, nombre d'ordres vivants max (dimensionne la BRAM en P3).
- [ ] Profiler la performance du golden model (cible : une journée complète en < 30 min, sinon réécrire le cœur en C++/Rust avec bindings Python).

**Preuve :** `reports/golden_vs_lobster.md` avec 0 divergence ; stats journée commitées.

---

### Étape P3 — Co-simulation RTL sur journées réelles *(1–2 semaines)*
- [ ] Harnais Verilator C++ (pas Cocotb, trop lent pour des millions de messages) qui injecte le flux ITCH réel dans le RTL et compare **chaque** mise à jour de BBO au golden model.
- [ ] Dimensionnement réaliste : nombre d'ordres vivants simultanés réels (souvent > 100 k par symbole actif) vs capacité BRAM/URAM ; gestion des **collisions de hash** et du débordement (politique documentée et testée).
- [ ] Rejeu des **pcap IEX** à travers l'ingress complet (FCS, IP/UDP, gaps de séquence réels).
- [ ] Tests aléatoires contraints + injection de fautes : paquets corrompus, gaps, rafales, symboles inconnus.
- [ ] Couverture fonctionnelle (Verilator `--coverage`) publiée.
- [ ] **Assertions formelles** (SVA + SymbiYosys) sur les invariants critiques : aucun ordre émis si kill-switch actif, aucun dépassement de collar, FIFO jamais en overflow.

**Preuve :** `reports/cosim_<date>.md` : « N millions de messages, M symboles, 0 divergence », couverture ≥ 90 %, preuves formelles vertes en CI.

---

### Étape P4 — Architecture : intégrer, simplifier, accélérer *(1–2 semaines)*
- [ ] Un **seul top-level** cohérent ; chaque module expérimental est soit intégré et testé de bout en bout, soit déplacé dans `rtl/experimental/`.
- [ ] Supprimer la division OBI du chemin critique (comparaison par produit croisé / seuils pré-calculés) → latence cible ≈ 15–20 cycles au lieu de 49. Documenter l'avant/après.
- [ ] Pipeliner le contrôle de notionnel (multiplication 64 bits sur DSP48E2 en 2–3 étages) au lieu de la promesse « 1 cycle ».
- [ ] Interfaces normalisées AXI4-Stream + AXI4-Lite partout ; registres documentés (`docs/REGISTER_MAP.md` généré automatiquement).

**Preuve :** nouveau budget de latence en cycles, issu de la co-simulation P3, pas d'un tableau écrit à la main.

---

### Étape P5 — Implémentation physique réelle (Vivado, sans carte) *(3–5 jours)*
- [ ] Synthèse + placement-routage complets sur `xck26-sfvc784-2LV-c` (Vivado ML Standard gratuit) avec le vrai MAC 10G/25G (IP AMD 10G/25G Ethernet Subsystem) et les contraintes du connecteur SFP+ de la KR260.
- [ ] Commiter `reports/timing_summary.rpt`, `utilization.rpt`, `power.rpt` et la Fmax atteinte. **Si 312,5 MHz n'est pas tenu, on publie le vrai chiffre** et on itère (re-pipelining, floorplanning Pblock).
- [ ] Build Vivado scripté en CI (runner self-hosted ou job manuel) ; bitstream versionné en artefact de release, pas dans git.

**Preuve :** WNS ≥ 0 à la fréquence annoncée, rapports dans le repo.

---

### Étape P6 — Logiciel & produit niveau pro *(1 semaine)*
- [ ] Mode **« software path »** de référence en C++ (même logique que le RTL) pour comparer FPGA vs CPU : c'est l'argument central d'une démo HFT.
- [ ] Ingestion **live crypto** (Coinbase/Binance WebSocket) → normalisation → pipeline logiciel → dashboard, 24/7.
- [ ] Dashboard : afficher la provenance des données (fichier NASDAQ + date, ou flux live), les latences **mesurées** (p50/p99/p99.9 en histogramme HDR), et l'état du kill-switch.
- [ ] Backend : tests, typage strict, logs structurés, métriques Prometheus, healthchecks.
- [ ] Sécurité : aucune clé en dur, `.env.example`, ports locaux uniquement.

**Preuve :** démo live 24 h sans crash ; captures de latence logicielle réelle.

---

### Étape P7 — Carte KR260 (dès l'achat) *(1–2 semaines)*
- [ ] Bring-up : PetaLinux/Ubuntu KR260, chargement du bitstream, driver UIO, test des registres AXI-Lite.
- [ ] **Hardware-in-the-loop** : un PC rejoue les pcap IEX/NASDAQ sur le port SFP+ (tcpreplay) ; la carte renvoie les ordres OUCH sur l'autre port ; capture et comparaison au golden model.
- [ ] Mesure **réelle** de latence : horodatage PTP matériel + compteurs internes ; publier distribution et gigue.
- [ ] Pont live : flux crypto → PC → paquets UDP → carte → ordres simulés (paper trading, jamais de vrais ordres).

**Preuve :** `reports/hw_latency_<date>.md` avec mesures brutes ; seulement alors le README peut dire « mesuré sur silicium ».

---

### Étape P8 — Stratégie & recherche quant crédibles *(continu)*
- [ ] Backtest **honnête** du signal OBI / Avellaneda-Stoikov sur données NASDAQ réelles : frais, rebates, latence, position dans la file, sélection adverse. Publier aussi les résultats négatifs.
- [ ] Notebook de recherche reproductible (`research/`) + note méthodologique.
- [ ] Ce sont les questions qu'un quant posera : « quel est ton edge après coûts ? », « comment modélises-tu la file ? ».

**Preuve :** `research/obi_backtest.md` avec PnL après coûts et intervalles de confiance.

---

### Étape P9 — Présentation professionnelle *(2–3 jours)*
- [ ] README réécrit : problème → architecture → preuves (liens vers chaque rapport) → limites connues.
- [ ] `docs/DESIGN_DECISIONS.md` : pourquoi chaque choix (BRAM vs URAM, hash vs CAM, pas de division…).
- [ ] Article technique (blog/LinkedIn) + vidéo promo mise à jour avec les chiffres prouvés.
- [ ] Préparation entretien : 20 questions types FPGA/HFT avec la réponse et le lien vers la preuve dans le repo.

---

## 3. Ordre et durée estimée

| Étape | Dépend de | Durée | Carte requise |
| :--- | :--- | :--- | :---: |
| P0 Audit chiffres | — | ½ j | non |
| P1 Reproductibilité & CI | P0 | 1–2 j | non |
| P2 Données réelles | P1 | 3–5 j | non |
| P3 Co-sim journées réelles | P2 | 1–2 sem | non |
| P4 Architecture | P3 | 1–2 sem | non |
| P5 Vivado réel | P4 | 3–5 j | non |
| P6 Logiciel pro & live crypto | P2 | 1 sem | non |
| P7 Carte KR260 | P5 | 1–2 sem | **oui** |
| P8 Recherche quant | P2 | continu | non |
| P9 Présentation | P5 (puis P7) | 2–3 j | non |

**Total sans carte : ~6–8 semaines** de travail régulier. P6 et P8 peuvent avancer en parallèle de P3–P5.

---

## 4. Définition de « fini »

Le projet est « pro » quand un ingénieur externe peut, sur un clone neuf :
1. lancer `make test` dans Docker et voir tout passer ;
2. rejouer une journée NASDAQ réelle dans le RTL et obtenir 0 divergence ;
3. ouvrir les rapports Vivado et retrouver la Fmax annoncée ;
4. retrouver chaque chiffre du README dans `docs/CLAIMS.md` avec sa preuve.
