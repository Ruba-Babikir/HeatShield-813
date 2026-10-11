"""Check repository completeness without claiming platform eligibility."""
from pathlib import Path
import json
import re

root=Path(__file__).resolve().parents[1]
required=['README.md','requirements.txt','notebooks/02_main_analysis.ipynb','data/sample_input/satellite_cells.csv','results/priority_map.png','results/interactive_priority_map.html','docs/slides.pdf']
for name in required:
    p=root/name
    assert p.is_file() and p.stat().st_size>0,f'Missing or empty: {name}'
for line in (root/'requirements.txt').read_text().splitlines():
    if line and not line.startswith('#'): assert re.fullmatch(r'[A-Za-z0-9_.-]+==[0-9][A-Za-z0-9_.+-]*',line),line
for file in [root/'notebooks/02_main_analysis.ipynb',*(root/'executed-notebooks').glob('*.ipynb')]:
    nb=json.loads(file.read_text());codes=[c for c in nb['cells'] if c['cell_type']=='code']
    assert codes and all(c.get('execution_count') is not None for c in codes)
    assert not any(o.get('output_type')=='error' for c in codes for o in c.get('outputs',[]))
    assert all('/content/drive' not in ''.join(c['source']) for c in codes)
readme=(root/'README.md').read_text()
assert 'results/priority_map.png' in readme
assert len(re.findall(r'^## [0-9]+\.',readme,re.M))==10
print('Repository file checks passed. File completeness only: repository access, workflow verification and submission-form checks remain separate. Restricted boundary polygons are excluded; their publication is not authorised.')
