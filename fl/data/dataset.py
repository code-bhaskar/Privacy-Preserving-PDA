"""Hashing-trick featurizer. No shared vocabulary => no cross-client vocab leakage."""
import hashlib
import re

import torch
from torch.utils.data import Dataset

from fl.model.net import HASH_DIM

_TOKEN = re.compile(r"[a-z0-9']+")


def tokenize(text: str):
    return _TOKEN.findall(text.lower())


def hash_token(tok: str, dim: int = HASH_DIM) -> int:
    return int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(),
                          "big") % dim


def encode(text: str):
    idx = [hash_token(t) for t in tokenize(text)]
    return idx or [0]


class IntentDataset(Dataset):
    def __init__(self, rows):
        self.rows = rows  # list of (text, label_int)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        text, label = self.rows[i]
        return torch.tensor(encode(text), dtype=torch.long), label


def collate(batch):
    idx_list, offsets, labels = [], [0], []
    for idx, lbl in batch:
        idx_list.append(idx)
        offsets.append(offsets[-1] + len(idx))
        labels.append(lbl)
    return (
        torch.cat(idx_list),
        torch.tensor(offsets[:-1], dtype=torch.long),
        torch.tensor(labels, dtype=torch.long),
    )
