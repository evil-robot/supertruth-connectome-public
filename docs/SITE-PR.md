# Site PR text (feat/connectome-paper → main), to open at publish

Title: Research page: connectome whitepaper (/research/connectome)

Body:
Adds the public page for the connectome whitepaper at /research/connectome with the interactive viewer, Figure 1, the
prologue and purpose sections, the first-seed results, intended use, conflict of interest, non-affiliation, and attribution.

Security (reviewed by the security seat, all three conditions met): CONNECTOME_PUBLISHED switch gates the page, press
entry, sitemap, OG image, and llms.txt; global frame headers stay DENY + frame-ancestors 'none' with two per-route
exceptions (the page may open a same-origin frame; the viewer folder may be framed by same origin, serves ACAO * and a
24-hour cache); the viewer iframe is sandboxed (allow-scripts only) with no-referrer; the viewer route's connect-src names
our hosts so WebKit loads data under the sandbox; Dockerfile passes PREVIEW_NOINDEX to the build. Headers test added.

SEO (reviewed by the seo seat): server-rendered prose under one h1; canonical on the page; OG image; ScholarlyArticle
JSON-LD from constants only (author with ORCID sameAs, publisher, license, citations, isBasedOn, about, isPartOf,
dateModified); sitemap entry with the true dates; internal links to the DTI glossary, DTI engine, and VIGIL pages; llms.txt
entry; title under 60 with "connectome"; description 155 characters; publish guard test fails on any leftover placeholder.

Verification: tsc clean; vitest 22 files, 138 passed; rendered on the Macly box in Chromium and WebKit at 1440 and 390,
zero console errors, figure at intrinsic size, viewer painted in both engines, mobile layout stacked.

Flip list done in this PR: CONNECTOME_PUBLISHED=true; CONNECTOME_DOI, CONNECTOME_DATASET_DOI set; publish and updated
dates real; byline date; press entry headline/date; LLMS_UPDATED bumped.

After merge (deploy = push to main): docs/LAUNCH-CHECKLIST.md steps 1 to 5 (curl checks, IndexNow, Bing, GSC).

Follow-up (seo seat, 20 Sep 2026): the viewer's .bin assets (points.bin, sample40k.bin, activity_frames.bin) are served by
Next's static file handler without content-encoding, and Next does not serve precompressed copies from public/. Compress
them at the edge (CDN) or move them behind a Route Handler that gzips. Not blocking: the viewer now loads on a click,
so the assets are not on the initial page load.
