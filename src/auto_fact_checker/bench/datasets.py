"""Benchmark datasets: SciFact claims as binary SUPPORT / CONTRADICT items, plus seeded balanced sampling.

Local: loads the Hugging Face parquet export of allenai/scifact (the original repo uses a loading script that
`datasets` >= 4 no longer runs), keeps claims whose evidence labels are all SUPPORT or all CONTRADICT (NEI and
conflicting claims are dropped: NEI only means "the given abstract does not address the claim", not "false").
Global context: bench/run.py turns each item's claim into a fact-checking run; label True = SUPPORT.
Dataset: Wadden et al. 2020, "Fact or Fiction: Verifying Scientific Claims", https://arxiv.org/abs/2004.14974 ;
https://huggingface.co/datasets/allenai/scifact (CC BY-NC 2.0). Expected binary counts (verified 2026-10-17):
validation 124 SUPPORT / 64 CONTRADICT, train 332 / 173.
"""

import random
from dataclasses import dataclass, field

import pandas as pd

SCIFACT_URL = ("https://huggingface.co/datasets/allenai/scifact/resolve/refs%2Fconvert%2Fparquet/"
               "claims/{split}/0000.parquet")


@dataclass
class BenchItem:
    """One benchmark claim with its gold binary label (True = supported by the scientific evidence)."""

    id: str
    text: str
    label: bool
    meta: dict = field(default_factory=dict)


def load_scifact(splits=("validation", "train")) -> list[BenchItem]:
    """Binary SciFact claims from the given splits (test labels are hidden, so it is never used)."""
    items = []
    for split in splits:
        df = pd.read_parquet(SCIFACT_URL.format(split=split))  # one row per (claim, evidence document)
        for cid, group in df.groupby("id", sort=True):
            labels = {x for x in group["evidence_label"] if x}
            if len(labels) == 1:  # drop NEI (no label) and conflicting claims
                gold = labels.pop()
                items.append(BenchItem(id=f"{split}-{cid}", text=str(group["claim"].iloc[0]),
                                       label=gold == "SUPPORT", meta={"split": split, "gold": gold}))
    return items


def sample_balanced(items: list[BenchItem], n: int, seed: int = 0, exclude_ids=frozenset()) -> list[BenchItem]:
    """n items with equal numbers of each label (seeded, reproducible), skipping excluded ids (e.g. pilot)."""
    rng = random.Random(seed)
    pool = [i for i in items if i.id not in exclude_ids]
    pos = sorted((i for i in pool if i.label), key=lambda i: i.id)
    neg = sorted((i for i in pool if not i.label), key=lambda i: i.id)
    k = min(n // 2, len(pos), len(neg))
    chosen = rng.sample(pos, k) + rng.sample(neg, k)
    rng.shuffle(chosen)
    return chosen


DATASETS = {"scifact": load_scifact}
