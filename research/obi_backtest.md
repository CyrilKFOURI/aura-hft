# Backtest honnête de la stratégie OBI câblée (étape P8)

**Conclusion courte : sur les données réelles du 30/01/2019, la stratégie telle que le RTL l'implémente perd de l'argent après coûts, dans toutes les configurations testées, en pré-ouverture comme en séance régulière.** Le signal OBI contient une petite information directionnelle (borne mid-to-mid positive en séance régulière), mais elle est inférieure à ce que coûtent la sélection adverse sur l'entrée passive et le spread payé à la sortie. Une seule demi-journée ne prouve rien, ni dans un sens ni dans l'autre.

Reproduire (≈ 35 min de téléchargement, ≈ 15 min d'extraction, 1 min de grille) :

```bash
python data/fetch.py --messages 60000000
python -m research.obi_backtest
python -m pytest research
```

Résultats bruts complets, générés par le script : [`obi_backtest/results/results.md`](obi_backtest/results/results.md) (et `results.json`).

## 1. Données

- NASDAQ TotalView-ITCH 5.0, échantillon public du **30/01/2019**, 60 M premiers messages (flux lu en continu, SHA-256 `a714f8cd…f74d`). Couverture : 04:00:00 → **10:11:06 ET**. Donc 5 h 30 de pré-ouverture et **41 minutes** de séance régulière seulement.
- Symboles : AAPL, MSFT, TSLA, QQQ. Carnets reconstruits par `sim/golden_model/golden_order_book.py`, validé à 0 divergence contre MeatPy sur ce fichier (P2). Événements carnet : AAPL 396 064, MSFT 253 055, TSLA 179 979, QQQ 701 286.

## 2. Règle de trading répliquée (lue dans le RTL)

| Élément | RTL | Backtest |
| :-- | :-- | :-- |
| Signal | `obi_signal.sv` : achat si `(Vb−Va)·2^31 ≥ T_buy·(Vb+Va)`, vente si `≤ T_sell·(Vb+Va)`, Q1.31, taille au meilleur niveau uniquement | Même comparaison entière exacte (`model.obi_signals`), `T_sell = −T_buy` |
| Ordre | `risk_ouch_top.sv` : achat au **best bid**, vente au **best ask**, `cfg_default_order_shares` | 100 actions, prix = touche au moment de la décision |
| Risque | `pre_trade_risk.sv` : kill switch, max actions, collier de prix, notionnel unitaire, notionnel cumulé | Mêmes règles et même priorité (`model.risk_check`) ; config des bancs : 1000 actions, collier 0,50 $, 50 k$ par ordre ; **plafond cumulé désactivé** pour la recherche (voir §5) |

**Ce que le RTL ne fait pas et que le backtest a dû ajouter** (écarts assumés, nécessaires pour qu'il y ait une stratégie évaluable) :

1. **Une position à la fois.** Le RTL émet un ordre à chaque mise à jour du BBO tant que le signal tient (limité seulement par `tx_busy`, ~77 ns). Il n'a ni gestion de position, ni annulation, ni sortie.
2. **Durée de vie de l'ordre d'entrée = horizon H**, puis annulation (latence d'annulation ignorée).
3. **Sortie** : ordre agressif (taker) à la touche opposée H après le fill, plus la latence.
4. Filtre : carnet des deux côtés non vide, non croisé, heure ≥ 04:00 (le RTL tirerait aussi sur un carnet à un seul côté, OBI = ±1).

## 3. Modèle de fill (hypothèses explicites)

L'ordre virtuel arrive à `t_décision + latence` et rejoint **la fin de la file** à son prix. Chaque événement du carnet porte l'heure d'entrée de l'ordre réel touché (= sa priorité).

- **Marketable à l'arrivée** (le marché a bougé pendant la latence, ask ≤ notre prix d'achat) : fill immédiat à la touche opposée, **taker**.
- **Priorité prix-temps** : les exécutions (`E`/`C`) au même prix sur des ordres **plus anciens** que nous ne nous remplissent pas. Une exécution au même prix sur un ordre **plus jeune** que nous nous aurait touchés d'abord (FIFO) : elle nous remplit action pour action. C'est la position dans la file à l'entrée, suivie exactement.
- **Annulations** (`X`/`D`/`U`) d'ordres devant nous : nous font avancer, ne remplissent jamais.
- **Trade-through** : exécution de notre côté à un prix pire que le nôtre, ou touche opposée qui traverse notre prix → fill du reste.
- Fill partiel possible ; le reste est annulé à l'expiration.
- Non modélisé : ordres cachés/non affichés, impact de nos propres ordres sur le marché (100 actions), profondeur à la sortie (on suppose 100 actions disponibles à la touche), file d'attente côté exchange pour l'OUCH.

Absence de look-ahead : toute décision lit l'état du carnet à l'événement courant ; tout prix à un instant t lit la dernière ligne de timestamp ≤ t (`model.row_at`). Un test le vérifie (`test_strategy_end_to_end_no_lookahead`).

## 4. Coûts

| Poste | Valeur | Source / statut |
| :-- | :-- | :-- |
| Frais taker Nasdaq | 0,0030 $/action | Hypothèse : plafond Reg NMS 610, tarif standard Nasdaq 2019 |
| Rebate maker Nasdaq | 0,0020 $/action | **Hypothèse** (dépend du palier de volume, 0,0015–0,0030 en 2019) |
| Frais SEC Section 31 (ventes) | 13,00 $ par million vendu | SEC, *Fee Rate Advisory #2 for Fiscal Year 2019* (taux en vigueur jusqu'au 15/04/2019) |
| FINRA TAF (ventes) | 0,000119 $/action, plafond 5,95 $/trade | Hypothèse : barème FINRA 2019 |

Latence de réaction testée : 0, 1, 10, 100 µs (appliquée à l'entrée et à la sortie).

## 5. Résultats (latence 1 µs, après coûts, 4 symboles agrégés)

### Séance régulière (09:30–10:11)

| Seuil | Horizon | Trades | Hit rate | Brut $/action | **Net $/action** | **PnL net $** | Max DD $ | IC 95 % PnL net |
|--:|--:|--:|--:|--:|--:|--:|--:|:--|
| 0.2 | 1 s | 2 044 | 12,4 % | −0,0249 | −0,0282 | −5 656 | 5 656 | [−6 534 ; −4 751] |
| 0.2 | 10 s | 555 | 33,5 % | −0,0328 | −0,0361 | −1 993 | 1 996 | [−2 323 ; −1 324] |
| 0.2 | 60 s | 119 | 38,7 % | −0,0408 | −0,0442 | −526 | 530 | [−879 ; +36] |
| 0.4 | 1 s | 1 865 | 13,4 % | −0,0262 | −0,0295 | −5 369 | 5 369 | [−6 308 ; −4 336] |
| 0.4 | 10 s | 544 | 31,1 % | −0,0345 | −0,0379 | −2 048 | 2 049 | [−2 442 ; −1 565] |
| 0.4 | 60 s | 115 | 49,6 % | −0,0035 | −0,0069 | −79 | 411 | [−510 ; +610] |
| 0.6 | 1 s | 1 669 | 14,0 % | −0,0253 | −0,0286 | −4 659 | 4 659 | [−5 739 ; −3 626] |
| 0.6 | 10 s | 521 | 33,6 % | −0,0333 | −0,0366 | −1 899 | 1 917 | [−2 182 ; −1 381] |
| 0.6 | 60 s | 122 | 42,6 % | −0,0865 | −0,0900 | −1 097 | 1 097 | [−1 786 ; −253] |

### Pré-ouverture (04:00–09:30)

Toutes les configurations perdent : net de −0,057 à −0,095 $/action, IC 95 % entièrement négatifs (tableau complet dans `results.md`). Le spread pré-ouverture est large et la sortie taker le paie à chaque trade.

### Par symbole (seuil 0.4, horizon 10 s, séance régulière)

| Symbole | Trades | Hit rate | Net $/action | PnL net $ | Max DD $ | IC 95 % |
|:--|--:|--:|--:|--:|--:|:--|
| AAPL | 154 | 33,1 % | −0,0388 | −587 | 587 | [−771 ; −385] |
| MSFT | 138 | 30,4 % | −0,0158 | −217 | 234 | [−387 ; −95] |
| TSLA | 94 | 28,7 % | −0,1050 | −986 | 996 | [−1 245 ; −571] |
| QQQ | 158 | 31,0 % | −0,0163 | −257 | 270 | [−366 ; −213] |

### Sensibilité à la latence (séance régulière, seuil 0.4) — net $/action

| Horizon | 0 µs | 1 µs | 10 µs | 100 µs |
|--:|--:|--:|--:|--:|
| 1 s | −0,0295 | −0,0295 | −0,0295 | −0,0296 |
| 10 s | −0,0379 | −0,0379 | −0,0379 | −0,0381 |
| 60 s | −0,0069 | −0,0069 | −0,0069 | −0,0069 |

La latence entre 0 et 100 µs ne change presque rien : la stratégie est **passive** (elle rejoint la fin de la file) et tient des secondes. Un avantage de latence FPGA ne sert à rien pour cette règle ; il servirait à une stratégie qui prend la liquidité ou qui gagne la priorité en file.

### Borne haute naïve « mid-to-mid » (clairement irréaliste)

Entrée et sortie au mid, sans coûts, sans file, sans latence. Séance régulière : +0,004 à +0,012 $/action à 1–10 s, IC 95 % positifs (ex. seuil 0.4, 10 s : +0,0124 $/action, 953 signaux, IC [+296 ; +1 659] $ pour 100 actions). Pré-ouverture : IC qui contiennent 0. **Le signal a donc un peu d'information directionnelle, de l'ordre de 1 tick sur 10 s, mais la moitié du spread payée à la sortie et la sélection adverse sur l'entrée passive (on est rempli surtout quand le prix part contre nous : hit rate de 12–34 % contre ~50 % pour la borne) l'effacent largement.**

### Comportement littéral du RTL

Avec seuil 0.4 et la config des bancs (plafond cumulé 500 k$), le RTL émet un ordre à chaque mise à jour du BBO qui satisfait le signal (AAPL : 199 392 ordres sur la période), et le plafond cumulé, qui ne décroît jamais, **bloque tout dès 04:03 (AAPL, QQQ), 04:35 (MSFT), 05:12 (TSLA)** après 16 à 47 ordres. En l'état, le pipeline n'est pas une stratégie déployable : il faut une gestion de position/annulation côté matériel ou logiciel avant de parler de PnL.

## 6. Statistiques

- PnL par trade = brut − frais des deux jambes. Hit rate = part des trades à PnL net > 0. Max drawdown sur la courbe de PnL net cumulé.
- IC 95 % : bootstrap par blocs mobiles (blocs de 5 minutes) sur le PnL net agrégé par minute, 2000 tirages, graine fixe. Les minutes sans trade comptent pour 0.

## 7. Limites

- **Une seule journée**, et seulement 41 minutes de séance régulière, dont l'ouverture (régime atypique). Aucune conclusion de stabilité possible ; il faudrait des dizaines de jours (P2 : journée complète, autres dates).
- Grille de 3 seuils × 3 horizons × 4 latences explorée sur les mêmes données : aucune configuration n'est gagnante, donc pas de risque de sélection d'un faux positif, mais une configuration « moins perdante » (0.4 / 60 s) n'est pas un edge.
- Frais/rebates : hypothèses de palier ; un rebate plus élevé (0,0030) n'améliorerait le net que de 0,001 $/action, loin des pertes mesurées.
- Ordres cachés, profondeur à la sortie, impact de marché et latence d'annulation non modélisés ; les fills par trade-through sont probablement optimistes pour un ordre virtuel.
- Sortie taker uniquement ; une sortie passive ou une logique de market-making (Avellaneda-Stoikov, expérimental) n'est pas testée ici.
- Pas de contrôle des LULD/halts, ni de la position nette maximale.
