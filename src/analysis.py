"""HeatShield 813 analysis of a prepared, independently defined satellite sample."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from sklearn.dummy import DummyRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

SEED = 42
BANDS = [f"B{x}_mean_reflectance" for x in ['02','03','04','08','11','12']]
INDICES = ['ndvi','ndbi','mndwi','bsi']
FEATURES = BANDS + INDICES
COLORS = {'Higher':'#C6533E','Medium':'#DFA747','Lower':'#4D858C','No usable heat data':'#D6D9D5'}

def load_sample(path):
    df=pd.read_csv(path)
    required=['cell_id','x_m','y_m','lst_mean_c','valid','landsat_id','sentinel_id','landsat_date_utc','sentinel_date_utc']+BANDS
    if set(required)-set(df): raise ValueError('Sample is missing required columns.')
    if df.cell_id.duplicated().any(): raise ValueError('Duplicate sample cells.')
    if len(df)!=100 or df.x_m.nunique()!=10 or df.y_m.nunique()!=10:
        raise ValueError('Expected the documented 10 by 10 sample grid.')
    for col in ['landsat_date_utc','sentinel_date_utc']:
        df[col]=pd.to_datetime(df[col],utc=True,errors='raise')
    values=df.valid.astype(str).str.lower().map({'true':True,'false':False})
    if values.isna().any(): raise ValueError('Invalid quality flags.')
    df['valid']=values
    if df.landsat_date_utc.dt.normalize().nunique()!=1:
        raise ValueError('This example expects one date. Redesign temporal validation before adding dates.')
    return df

def derive_features(df):
    df=df.copy()
    def nd(a,b):
        denom=a+b
        return (a-b).where(np.abs(denom)>1e-10)/denom.where(np.abs(denom)>1e-10)
    b={x:df[f'B{x}_mean_reflectance'] for x in ['02','03','04','08','11','12']}
    df['ndvi']=nd(b['08'],b['04'])
    df['ndbi']=nd(b['11'],b['08'])
    df['mndwi']=nd(b['03'],b['11'])
    df['bsi']=nd(b['11']+b['04'],b['08']+b['02'])
    df['surface_usable']=np.isfinite(df[FEATURES]).all(axis=1)&df[BANDS].ge(0).all(axis=1)&df[BANDS].le(1).all(axis=1)
    df['heat_usable']=df.valid & np.isfinite(df.lst_mean_c)
    median=df.loc[df.heat_usable,'lst_mean_c'].median()
    df['relative_temp_c']=df.lst_mean_c.where(df.heat_usable)-median
    return df

def grid_values(df,field):
    xs=np.sort(df.x_m.unique());ys=np.sort(df.y_m.unique())
    grid=df.pivot(index='y_m',columns='x_m',values=field).reindex(index=ys,columns=xs).to_numpy(dtype=float)
    return np.ma.masked_invalid(grid),[xs.min()-50,xs.max()+50,ys.min()-50,ys.max()+50]

def plot_grid(df,field,title,unit,output,cmap='inferno',vmin=None,vmax=None):
    grid,extent=grid_values(df,field)
    cm=plt.get_cmap(cmap).copy();cm.set_bad('#D6D9D5')
    fig,ax=plt.subplots(figsize=(8,6.2),layout='constrained')
    im=ax.imshow(grid,origin='lower',extent=extent,cmap=cm,vmin=vmin,vmax=vmax,interpolation='nearest')
    ax.set(title=title,xlabel='Easting (m), EPSG:32640',ylabel='Northing (m)')
    ax.ticklabel_format(style='plain',useOffset=False)
    ax.set_aspect('equal');fig.colorbar(im,ax=ax,label=unit,shrink=.82)
    fig.savefig(output,dpi=180)
    return fig

def rank_priorities(df):
    df=df.copy();good=df.heat_usable;v=df.loc[good,'lst_mean_c']
    df['priority_score']=np.nan
    df.loc[good,'priority_score']=100*(v.rank(method='average')-.5)/len(v)
    df['priority']=np.select([~good,df.priority_score.ge(90),df.priority_score.ge(75)],['No usable heat data','Higher','Medium'],default='Lower')
    df['priority_rank']=df.priority_score.rank(method='min',ascending=False).astype('Int64')
    for q in [.85,.90,.95]: df[f'hot_q{int(q*100)}']=good&df.lst_mean_c.ge(v.quantile(q))&df.relative_temp_c.gt(0)
    actions=[]
    for row in df.itertuples():
        proposed=[]
        if not row.heat_usable: proposed=['Acquire or review observations']
        elif row.priority=='Lower': proposed=['Monitor on additional dates and check site use']
        elif not row.surface_usable: proposed=['Inspect surface cover before selecting a measure']
        else:
            proposed=['Assess shade where people walk or work outdoors']
            if row.ndvi<.2: proposed.append('Assess planting feasibility, water needs and maintenance')
            if row.ndbi>0 or row.bsi>0:
                proposed+=['Assess reflective roof options only after confirming a roof','Assess cooler pavements only after confirming paving']
        actions.append('; '.join(proposed))
    df['candidate_actions']=actions
    df['evidence_confidence']='Provisional: one observation day'
    df['priority_reason']=df.apply(lambda r: f"Observed relative surface temperature {r.relative_temp_c:+.2f} C; within-window heat percentile {r.priority_score:.1f}. Persistence is not established." if r.heat_usable else 'No usable heat observation.',axis=1)
    return df

def plot_priority(df,output):
    order=['Lower','Medium','Higher','No usable heat data']
    d=df.copy();d['tier_code']=d.priority.map({x:i for i,x in enumerate(order)})
    grid,extent=grid_values(d,'tier_code')
    fig,ax=plt.subplots(figsize=(8,6.2),layout='constrained')
    im=ax.imshow(grid,origin='lower',extent=extent,cmap=ListedColormap([COLORS[x] for x in order]),norm=BoundaryNorm(np.arange(-.5,4.5),4),interpolation='nearest')
    ax.set(title='Provisional assessment priorities | 11 June 2026',xlabel='Easting (m), EPSG:32640',ylabel='Northing (m)')
    ax.ticklabel_format(style='plain',useOffset=False)
    cb=fig.colorbar(im,ax=ax,ticks=range(4),shrink=.82);cb.ax.set_yticklabels(order)
    fig.savefig(output,dpi=180)
    return fig

def validate_models(df,output):
    output=Path(output)
    d=df.loc[df.heat_usable&df.surface_usable].copy().reset_index(drop=True)
    cols=np.sort(d.x_m.unique());groups={x:i for i,xs in enumerate(np.array_split(cols,4)) for x in xs}
    d['fold']=d.x_m.map(groups)
    plan=[];metrics=[];predictions=[];membership=[]
    for fold in range(4):
        test=d.index[d.fold.eq(fold)].to_numpy()
        dist=NearestNeighbors(n_neighbors=1).fit(d.loc[test,['x_m','y_m']]).kneighbors(d[['x_m','y_m']])[0].ravel()
        train=d.index[dist>200].to_numpy()
        if len(train)<20 or len(test)<10: raise ValueError('Insufficient data for the documented spatial test.')
        assert not set(d.loc[train,'cell_id']) & set(d.loc[test,'cell_id'])
        assert dist[train].min()>200
        plan.append({'fold':fold+1,'train_n':len(train),'test_n':len(test),'minimum_training_distance_m':float(dist[train].min())})
        mem=d[['cell_id']].copy();mem['fold']=fold+1;mem['role']='buffer_excluded';mem.loc[train,'role']='train';mem.loc[test,'role']='test';membership.append(mem)
        reference=d.loc[train,'lst_mean_c'].median()
        ytrain=d.loc[train,'lst_mean_c']-reference;ytest=d.loc[test,'lst_mean_c']-reference
        models={'Mean baseline':DummyRegressor(strategy='mean'),'Linear regression':make_pipeline(StandardScaler(),LinearRegression()),'Random forest':RandomForestRegressor(n_estimators=200,max_depth=8,min_samples_leaf=5,random_state=SEED,n_jobs=1)}
        for name,m in models.items():
            m.fit(d.loc[train,FEATURES],ytrain);p=m.predict(d.loc[test,FEATURES])
            metrics.append({'model':name,'fold':fold+1,'train_n':len(train),'test_n':len(test),'MAE_C':mean_absolute_error(ytest,p),'RMSE_C':np.sqrt(mean_squared_error(ytest,p)),'R2':r2_score(ytest,p)})
            predictions.extend({'cell_id':d.at[i,'cell_id'],'model':name,'fold':fold+1,'observed_relative_c':float(ytest.loc[i]),'predicted_relative_c':float(v),'training_reference_median_c':float(reference)} for i,v in zip(test,p))
    met=pd.DataFrame(metrics)
    summary=met.groupby('model',sort=False).agg(folds=('fold','nunique'),test_cells=('test_n','sum'),MAE_mean_C=('MAE_C','mean'),MAE_min_C=('MAE_C','min'),MAE_max_C=('MAE_C','max'),RMSE_mean_C=('RMSE_C','mean'),R2_mean=('R2','mean')).reset_index()
    pd.DataFrame(plan).to_csv(output/'validation_plan.csv',index=False)
    pd.concat(membership).to_csv(output/'split_membership.csv',index=False)
    pd.DataFrame(predictions).to_csv(output/'heldout_predictions.csv',index=False)
    met.to_csv(output/'validation_by_fold.csv',index=False);summary.to_csv(output/'validation_summary.csv',index=False)
    return met,summary

def plot_validation(summary,output):
    fig,ax=plt.subplots(figsize=(9,4.5),layout='constrained')
    names=summary.model.tolist();v=summary.MAE_mean_C.to_numpy()
    ax.barh(names,v,color=['#899C96','#E0AA69','#1B575A'])
    for i,x in enumerate(v): ax.text(x+.015,i,f'{x:.3f} °C',va='center',fontsize=12)
    ax.set(xlabel='Mean MAE across four spatial folds (°C)',title='Spatial model validation on the sample window',xlim=(0,float(v.max())*1.35))
    ax.invert_yaxis();ax.spines[['top','right']].set_visible(False)
    fig.savefig(output,dpi=180)
    return fig

def write_interactive_map(df,root):
    root=Path(root);template=(root/'src/map_template.html').read_text()
    records=[]
    for r in df.itertuples():
        records.append({'cell_id':r.cell_id,'x':r.x_m,'y':r.y_m,'temperature':float(r.lst_mean_c) if r.heat_usable else None,'relative':float(r.relative_temp_c) if r.heat_usable else None,'ndvi':float(r.ndvi) if r.surface_usable else None,'priority':r.priority,'score':float(r.priority_score) if r.heat_usable else None,'reason':r.priority_reason,'actions':r.candidate_actions,'landsat':r.landsat_id,'sentinel':r.sentinel_id})
    text=json.dumps(records,allow_nan=False).replace('<','\\u003c').replace('&','\\u0026')
    target=root/'results/interactive_priority_map.html';target.write_text(template.replace('__DATA__',text))
    return target
