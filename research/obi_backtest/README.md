# Backtest OBI (étape P8)

Backtest de la règle de trading **telle qu'elle est câblée dans le RTL**
(`rtl/quant/obi_signal.sv`, `rtl/risk/risk_ouch_top.sv`, `rtl/risk/pre_trade_risk.sv`)
sur des données NASDAQ ITCH 5.0 réelles, après coûts. Méthodologie et résultats :
[`../obi_backtest.md`](../obi_backtest.md).

## Lancer

```bash
python data/fetch.py --messages 60000000      # ~750 Mo lus, ~1,9 Go écrits dans data/cache/ (gitignoré)
python -m research.obi_backtest               # prend le plus gros fichier 01302019 de data/cache/
python -m pytest research                     # tests unitaires du modèle de fill et des coûts
```

Options : `--itch FICHIER`, `--symbols AAPL MSFT ...`, `--re-extract`.

## Fichiers

| Fichier | Rôle |
| :-- | :-- |
| `extract.py` | Une passe sur le fichier ITCH, reconstruction des carnets par `GoldenOrderBook` (validé 0 divergence vs MeatPy), export d'un tableau d'événements par symbole (`data/cache/*.obi_events.<SYM>.npz`). |
| `model.py` | Règle OBI exacte en Q1.31, contrôles de risque, modèle de fill passif (priorité prix-temps), coûts. |
| `backtest.py` | Boucle de stratégie, borne haute mid-to-mid, comportement littéral du RTL, statistiques (drawdown, bootstrap par blocs). |
| `__main__.py` | Grille seuil × horizon × latence, écrit `results/results.json` et `results/results.md`. |
| `test_fill_costs.py` | Scénarios faits main : file d'attente, partiels, trade-through, coûts, règle Q1.31, risque, absence de look-ahead. |

Les données NASDAQ ne sont jamais commitées ; seuls les agrégats (`results/`) le sont.
