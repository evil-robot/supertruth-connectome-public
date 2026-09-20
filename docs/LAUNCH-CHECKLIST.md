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
