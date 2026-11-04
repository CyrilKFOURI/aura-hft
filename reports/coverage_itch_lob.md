# Couverture Verilator — `itch_lob_pipeline_top` sous le banc d'injection de fautes

- Run : `make coverage` (Docker `aura-hft-ci`, Verilator 5.040, `--coverage-line --coverage-toggle`), 2026-10-21.
- Stimulus : les 10 scénarios de `sim/tests/test_fault_injection.py` (un processus par scénario, `.dat` fusionnés par `verilator_coverage --write`). **Pas** les co-sims sur données réelles (non instrumentées).
- `verilator_coverage` global : **57,0 %** (647/1 125 points). Détail (`python -m sim.validation.coverage_summary`) :

| Fichier | line | branch | toggle |
| :-- | --: | --: | --: |
| `depth_book.sv` | 92.1 % (35/38) | 64.6 % (53/82) | 16.2 % (150/926) |
| `ingress_pipeline_top.sv` | — | — | 29.8 % (635/2130) |
| `itch_lob_pipeline_top.sv` | — | — | 36.6 % (1015/2776) |
| `itch_pkg.sv` | 0.0 % (0/4) | — | — |
| `lob_engine_top.sv` | 87.5 % (7/8) | 85.0 % (17/20) | 32.3 % (1055/3268) |
| `moldudp64_depacketizer.sv` | 34.3 % (12/35) | 51.5 % (34/66) | 34.0 % (557/1636) |
| `order_store.sv` | 54.3 % (25/46) | 73.7 % (28/38) | 15.5 % (189/1220) |
| `speculative_itch_parser.sv` | 61.8 % (21/34) | 61.5 % (32/52) | 49.2 % (354/720) |
| `top_of_book_cache.sv` | 100.0 % (3/3) | 90.9 % (20/22) | 38.0 % (742/1952) |
| **Total** | **61.3 %** (103/168) | **65.7 %** (184/280) | **32.1 %** (4697/14628) |

## Lecture honnête

**Loin de la cible P3 (≥ 90 %).** Ce qui manque et compte :

- **Parser** : messages `F` (Add avec MPID) et `C` (Executed with price) jamais envoyés par ce banc ; mode `skip_frame` (longueur 0 ou > 62 *au milieu* d'une trame) non exercé — seul le cas en fin de trame l'est.
- **Dépaquetiseur** : branche `STRIP_ETH_IP_UDP=0` jamais instanciée dans le top de référence (code mort pour ce top) ; trames d'un mot ou à < 2 octets de charge dans le dernier mot non testées ; `keep_to_len` / `len_to_keep` hors valeurs contiguës (tkeep non contigu jamais envoyé).
- **Carnet** (`order_store.sv`, `depth_book.sv`, hors de ce lot) : stash du hachage deux-choix, table pleine, ordres hors fenêtre de prix et `U` (replace) peu couverts ici ; ils le sont en partie par la co-sim réelle (non instrumentée).
- **Toggle 32 %** : attendu bas avec des stimuli dirigés (bus 64 bits, mémoire FIFO) ; pas un objectif en soi.

Suite : instrumenter aussi `tb_order_book`, un préfixe de co-sim réelle et un banc aléatoire contraint, puis viser 90 % ligne/branche sur ingress + parser.
