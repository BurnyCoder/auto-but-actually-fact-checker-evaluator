| system | n | accuracy [95% Wilson CI] | balanced acc. | macro-F1 | AUROC | Brier | parse fails | leak items | mean searches | cost $ |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 200 | 0.755 [0.691, 0.809] | 0.755 | 0.755 | 0.844 | 0.165 | 0 | 0 | 0.00 | 0.0634 |
| full_single_openai | 200 | 0.865 [0.811, 0.906] | 0.865 | 0.865 | 0.944 | 0.101 | 0 | 0 | 1.17 | 2.9725 |

| comparison | Δ balanced accuracy [95% paired bootstrap CI] | McNemar b / c | exact p |
|---|---|---|---|
| baseline_vs_full_single_openai | +0.110 [+0.062, +0.160] | 3 / 25 | 0.0000 |
