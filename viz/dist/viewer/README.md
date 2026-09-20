# viewer

Drop this folder at public/research/connectome/viewer/. Entry point: connectome.html. Data: points.bin (Float32 xyz in micrometres + Uint8 role, neurotransmitter class, position source), activity_frames.bin (8 Uint8 frames; the trained run replaces this file, same layout, or point data-frames on <main> at a new path), sample40k.bin (stratified 40,000 fallback), points_meta.json (counts, offsets, provenance). Address parameters for deep links and QA: ?view=roles|activity|nt, ?cam=dorsal|lateral|front|reset, ?step=1..8, ?sample=1 (force the 40,000 sample), ?full=1 (force the full set). Under 560 px of stage width the header compacts and the excitatory/inhibitory halves stack top and bottom; under 480 px the scale bar and orientation caption move under the canvas. The page posts its content height to the parent frame (connectome-viewer-height).

Serving notes: static files, relative paths only, no CDN, no external requests. The viewer runs inside a same-origin iframe with sandbox="allow-scripts" (opaque origin), so its relative fetches are CORS requests without credentials; the folder must send Access-Control-Allow-Origin: *. Cache-Control public, max-age 86400 is fine: rebuilding replaces files in place.

| file | bytes | sha256 |
|---|---:|---|
| connectome.html | 34,523 | 6a169a1df6c7bc6a4b667d4c4f50774e5148b84aa039319307a8d5e0ee3dbb98 |
| points.bin | 2,500,500 | 55d2b6a3af5ba05d60c54daeceb70b3cebb2452d9dbcb22942fc609b0d382bfb |
| activity_frames.bin | 1,333,600 | 9f7e94ceced1daa0287a5456e761089b82a91dbd66d55c0aa8bfe65e8ee5a1e2 |
| sample40k.bin | 160,000 | e297917c540c1762278cb2a1a06dfa0540bdfc417d0de2bcb93038cbad9a33c0 |
| points_meta.json | 2,457 | a8da83a581db9f5391b9ff4eaa10a36e1718b5d00ad6be045e96c482f35c3dcb |
| vendor/three.module.min.js | 687,458 | f7cee3c7533449a1505cc12cb5128b89e3d4fd3d7ea62b05f9f5464a217472ee |
| vendor/OrbitControls.js | 32,209 | 71a40d88a97d447d161fc8fbc4728f1499a66afa01306694f610dbfa30b9ccf0 |

Total: 4,750,747 bytes (4.75 MB). Ceilings: HTML under 2 MB, folder under 25 MB.

## Vendored libraries

- `vendor/three.module.min.js`: three.js 0.169.0, build/three.module.min.js from https://cdn.jsdelivr.net/npm/three@0.169.0/ (MIT)
- `vendor/OrbitControls.js`: three.js 0.169.0, examples/jsm/controls/OrbitControls.js (MIT); one edit: the import specifier 'three' rewritten to './three.module.min.js' so no import map is needed

Built by viz/build_dist.py on 20 Sep 2026 from the files in viz/.
