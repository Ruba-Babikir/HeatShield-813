"""Execute plain-Python notebook cells in a fresh process and preserve real outputs.

For the official Jupyter kernel check use the nbconvert command in README.md.
This runner uses no hidden notebook state and does not claim to be a Jupyter kernel.
"""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback

root=Path(__file__).resolve().parents[1]
notebook=root/'notebooks/02_main_analysis.ipynb'
nb=json.loads(notebook.read_text())
os.chdir(notebook.parent)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
scope={'__name__':'__main__'}
count=0
started=time.perf_counter()
for cell in nb['cells']:
    if cell['cell_type']!='code': continue
    count+=1;outputs=[];capture=io.StringIO()
    def show(*args,**kwargs):
        for num in plt.get_fignums():
            figure=plt.figure(num);data=io.BytesIO()
            figure.savefig(data,format='png',dpi=120,bbox_inches='tight')
            outputs.append({'output_type':'display_data','data':{'image/png':base64.b64encode(data.getvalue()).decode(),'text/plain':['<Matplotlib figure>']},'metadata':{}})
        plt.close('all')
    plt.show=show
    try:
        with contextlib.redirect_stdout(capture),contextlib.redirect_stderr(capture):
            exec(compile(''.join(cell['source']),f'notebook cell {count}','exec'),scope)
    except Exception:
        print(capture.getvalue());traceback.print_exc();sys.exit(1)
    if capture.getvalue(): outputs.insert(0,{'output_type':'stream','name':'stdout','text':capture.getvalue().splitlines(keepends=True)})
    cell['outputs']=outputs;cell['execution_count']=count
    print(f'Executed cell {count}')
seconds=time.perf_counter()-started
nb['metadata']['execution_verification']={'method':'fresh Python process, cells executed in order','jupyter_kernel_verified':False,'elapsed_seconds':round(seconds,2)}
notebook.write_text(json.dumps(nb,indent=1)+'\n')
(root/'UrbanCool_AI_Space_Hackathon.ipynb').write_bytes(notebook.read_bytes())
print(f'All {count} code cells completed in {seconds:.2f} seconds. Jupyter kernel validation is a separate check.')
