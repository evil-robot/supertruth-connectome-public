# Launch checklist (site page + paper), from the SEO and security seats, 20 Sep 2026

Order: results in → paper PDF final → JAS Zenodo upload (DOI) → flip CONNECTOME_PUBLISHED, set CONNECTOME_DOI, real dates,
RESULT sentences, fig1.png, viewer folder → PR → JAS merges (deploy = push to main) → the steps below.

1. Verify live HTML before any submission (all must be true):
   curl -s -A "Mozilla/5.0" https://supertruth.ai/research/connectome | grep -o '<link rel="canonical"[^>]*>\|<meta property="og:[a-z:]*"[^>]*>\|<title>[^<]*</title>'
   curl -s -A "Mozilla/5.0" https://supertruth.ai/research/connectome | grep -c '\[RESULT\|\[PUBLISH DATE\]\|\[DATE\]'   # must print 0
   curl -s https://supertruth.ai/sitemap.xml | grep -o '<url><loc>https://supertruth.ai/research/connectome</loc><lastmod>[^<]*'
   curl -s -o /dev/null -w '%{http_code}\n' https://supertruth.ai/research/connectome/opengraph-image
   curl -sI https://supertruth.ai/admin | grep -i -E 'x-frame-options|frame-ancestors'      # DENY + 'none'
   curl -sI https://supertruth.ai/research/connectome/viewer/connectome.html | grep -i -E 'x-frame|frame-ancestors|access-control'
2. IndexNow:
   curl -s -w '%{http_code}\n' -X POST https://api.indexnow.org/indexnow -H 'content-type: application/json' -d '{"host":"supertruth.ai","key":"2243fe04088544fda94743bf45afda8f","keyLocation":"https://supertruth.ai/2243fe04088544fda94743bf45afda8f.txt","urlList":["https://supertruth.ai/research/connectome","https://supertruth.ai/on-the-record","https://supertruth.ai/llms.txt"]}'
3. Bing Webmaster (key: memory bing-webmaster-api-key.md; siteUrl with trailing slash):
   curl -s -X POST "https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlBatch?apikey=$BING_WEBMASTER_API_KEY" -H 'content-type: application/json' -d '{"siteUrl":"https://supertruth.ai/","urlList":["https://supertruth.ai/research/connectome","https://supertruth.ai/on-the-record"]}'
   curl -s -X POST "https://ssl.bing.com/webmaster/api.svc/json/SubmitFeed?apikey=$BING_WEBMASTER_API_KEY" -H 'content-type: application/json' -d '{"siteUrl":"https://supertruth.ai/","feedUrl":"https://supertruth.ai/sitemap.xml"}'
4. Search Console (sc-domain:supertruth.ai): resubmit sitemap.xml; URL Inspection → Request indexing (UI only; house token lacks the webmasters write scope).
5. Add /research/connectome to PILLAR_PATHS in scripts/ga4-report.ts; define key events DOI click + viewer open; first traffic claim comes from `npx tsx scripts/ga4-report.ts` at +7 days, never a glance.
6. LinkedIn post (launch-copy.md §3) after the page is live and verified; pull baselines (April DTI post +7/+30, DTI page sessions, Zenodo views) BEFORE posting.
7. Re-run the awesome-fly "first" check on publish day; move the "as of" date on paper, page, press entry, post.

## Added 21 Sep (publish-day sequence, in order)
0. JAS picks the headline (launch-copy §10/§11) and the publish moment (after seed 2 lands, or now as provisional).
1. Final render: `uv run --project ~/Projects/ds-lab python scripts/render_results.py && ... scripts/splice_paper.py && cd paper && ./build.sh`; confirm seeds count and every "awaiting run" is gone or intended; grep em dashes 0, "[RUN:" list acceptable, no "[RESULT".
2. Zenodo, PAPER: upload paper/paper.pdf with paper/zenodo.json metadata (JAS's account, ORCID 0009-0001-6157-8100); note the DOI.
3. Re-run `.venv/bin/python scripts/package_dataset.py --verify-weights` with the paper DOI filled in dataset/zenodo-dataset.json; Zenodo, DATASET: upload dataset/*.gz, splits.json, README.md, MANIFEST.json; note the dataset DOI; add it to the paper (Data and Code Availability), zenodo.json (isSupplementedBy), README, page constant CONNECTOME_DATASET_DOI; rebuild the PDF; if Zenodo allows editing the paper record's files before publishing, replace the PDF with the DOI-bearing build; otherwise publish v1.0 and the DOI lands in v1.1.
4. Re-export the public code (`scripts/export_public.sh /tmp/stc-public`, commit, push) and flip evil-robot/supertruth-connectome-public to PUBLIC: `gh repo edit evil-robot/supertruth-connectome-public --visibility public --accept-visibility-change-consequences`. The working repo evil-robot/supertruth-connectome stays private.
5. Site: set CONNECTOME_DOI, CONNECTOME_DATASET_DOI, CONNECTOME_PUBLISH_DATE (real), CONNECTOME_UPDATED_DATE, byline date, press.ts headline (#2 or the chosen error-column headline) and date; flip CONNECTOME_PUBLISHED = true; the publish guard test must pass (no brackets); open the PR from feat/connectome-paper; JAS merges (deploy = push to main); then the curl checks, IndexNow, Bing, GSC steps above.
6. Press release: fill [ZENODO DOI], [DATASET DOI], [PUBLISH DATE], [SEARCH DATE] (re-run docs/FIRST-CLAIM-SEARCH.md first), examples-arm numbers if finished; Rheanna's title confirmed; boilerplate "proprietary".
7. LinkedIn post (launch-copy §3) with the final result sentence and the page URL; pull baselines first.
8. Teardown of st-connectome-preview = JAS's call, after the production page is verified.
