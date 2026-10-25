"""Etap 7. Typologia modeli lokalnej polityki mieszkaniowej (RQ6) — odległość Gowera + klasteryzacja hierarchiczna,
dobór liczby grup (silhouette) i stabilność (ARI na podpróbach). Wyniki są punktem wyjścia do interpretacji
i do analiz komplementarnych (QCA / LCA w R), nie „odpowiedzią” samą w sobie."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.metrics import adjusted_rand_score, silhouette_score


def gower_distance(df: pd.DataFrame, num: list[str], cat: list[str], weights: dict[str, float] | None = None) -> np.ndarray:
    n = len(df)
    w = weights or {}
    num_sum = np.zeros((n, n))
    den = np.zeros((n, n))
    for c in num:
        x = pd.to_numeric(df[c], errors="coerce").to_numpy(float)
        rng = np.nanmax(x) - np.nanmin(x)
        if not np.isfinite(rng) or rng == 0:
            continue
        d = np.abs(x[:, None] - x[None, :]) / rng
        m = (~np.isnan(x))[:, None] & (~np.isnan(x))[None, :]
        num_sum += np.where(m, d, 0) * w.get(c, 1.0)
        den += m * w.get(c, 1.0)
    for c in cat:
        x = df[c].astype("object").where(df[c].notna(), None).to_numpy()
        present = np.array([v is not None for v in x])
        d = (x[:, None] != x[None, :]).astype(float)
        m = present[:, None] & present[None, :]
        num_sum += np.where(m, d, 0) * w.get(c, 1.0)
        den += m * w.get(c, 1.0)
    D = np.divide(num_sum, den, out=np.full_like(num_sum, np.nan), where=den > 0)
    np.fill_diagonal(D, 0)
    # braki całkowite (brak wspólnych cech) -> odległość maksymalna, aby nie psuć klasteryzacji
    D = np.where(np.isnan(D), np.nanmax(D), D)
    return (D + D.T) / 2


def cluster_labels(D: np.ndarray, k: int, method: str = "average") -> np.ndarray:
    Z = linkage(squareform(D, checks=False), method=method)
    return fcluster(Z, k, criterion="maxclust")


def scan_k(D: np.ndarray, k_range=range(2, 9), method="average", n_boot=200, frac=0.8, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(D)
    out = []
    for k in k_range:
        lab = cluster_labels(D, k, method)
        sil = silhouette_score(D, lab, metric="precomputed") if 1 < len(set(lab)) < n else np.nan
        aris = []
        for _ in range(n_boot):
            idx = rng.choice(n, int(frac * n), replace=False)
            sub = cluster_labels(D[np.ix_(idx, idx)], k, method)
            aris.append(adjusted_rand_score(lab[idx], sub))
        out.append(dict(k=k, silhouette=sil, stability_ari=float(np.mean(aris)), min_cluster_size=int(np.bincount(lab)[1:].min())))
    return pd.DataFrame(out)


def profile(df: pd.DataFrame, labels: np.ndarray, num: list[str], cat: list[str]) -> pd.DataFrame:
    d = df.copy()
    d["cluster"] = labels
    parts = [d.groupby("cluster")[num].median().T.add_prefix("med_")] if num else []
    for c in cat:
        parts.append(d.groupby("cluster")[c].agg(lambda s: f"{s.mode().iat[0]} ({(s == s.mode().iat[0]).mean():.0%})" if s.notna().any() else "NA").to_frame(c).T)
    return pd.concat(parts + [d.groupby("cluster").size().rename("n").to_frame().T])


def heatmap(df: pd.DataFrame, labels: np.ndarray, num: list[str], path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    z = df[num].apply(pd.to_numeric, errors="coerce")
    z = (z - z.mean()) / z.std(ddof=0)
    m = z.groupby(labels).mean().T
    fig, ax = plt.subplots(figsize=(1.2 * m.shape[1] + 4, 0.38 * m.shape[0] + 1.5))
    im = ax.imshow(m.values, cmap="RdBu_r", vmin=-2, vmax=2, aspect="auto")
    ax.set_xticks(range(m.shape[1]), [f"Typ {c}" for c in m.columns]); ax.set_yticks(range(m.shape[0]), m.index, fontsize=8)
    fig.colorbar(im, ax=ax, label="z-score (średnia w grupie)"); fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)
