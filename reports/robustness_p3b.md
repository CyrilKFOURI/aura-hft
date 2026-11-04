# Robustesse du pipeline de référence — étape P3 (2/2)

Environnement : Docker `aura-hft-ci` (Verilator 5.040, cocotb 2.0.1), image `aura-hft-formal` (= CI + yosys 0.33 Ubuntu 24.04). Date : 2026-10-21. Tout ce qui suit a été exécuté ; rien n'est extrapolé.

## 1. Injection de fautes — `sim/tests/test_fault_injection.py` (`itch_lob_pipeline_top`)

Chaque scénario rejoue le trafic fautif dans le RTL, applique l'interprétation correcte au golden model (`sim/golden_model/golden_order_book.py`) et exige top 5 RTL = golden, plus la télémétrie documentée (contrat : `docs/features/029-robustness/spec.md`).

| Scénario | Avant correction | Après |
| :-- | :-- | :-- |
| Types ITCH inconnus (`S`, `R`, `?`) | ✅ | ✅ |
| Symboles inconnus | ✅ | ✅ |
| E/X/D/U sur références inconnues (6 messages → 6 `table_miss`) | ✅ | ✅ |
| Ordres à 0 action | ✅ | ✅ |
| Trou de séquence (gap = 6, attente = 11) | ✅ | ✅ |
| **Doublon MoldUDP64** | ❌ appliqué deux fois : bid 1 500 000 à 200 au lieu de 100 | ✅ trame jetée |
| **Trame tronquée** | ❌ blocage du pipeline (timeout 3 ms simulées) | ✅ |
| **Bloc de longueur 0** | ❌ blocage définitif du parser | ✅ |
| Trames ARP / IPv4 avec options / TCP (nouveau) | (analysées comme MoldUDP64) | ✅ jetées, séquence intacte |
| **Rafale dos-à-dos** (1 800 messages, 48 trames de 38) | ❌ **741 requêtes perdues** (FIFO 64 pleine, sans frein) | ✅ 0 perte ; débit soutenu mesuré 0,117 msg/cycle = 18,3 M msg/s à 156,25 MHz |

Résultat : **10/10 passent** (run du 2026-10-21).

### Bugs RTL trouvés et corrigés

1. **Doublons réappliqués** (`moldudp64_depacketizer.sv`). Scénario : trames seq 1 (2 msgs), seq 3 (2 msgs), puis seq 1 retransmise. Attendu : carnet inchangé. Observé : `duplicate_detected` levé mais les messages transmis au carnet (parts doublées). Correction : trame jetée (`drop_frame`), compteur `dropped_dup_frames`. Un recouvrement partiel jette aussi la trame ; la trame suivante lève alors un trou (détecté, non silencieux).
2. **Parser bloqué par une trame tronquée ou un bloc de longueur 0** (`speculative_itch_parser.sv`). Le parser ignorait `tlast` : un reste de message se collait à la trame suivante, et une longueur 0 bloquait la fenêtre pour toujours (`s_axis_tready` à 0). Correction : suivi de frontière de trame (`eof_valid/eof_pos`), rejet de la fin de trame incomplète, saut du reste de trame si longueur 0 ou > 62 (`truncated_msg_count`). Aucun cycle ajouté pour une trame propre à un message.
3. **Perte silencieuse de requêtes** (`lob_engine_top.sv`). La FIFO de 64 requêtes jetait en silence quand le carnet (multi-cycle) est plus lent que le parser. Correction : `req_almost_full` (64 − 8) → `book_backpressure` de `ingress_pipeline_top`, qui gèle le flux dépaquetiseur → parser et donc `s_axis_tready`.
4. **Trames non MoldUDP64 analysées** (dépaquetiseur, `STRIP_ETH_IP_UDP=1`). Contrôle EtherType 0x0800, IHL 5, protocole 17 ; sinon trame jetée sans toucher à la séquence (`dropped_bad_hdr_frames`).
5. **Débordement 64 bits du notionnel cumulé** (`pre_trade_risk.sv`, trouvé par la preuve formelle, §4). `acc + notionnel` pouvait passer 2^64 et revenir sous la limite : contre-exemple yosys à 5 cycles (acc = 2,786·10^18, notionnel = 1,566·10^19, limite = 2 → approuvé, acc = 2). Correction : comparaison sur 65 bits et accumulateur saturant.

Les modules interdits (`order_store.sv`, `depth_book.sv`) n'ont pas été modifiés.

