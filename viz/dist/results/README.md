# results

The arms-comparison page. results_charts.html reads results.sample.json (all null: 'awaiting run') until results.json from the run is dropped beside it and data-results on <main> (or ?results=) points to it. Schema: results.schema.json.

Serving notes: static files, relative paths only, no CDN, no external requests. The viewer runs inside a same-origin iframe with sandbox="allow-scripts" (opaque origin), so its relative fetches are CORS requests without credentials; the folder must send Access-Control-Allow-Origin: *. Cache-Control public, max-age 86400 is fine: rebuilding replaces files in place.

| file | bytes | sha256 |
|---|---:|---|
| results_charts.html | 10,167 | 0f3e3e22eaf44e3b5422d81e763220d2a7dfb2b9dd95da2be7ff83f4aea3f923 |
| results.schema.json | 2,918 | 30f658a767e718fd4fa2b90445e1a3c387f5360763e51a0e929543a2834746a8 |
| results.sample.json | 5,909 | 95acdb538b7e3b7dd096a8f556056d1c567c89b271a3d1f0579563ffd237d3aa |
| vendor/plotly-basic.min.js | 1,071,091 | 138c2e81014b979dc00867a93da55b7605a17495ee78dd7afb433b7f021dfcfa |

Total: 1,090,085 bytes (1.09 MB). Ceilings: HTML under 2 MB, folder under 25 MB.

## Vendored libraries

- `vendor/plotly-basic.min.js`: plotly.js-basic-dist-min 2.35.2 from https://cdn.jsdelivr.net/npm/plotly.js-basic-dist-min@2.35.2/ (MIT)

Built by viz/build_dist.py on 20 Sep 2026 from the files in viz/.
