| system | n | accuracy [95% Wilson CI] | balanced acc. | macro-F1 | AUROC | Brier | parse fails | leak items | mean searches | cost $ |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 6 | 1.000 [0.610, 1.000] | 1.000 | 1.000 | 1.000 | 0.027 | 0 | 0 | 0.00 | 0.0017 |
| full_single_openai | 6 | 0.833 [0.436, 0.970] | 0.833 | 0.829 | 1.000 | 0.096 | 0 | 0 | 1.33 | 0.0992 |

| comparison | Δ balanced accuracy [95% paired bootstrap CI] | McNemar b / c | exact p |
|---|---|---|---|
| baseline_vs_full_single_openai | -0.167 [-0.500, +0.000] | 1 / 0 | 1.0000 |