### Écart non corrigé : FCS (`aura_hft_top`)
`sim/tests/test_fcs_top.py` envoie une trame avec FCS correct puis une avec FCS corrompu. Attendu : `fcs_error_count = 1` et trame non appliquée. Observé : `axis_eth_fcs_checker` est instancié avec `CHECK_TRAILING_FCS=0` et sans FCS en bande latérale, en cut-through : rien n'est compté et la trame atteint le carnet. Correction non triviale (tampon store-and-forward, ou s'appuyer sur le MAC AMD qui jette les trames invalides) → P5. Test marqué `xfail(strict=True)`.

## 2. Cadrage réseau réel — IEX HIST (`sim/tests/test_iex_framing.py`)

- Source : IEX HIST DEEP 1.0 du 30/01/2019 (même jour que l'échantillon NASDAQ), fichier publié 1,30 Go ; `data/fetch_iex.py` le lit en flux et garde les **5 000 premières trames** (262 Ko compressés lus, jamais commités).
- Trames : 5 000/5 000 Ethernet II / IPv4 sans options / UDP, 0 VLAN, 1 MAC source, multicast 23.226.155.132 → 233.215.21.4, port 10378, 82 à 1 512 octets (moyenne 210,7).
- Méthode : en-têtes réels conservés (MAC, EtherType, TOS/ID/flags/TTL/adresses IP, ports UDP ; longueurs et checksum IP recalculés, checksum UDP à 0) ; la charge IEX-TP est remplacée par un paquet MoldUDP64 de vrais messages NASDAQ AAPL **remplissant la taille d'origine** (1 à 52 messages par trame).
- Résultat : **5 000 trames, 23 123 messages réels, 0 divergence top 5** après chaque trame, 0 trou, 0 trame rejetée, 0 troncature, 0 débordement FIFO (`reports/iex_framing_20190130.json`).
- Limite honnête : le FCS réel n'est pas présent dans la capture (pcap sans FCS) ; la variété de cadrage d'un seul flux IEX est faible (pas de VLAN ni d'options IP réels) — les cas ARP/options/TCP sont couverts par l'injection de fautes.

Non-régression sur données réelles après les corrections : co-sim AAPL `test_real_data_rtl.py`, **125 232 messages, 0 divergence BBO, 0 divergence top 5**.

## 3. Couverture

Voir [coverage_itch_lob.md](coverage_itch_lob.md).

## 4. Méthode formelle — ce qui a réellement été fait

- **Preuve** (`make docker-formal`, `formal/run_risk_formal.sh`) : propriétés P1–P6 de `rtl/assertions/pre_trade_risk_props.sv` sur `pre_trade_risk`, toutes entrées libres à chaque cycle, reset au premier cycle. Moteur : `sat -tempinduct` de yosys (SAT bit-level : BMC depuis le reset + k-induction). **Résultat : induction prouvée à k = 3 (preuve non bornée).**
- Ce n'est **pas** SymbiYosys : `sby` n'est pas packagé pour Ubuntu 24.04, et `yosys-smtbmc` avec les z3/boolector Ubuntu n'a pas fini le pas 0 en 10 min (boolector plante dans le déroulage). PDR (ABC) n'a pas convergé en 15 min sur le multiplicateur.
- **Abstraction** : le produit 32×32 du notionnel est un point de coupure (valeur libre) ; le checker utilise la même expression, fusionnée en une seule cellule `$mul` (vérifié par `select -assert-count 1`). Les propriétés sont donc vraies pour *tout* notionnel ; l'arithmétique du DSP n'est pas prouvée.
- **Non-vacuité** : 8 mutants (kill-switch étage A, étage B, max actions, collar, notionnel, cumul, cumul 64 bits, strobes simultanés) sont tous **réfutés**.
- **Simulation** : le même checker est lié (`bind`) dans `pre_trade_risk` et exécuté avec `--assert` sous les bancs `tb_risk_and_ouch` et `tb_tick_to_trade_top` (`test_risk_assertions.py`) : 2/2 passent, aucune assertion déclenchée.
- P1 porte sur `risk_approved`, qui pilote directement `ouch_order_gen.order_valid` : un kill-switch levé au cycle même où l'approbation sort n'arrête pas cette trame (fenêtre d'un cycle, documentée).
- Non prouvé : « FIFO jamais en overflow » (le frein §1 est vérifié en simulation seulement).

## 5. Régression complète

`PYTHONPATH=. python -m pytest -q sim/tests server/tests -p no:cacheprovider` (Docker) : **51 passed, 2 skipped, 1 xfailed** (26 min). Skips : `test_real_data_rtl.py` (sans `REAL_STREAM`) et `test_real_data_meatpy.py` (pas de capture `.itch` dans `data/cache` du worktree). xfail : FCS (§1). `make lint` (Verilator `-Wall` sur les 4 tops + ruff) : propre.
