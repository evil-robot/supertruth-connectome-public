# Intelligence Is Structure, Not Scale

Code and derived data for the SuperTruth whitepaper *A Whole Central Nervous System Connectome as a Fixed Substrate
for Scoring Health Data Trust* (Jason Alan Snyder, SuperTruth Inc., September 2026). Paper: `paper/paper.pdf`
(built from `paper/paper.md` with `paper/build.sh`). Zenodo DOI: to be added at deposit.

**What this is.** The MaleCNS v1.0 fruit fly connectome (166,700 neurons, 6,242,118 connections of five or more
synapses) held fixed as a signed recurrent graph. Only per-connection gains, per-neuron biases and leaks, an input
projection into the sensory neurons, and a readout from the descending and motor neurons are trained. The task is to
reproduce SuperTruth's Data Trust Index on synthetic health records and VIGIL's Behavioral Integrity Index on
synthetic agent event windows, against a degree-preserving shuffle, a random graph at matched density, a network
with the same number of trainable parameters, a linear readout, and four frontier models given the published DTI
paper. Every record is synthetic. No real person's data was used.

**Layout.** `data/` build the graph from the public release (`build_graph.py`; the 1 GB release table is not
committed). `flytrust/` model, controls, deterministic edge ops, trainer. `teachers/` synthetic record and window
generators, feature specs, QA (label files not committed; hashes in `MANIFEST.md`). `llm_arm/` the four-vendor
comparison runner (keys read from the environment, never committed). `scripts/` splits, adversary tests, runs, results
rendering, paper splice. `viz/` the interactive viewer and figures. `docs/` the pre-registered protocol, its dated
amendment, decision rules, and decision log. `paper/` the manuscript.

**Reproduce.** Python 3.12 venv at `.venv` (`requirements.txt`, torch with Metal on Apple silicon); pandas and plotting
through the `ds-lab` environment described in `docs/`. `data/README.md` has the download commands; `teachers/MANIFEST.md`
the exact teacher commands and pins; `docs/PROTOCOL.md` the design; `scripts/run_pilot.sh` the run driver;
`scripts/render_results.py` and `scripts/splice_paper.py` rebuild Section 4 and the page sentences from `runs/`.

**Licenses and release.** Code MIT. Derived graph, paper, and dataset CC BY 4.0 with the attribution in the paper. Released:
all synthetic records and features, all DTI engine labels, the DTI-trained parameters (Zenodo dataset, https://doi.org/10.5281/zenodo.22865020).
Held: BII scores, BII-trained parameters, and the BII feature specification (unpublished work), and the teacher engines.
We have released everything that does not expose SuperTruth's intellectual property; write to jas@supertruth.ai about the
rest. See `LICENSE`.

**About this public copy.** This is a clean export of the working repository at the commit named in `dataset/MANIFEST.json`.
Held back from the export: the Behavioral Integrity Index feature specification and window generator (unpublished work) and
the raw language-model call logs (kept privately as the substantiation record). Everything else is here.
