import numpy as np

from fl.privacy.accountant import compute_rdp, rdp_to_dp, sigma_for_target_epsilon
from fl.protocol import shamir
from fl.protocol.quantize import dequantize_sum, quantize
from fl.protocol.secagg import ClientSecAgg, ServerSecAgg, self_mask


def _make_clients(ids, threshold=2, round_id=7):
    cs = {i: ClientSecAgg(i, threshold, round_id) for i in ids}
    peers = {i: {"c_pk": c.c_pk, "s_pk": c.s_pk} for i, c in cs.items()}
    for c in cs.values():
        c.peer_pubkeys = peers
    return cs, peers


def test_shamir_roundtrip():
    secret = int.from_bytes(b"\x11" * 32, "big")
    shares = shamir.split(secret, 3, 5)
    assert shamir.reconstruct(shares[:3]) == secret
    assert shamir.reconstruct(shares[2:5]) == secret


def test_masks_cancel():
    d, ids = 1000, [1, 2, 3]
    cs, _ = _make_clients(ids)
    rng = np.random.default_rng(0)
    xs = {i: rng.integers(0, 2 ** 20, d, dtype=np.uint64).astype(np.uint32)
          for i in ids}
    ys = {i: cs[i].mask_vector(xs[i], ids) for i in ids}

    masked_sum = np.zeros(d, dtype=np.uint32)
    for y in ys.values():
        masked_sum += y
    for i in ids:
        masked_sum -= self_mask(cs[i].b_seed, d)

    expected = np.zeros(d, dtype=np.uint32)
    for x in xs.values():
        expected += x
    assert np.array_equal(masked_sum, expected)


def test_masked_vector_hides_individual_update():
    d, ids = 500, [1, 2, 3]
    cs, _ = _make_clients(ids)
    x = np.full(d, 12345, dtype=np.uint32)
    y = cs[1].mask_vector(x, ids)
    assert not np.array_equal(x, y)
    # masked output should look uniform, not concentrated on the constant
    assert np.unique(y).size > d * 0.9


def test_server_aggregate_with_dropout():
    d, ids = 256, [1, 2, 3, 4, 5]
    threshold, rid = 3, 11
    cs, peers = _make_clients(ids, threshold, rid)

    sealed = {i: cs[i].make_shares(peers) for i in ids}
    for target in ids:
        cs[target].store_shares(
            {owner: sealed[owner][target] for owner in ids if owner != target})

    rng = np.random.default_rng(1)
    xs = {i: rng.integers(0, 2 ** 18, d, dtype=np.uint64).astype(np.uint32)
          for i in ids}
    masked = {i: cs[i].mask_vector(xs[i], ids) for i in ids}

    dropped = [5]
    survivors = [i for i in ids if i not in dropped]
    masked = {i: masked[i] for i in survivors}

    b_pool, s_pool = {}, {}
    for i in survivors:
        rev = cs[i].reveal(survivors, dropped)
        for o, p in rev["b_shares"].items():
            b_pool.setdefault(o, []).append(p)
        for o, p in rev["s_shares"].items():
            s_pool.setdefault(o, []).append(p)

    total = ServerSecAgg.aggregate(
        masked, b_pool, s_pool,
        {i: {"s_pk": cs[i].s_pk} for i in ids},
        survivors, dropped, threshold, rid)

    expected = np.zeros(d, dtype=np.uint32)
    for i in survivors:
        expected += xs[i]
    assert np.array_equal(total, expected)


def test_quantize_roundtrip():
    rng = np.random.default_rng(2)
    clip = 2.0
    vecs = [rng.normal(0, 0.3, 400).astype(np.float32).clip(-clip, clip)
            for _ in range(4)]
    q = np.zeros(400, dtype=np.uint32)
    for v in vecs:
        q += quantize(v, clip)
    back = dequantize_sum(q, clip, len(vecs))
    assert np.allclose(back, np.sum(vecs, axis=0), atol=1e-3)


def test_accountant_monotonic_and_calibrated():
    q, steps, delta = 0.05, 20, 1e-5
    e_small, _ = rdp_to_dp(compute_rdp(q, 0.6, steps), delta)
    e_big, _ = rdp_to_dp(compute_rdp(q, 4.0, steps), delta)
    assert e_big < e_small  # more noise -> smaller epsilon

    for target in (1.0, 5.0, 10.0):
        sigma = sigma_for_target_epsilon(q, steps, target, delta)
        got, _ = rdp_to_dp(compute_rdp(q, sigma, steps), delta)
        assert got <= target + 1e-2
