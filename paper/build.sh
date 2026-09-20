#!/bin/zsh
# Reproduces the DTI paper's build: pandoc standalone HTML (default pandoc CSS) → headless Chrome PDF.
set -euo pipefail
cd "$(dirname "$0")"
pandoc paper.md -s --metadata title="" -o paper.html
# strip pandoc's auto <header> title block so the markdown H1 is the visible title, as in the DTI paper
/opt/homebrew/bin/python3.12 - <<'PY'
import re;p='paper.html';s=open(p).read()
s=re.sub(r'<header id="title-block-header">.*?</header>\n?','',s,flags=re.S);s=s.replace('<title></title>','<title>paper</title>')
# pandoc's default CSS makes tables display:block with overflow-x:auto, which Chrome's print clips at the right margin;
# render them as real tables that wrap to the page width. Results tables (render_results.py) carry at most six data columns
# and print at 9pt with no mid-word breaks (table.narrow); a table wider than seven columns (the Section 3.8 vendor table)
# keeps the break-anywhere fallback so it cannot run off the page (table.wide).
def classify(m):
    head=re.search(r'<tr[^>]*>(.*?)</tr>',m.group(0),flags=re.S)
    n=len(re.findall(r'<th\b',head.group(1))) if head else 0
    t=re.sub(r'^<table[^>]*>','<table class="%s">'%('narrow' if n<=7 else 'wide'),m.group(0),count=1)
    if n<=7:
        t=re.sub(r'<colgroup>.*?</colgroup>','',t,flags=re.S)  # pandoc's equal-width hint from the dash row is not a layout  # a number is never broken across lines: cells without letters keep to one line, so width flows to the label columns
        t=re.sub(r'<td([^>]*)>([^<]*)</td>',lambda c:c.group(0) if re.search(r'[A-Za-z]',c.group(2)) or not c.group(2).strip() else '<td class="nw"%s>%s</td>'%(c.group(1),c.group(2)),t)
        # a label column with long labels gets a quarter of the width up front; Chrome's auto layout would otherwise share the slack out to the number columns
        first=[re.sub(r'<[^>]+>','',c) for c in re.findall(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>',t,flags=re.S)]
        if first and max(len(c.strip()) for c in first)>16:
            t=t.replace('>','><colgroup><col style="width:25%"></colgroup>',1)
    return t
s=re.sub(r'<table[^>]*>.*?</table>',classify,s,flags=re.S)
css=('table{display:table;width:100%;table-layout:auto;font-size:9pt;line-height:1.25;overflow-x:visible;border-collapse:collapse}'
     'th{vertical-align:bottom}td{vertical-align:top}tr{break-inside:avoid}'
     'table.narrow td,table.narrow th{overflow-wrap:normal;word-break:keep-all;hyphens:none}'
     'table.wide td,table.wide th{overflow-wrap:anywhere;hyphens:auto}td.nw{white-space:nowrap}')
s=s.replace('</head>','<style>'+css+'</style>\n</head>',1)
open(p,'w').write(s)
PY
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$PWD/paper.pdf" "file://$PWD/paper.html" 2>/dev/null
mdls -name kMDItemNumberOfPages paper.pdf
