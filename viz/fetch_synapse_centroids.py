"""Per-neuron synapse centroid from the MaleCNS v1.0 syn-points table, streamed over HTTP range requests.

Why: 26,062 of the 166,700 graph neurons have no somaLocation in the body annotations (mostly sensory neurons,
whose cell bodies lie outside the imaged volume). Their synapse locations are inside the volume, so the centroid
of a neuron's synapses is a real, measured position for it. This script reads only the x, y, z, body columns of
gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/syn-points-male-cns-v1.0-minconf-0.5.feather (13.1 GB,
5,455 record batches) through the public HTTPS mirror and never writes the table to disk.

Output data/malecns/synapse_centroids.npz: body_id int64[N] (graph order), centroid_vox float64[N,3] (x,y,z in
8 nm voxels, NaN where the neuron has no synapse row), n_synapses int64[N].

Run:  .venv/bin/python viz/fetch_synapse_centroids.py [--workers 8] [--limit N_BATCHES]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "malecns"
URL = ("https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/"
       "syn-points-male-cns-v1.0-minconf-0.5.feather")
OUT = DATA / "synapse_centroids.npz"


class HttpRangeFile:
    """Minimal seekable read-only file over HTTP range requests, for pyarrow.PythonFile."""

    def __init__(self, url: str, session: requests.Session, stats: dict):
        self.url, self.s, self.stats = url, session, stats
        self.size = int(session.head(url, timeout=60).headers["Content-Length"])
        self.pos = 0

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0:
            return b""
        end = min(self.pos + n, self.size) - 1
        for attempt in range(6):
            try:
                r = self.s.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=120)
                r.raise_for_status()
                data = r.content
                break
            except Exception as e:  # network hiccup: back off and retry
                if attempt == 5:
                    raise
                time.sleep(2 ** attempt)
        self.pos += len(data)
        self.stats["bytes"] = self.stats.get("bytes", 0) + len(data)
        self.stats["requests"] = self.stats.get("requests", 0) + 1
        return data

    def close(self):
        pass

    @property
    def closed(self):
        return False

    def readable(self):
        return True

    def seekable(self):
        return True

    def writable(self):
        return False

    def flush(self):
        pass


def worker(k: int, workers: int, ids: np.ndarray, limit: int, acc: dict, lock: threading.Lock, stats: dict):
    try:
        _worker(k, workers, ids, limit, acc, lock, stats)
    except Exception as e:  # surface thread failures instead of dying silently
        import traceback
        traceback.print_exc()
        with lock:
            stats["failed_workers"] = stats.get("failed_workers", 0) + 1


def _worker(k: int, workers: int, ids: np.ndarray, limit: int, acc: dict, lock: threading.Lock, stats: dict):
    s = requests.Session()
    f = HttpRangeFile(URL, s, stats)
    reader = ipc.open_file(pa.PythonFile(f, mode="r"),
                           options=ipc.IpcReadOptions(included_fields=[0, 1, 2, 6]))  # z, y, x, body
    nb = reader.num_record_batches if limit <= 0 else min(limit, reader.num_record_batches)
    n = len(ids)
    sx = np.zeros(n); sy = np.zeros(n); sz = np.zeros(n); cnt = np.zeros(n, dtype=np.int64)
    for i in range(k, nb, workers):
        b = reader.get_batch(i)
        body = b.column("body").to_numpy()
        idx = np.searchsorted(ids, body)
        idx[idx >= n] = 0
        keep = ids[idx] == body
        if not keep.any():
            continue
        idx = idx[keep]
        x = b.column("x").to_numpy()[keep].astype(np.float64)
        y = b.column("y").to_numpy()[keep].astype(np.float64)
        z = b.column("z").to_numpy()[keep].astype(np.float64)
        sx += np.bincount(idx, weights=x, minlength=n)
        sy += np.bincount(idx, weights=y, minlength=n)
        sz += np.bincount(idx, weights=z, minlength=n)
        cnt += np.bincount(idx, minlength=n)
        with lock:
            stats["batches"] = stats.get("batches", 0) + 1
    with lock:
        acc["sx"] += sx; acc["sy"] += sy; acc["sz"] += sz; acc["cnt"] += cnt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="only the first N record batches (throughput test)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    g = np.load(DATA / "graph.npz", allow_pickle=False)
    ids = g["body_id"].astype(np.int64)
    assert (np.diff(ids) > 0).all(), "body_id must be sorted for searchsorted"
    n = len(ids)
    acc = {"sx": np.zeros(n), "sy": np.zeros(n), "sz": np.zeros(n), "cnt": np.zeros(n, dtype=np.int64)}
    stats: dict = {}
    lock = threading.Lock()
    t0 = time.time()
    threads = [threading.Thread(target=worker, args=(k, args.workers, ids, args.limit, acc, lock, stats), daemon=True)
               for k in range(args.workers)]
    for t in threads:
        t.start()
    total = args.limit if args.limit > 0 else 5455
    while any(t.is_alive() for t in threads):
        time.sleep(15)
        done = stats.get("batches", 0)
        dt = time.time() - t0
        print(f"  {done}/{total} batches  {stats.get('bytes', 0) / 1e6:,.0f} MB  {stats.get('requests', 0)} requests  "
              f"{dt:.0f}s  eta {dt / max(done, 1) * (total - done) / 60:.1f} min", file=sys.stderr, flush=True)
    for t in threads:
        t.join()
    cnt = acc["cnt"]
    with np.errstate(invalid="ignore", divide="ignore"):
        cen = np.stack([acc["sx"] / cnt, acc["sy"] / cnt, acc["sz"] / cnt], axis=1)
    cen[cnt == 0] = np.nan
    meta = {"source": URL, "record_batches_read": int(stats.get("batches", 0)), "bytes_read": int(stats.get("bytes", 0)),
            "neurons_with_synapses": int((cnt > 0).sum()), "n_neurons": int(n), "units": "8 nm voxels",
            "seconds": round(time.time() - t0, 1), "limit": args.limit}
    np.savez_compressed(args.out, body_id=ids, centroid_vox=cen, n_synapses=cnt, meta=json.dumps(meta))
    print(json.dumps(meta, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
