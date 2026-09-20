# MaleCNS v1.0 data

Male *Drosophila melanogaster* central nervous system connectome (brain + ventral nerve cord),
released 2026 by FlyEM (HHMI Janelia) with the University of Cambridge, MRC LMB and Google Research.
Only MaleCNS is used here. No FlyWire/FAFB data and no non-commercial data.

## License

Data: **CC-BY 4.0**. The download page (https://male-cns.janelia.org/download/) states:
"The Male CNS is licensed under CC-BY." and "The Male CNS dataset is licensed under CC-BY."
(https://creativecommons.org/licenses/by/4.0/). Attribution to the papers below is the only requirement.

## Citation

Published paper (metadata verified via Crossref on 2026-09-20):

> Berg, S., Beckett, I. R., Costa, M., Schlegel, P., Januszewski, M., Marin, E. C., Nern, A., Preibisch, S., et al.
> (2026). Sexual dimorphism in the complete *Drosophila* male central nervous system connectome.
> *Cell*, 189(18), 5504–5526.e15. https://doi.org/10.1016/j.cell.2026.08.015

Preprint of the same work:

> Berg, S., Beckett, I. R., Costa, M., Schlegel, P., Januszewski, M., Marin, E. C., Nern, A., et al. (2025).
> Sexual dimorphism in the complete connectome of the *Drosophila* male central nervous system.
> *bioRxiv* 2025.10.09.680999. https://doi.org/10.1101/2025.10.09.680999

Dataset: MaleCNS v1.0, https://male-cns.janelia.org/ ; neuPrint dataset `male-cns:v1.0`
(https://neuprint.janelia.org/?dataset=male-cns%3Av1.0). Per the download page, the per-body
neurotransmitter predictions are described in the manuscript's methods section; no separate
neurotransmitter paper is named there.

## Files downloaded (2026-09-20)

Public Google Cloud Storage bucket, no auth: `gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/`
(HTTPS: `https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/<file>`).
All three files were checked against the bucket's md5 after download.

| File | Bytes | sha256 |
|---|---:|---|
| body-annotations-male-cns-v1.0-minconf-0.5.feather | 14,483,314 | 2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2 |
| body-neurotransmitters-male-cns-v1.0.feather | 43,282,834 | 95c9289220663abeb3409f3ad9e5a7f8a53f8093f5139d15502cd08da8879621 |
| connectome-weights-male-cns-v1.0-minconf-0.5.feather | 1,051,241,946 | e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1 |

Other files in the bucket, not downloaded: `body-stats-...` (778 MB), `connectome-weights-...-significant-only`
(502 MB) and `...-traced-only` (508 MB, both undocumented on the download page), `syn-partners-...` (2.9 to 6.8 GB),
`tbar-neurotransmitters-...` (2.65 GB), `syn-points-...` (13.1 GB).

Columns used: annotations `bodyId, superclass, class, type, somaSide`; neurotransmitters
`body, consensus_nt, predicted_nt_confidence`; weights `body_pre, body_post, weight`.

## Commands

```bash
cd ~/Projects/supertruth-connectome
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install torch numpy scipy pandas pyarrow safetensors requests tqdm
.venv/bin/python -m pip freeze > requirements.txt          # pinned versions live there

B=https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome
cd data/malecns
for f in body-annotations-male-cns-v1.0-minconf-0.5.feather \
         body-neurotransmitters-male-cns-v1.0.feather \
         connectome-weights-male-cns-v1.0-minconf-0.5.feather; do
  curl -sS -L -C - -o "$f" "$B/$f"
done
cd ../..
.venv/bin/python data/build_graph.py --threshold 5         # writes data/malecns/graph.npz + graph_meta.json
```

## graph.npz layout

Neurons = annotation rows with a non-null `superclass`, sorted by `bodyId`; index = position in `body_id`.
CSR is presynaptic (row) to postsynaptic (column).

| key | dtype | meaning |
|---|---|---|
| body_id | int64[N] | MaleCNS body id |
| superclass, cell_class, cell_type, soma_side | str[N] | from annotations ("" where missing) |
| nt_label | str[N] | `consensus_nt` ("unclear" where missing) |
| nt_confidence | float32[N] | `predicted_nt_confidence` |
| nt_sign_neuron | int8[N] | +1 acetylcholine; -1 gaba/glutamate/histamine; 0 modulatory or unclear |
| nt_class_neuron | int8[N] | 0 excitatory, 1 inhibitory, 2 modulatory (DA/OA/5-HT), 3 unclear |
| indptr | int64[N+1] | CSR row pointer |
| indices | int32[E] | postsynaptic neuron index |
| syn_count | int32[E] | synapse count (weight) |
| edge_sign | int8[E] | sign applied to each edge (see below) |
| threshold | int32 | minimum synapse count kept |
| modulatory_policy, unclear_policy | str | how 0-sign presynaptic neurons were signed |

Sign rule (Dale's law, presynaptic neuron's consensus NT): acetylcholine excitatory (+1);
GABA, glutamate and histamine inhibitory (-1) in the fly (Glu mostly through GluCl, His through HisCl).
Dopamine, octopamine and serotonin are modulatory and have no fixed sign; by default their edges are
kept and signed +1 (`--modulatory plus`, the nfly convention), as are edges from neurons with an
unclear prediction (`--unclear plus`). Use `--modulatory zero --unclear zero` to zero those edges
instead (the drosophila-brain-mlx / mps-malecns-model convention), or mask them with `nt_class_neuron`.

## Summary at threshold 5 (from `graph_meta.json`, produced by build_graph.py)

- Neurons: 166,700 (of 211,577 bodies in the annotation table); 11,751 distinct `type` labels
- Weights table: 151,856,684 rows over all bodies; 25,582,938 neuron-to-neuron rows (124,177,617 synapses) at any weight
- Edges with >= 5 synapses: 6,242,118 carrying 89,860,280 synapses; 0 duplicate pairs
- Edges excitatory 62.80%, inhibitory 37.20% (by count); 61.96% of synapses excitatory
- Edges from known ACh/GABA/Glu/His presynaptic neurons 97.72%; from modulatory 0.80%; from unclear 1.48%
- 864 neurons have no edge in either direction at this threshold
- Out-degree quantiles (0, 5, 25, 50, 75, 95, 99, 100%): 0, 2, 14, 25, 43, 107, 226, 7570
- In-degree quantiles: 0, 2, 10, 19, 39, 132, 279, 6660
- NT labels: acetylcholine 103,720; glutamate 29,302; gaba 22,069; histamine 7,891; unclear 3,177; dopamine 392; octopamine 101; serotonin 48
- Sensory (superclass in *_sensory, sensory_ascending/descending, incl. _tbc) 17,937; descending 1,316; motor (vnc_motor + cb_motor) 815
