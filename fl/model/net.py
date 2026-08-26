"""Lightweight on-device intent classifier (~70k params) - genuinely deployable."""
import numpy as np
import torch
import torch.nn as nn

HASH_DIM = 2048
EMBED_DIM = 32
HIDDEN = 64


class IntentNet(nn.Module):
    def __init__(self, num_classes: int, hash_dim=HASH_DIM,
                 embed_dim=EMBED_DIM, hidden=HIDDEN):
        super().__init__()
        self.emb = nn.EmbeddingBag(hash_dim, embed_dim, mode="mean")
        self.fc1 = nn.Linear(embed_dim, hidden)
        self.act = nn.ReLU()
        self.fc2 = nn.Linear(hidden, num_classes)

    def forward(self, text_idx, offsets):
        x = self.emb(text_idx, offsets)
        return self.fc2(self.act(self.fc1(x)))


def flatten_state(sd) -> np.ndarray:
    return np.concatenate(
        [v.detach().cpu().numpy().ravel() for v in sd.values()]
    ).astype(np.float32)


def unflatten_state(flat: np.ndarray, template) -> dict:
    out, i = {}, 0
    for k, v in template.items():
        n = v.numel()
        out[k] = torch.tensor(flat[i:i + n].reshape(tuple(v.shape)), dtype=v.dtype)
        i += n
    return out


def num_params(model) -> int:
    return sum(p.numel() for p in model.state_dict().values())
