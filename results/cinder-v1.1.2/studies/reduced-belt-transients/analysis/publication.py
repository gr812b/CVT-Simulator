"""Prepare/check/plot belt publication evidence without running a simulation."""
from __future__ import annotations
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

STUDY=Path(__file__).resolve().parents[1]
RELEASE=STUDY.parents[1]
REPO=RELEASE.parents[1]
INPUT=STUDY/'publication_inputs'
FIGURES=REPO/'docs/CVT_Module_Formulation/figures/results/dynamics'
STATE_KEYS=('primary_omega','secondary_omega','belt_speed','shift','shift_speed')
TERMS=('radial_shift_acceleration','radial_geometry_curvature','tangential_belt_acceleration','tangential_shifting_radius','normal_contact')
PLOT_RUNS={c+'_tight_full' for c in ('flat','rise50','rise200','rise800','envelope','contact','contact_combined')}
PLOT_FIELDS={'time_s','segment_index','mode','shift','shift_speed','belt_speed',
    'loop.activity_scale_N','loop.contact_scale_N',
    'loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2',
    'loop.driver.tangential_shifting_radius_m2ps2',
    'coefficient.primary_G','coefficient.secondary_G','contact.primary_normal_N','contact.secondary_normal_N',
    'transport.belt_inertia_N','transport.primary_reaction_N','transport.secondary_reaction_N',
    *('loop.'+t+'_N' for t in TERMS)}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def read_rows(p):
    with gzip.open(p,'rt') as f:rows=list(csv.DictReader(f))
    columns={}
    for k in rows[0]:
        vals=[r[k] for r in rows]
        try:columns[k]=np.array([float(v) if v else np.nan for v in vals])
        except ValueError:columns[k]=np.array(vals)
    return columns

def sample_segments(data,t,side='right'):
    """Interpolate only inside each continuous segment; event sides stay distinct."""
    out=np.full((len(t),len(STATE_KEYS)),np.nan);labels=np.full(len(t),-1,int)
    ids=np.unique(data['segment_index']).astype(int)
    # Overwrite duplicate event times with the requested left or right limit.
    for i in (ids if side=='right' else ids[::-1]):
        m=data['segment_index']==i;tt=data['time_s'][m]
        q=(t>=tt[0])&(t<=tt[-1])
        for j,key in enumerate(STATE_KEYS):out[q,j]=np.interp(t[q],tt,data[key][m])
        labels[q]=i
    return out,labels

def compare(a,b):
    t=np.unique(np.r_[a['time_s'],b['time_s']])
    t=t[(t>=max(a['time_s'][0],b['time_s'][0]))&(t<=min(a['time_s'][-1],b['time_s'][-1]))]
    ar,ai=sample_segments(a,t);br,bi=sample_segments(b,t)
    al,_=sample_segments(a,t,'left');bl,_=sample_segments(b,t,'left')
    assert np.isfinite(ar).all() and np.isfinite(br).all()
    diff=ar-br;left=al-bl
    scale=np.array([60/(2*np.pi),60/(2*np.pi),1,1000,1000])
    units=('rpm','rpm','m_per_s','mm','mm_per_s')
    result={}
    am={int(i):a['mode'][np.flatnonzero(a['segment_index']==i)[0]] for i in np.unique(ai)}
    bm={int(i):b['mode'][np.flatnonzero(b['segment_index']==i)[0]] for i in np.unique(bi)}
    same_mode=np.array([am[i]==bm[j] for i,j in zip(ai,bi)])
    for name,mask in [('whole',np.ones(len(t),bool)),('after_0_1s',t>=.1),
                     ('same_mode',same_mode)]:
        mx=np.maximum(np.max(abs(diff[mask]),axis=0),np.max(abs(left[mask]),axis=0))*scale
        if name=='same_mode':
            # Left limits can have a different mode at this time: report right-side mask only.
            mx=np.max(abs(diff[mask]),axis=0)*scale
        result[name]={key+'_'+unit:float(x) for key,unit,x in zip(STATE_KEYS,units,mx)}
    # Preserve pair-of-segment identity for plots; never join across a reset.
    return {'time_s':t,'difference':diff,'left_difference':left,'full_segment':ai,'variant_segment':bi},result

def event_comparison(a,b):
    same=len(a)==len(b) and all(x['events']==y['events'] and x['next_mode']==y['next_mode'] for x,y in zip(a,b))
    out={'same_ordered_events_and_modes':same,'full_count':len(a),'variant_count':len(b)}
    if same:
        out['max_abs_event_time_difference_ms']=max([1000*abs(x['time_s']-y['time_s']) for x,y in zip(a,b)]+[0.])
        out['event_time_differences_ms']=[1000*(x['time_s']-y['time_s']) for x,y in zip(a,b)]
        scales=np.array([60/(2*np.pi),60/(2*np.pi),1.,1000.,1000.])
        for side in ('pre_state','post_state'):
            delta=np.array([np.array(x[side][:5])-np.array(y[side][:5]) for x,y in zip(a,b)])
            out[side+'_max_abs_difference']=dict(zip(STATE_KEYS,(np.max(abs(delta),axis=0)*scales).tolist()))
    # The sequence after launch is a separate result, not erased by early chatter.
    aa=[x for x in a if x['time_s']>=.1];bb=[x for x in b if x['time_s']>=.1]
    out['same_order_after_0_1s']=len(aa)==len(bb) and all(x['events']==y['events'] and x['next_mode']==y['next_mode'] for x,y in zip(aa,bb))
    if out['same_order_after_0_1s']:
        out['max_abs_later_event_time_difference_ms']=max([1000*abs(x['time_s']-y['time_s']) for x,y in zip(aa,bb)]+[0.])
    return out

def integrate(data,values,a,b):
    total=0.
    for i in np.unique(data['segment_index']):
        m=(data['segment_index']==i)&(data['time_s']>=a)&(data['time_s']<=b)
        if m.sum()>1:total+=float(np.trapezoid(values[m],data['time_s'][m]))
    return total

def peak(data,key,mask=None):
    if mask is None:mask=np.ones(len(data['time_s']),bool)
    ix=np.flatnonzero(mask);i=ix[np.argmax(abs(data[key][ix]))]
    keys=['time_s','segment_index','mode','shift','shift_speed','belt_speed',key,
          'loop.activity_scale_N','loop.contact_scale_N','coefficient.primary_G','coefficient.secondary_G',
          'contact.primary_normal_N','contact.secondary_normal_N','contact.primary_lambda','contact.secondary_lambda',
          'loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2',
          'loop.driver.tangential_shifting_radius_m2ps2']
    return {k:data[k][i].item() for k in dict.fromkeys(keys)}

def regional_balance(data, start, end):
    """Five-term magnitude shares, integrating each continuous segment separately.

    Terms exist only at engaged states. Disengaged gaps have no primary wrap;
    they are excluded, never bridged or assigned a fictitious force.
    """
    integrals={k:integrate(data,abs(data['loop.'+k+'_N']),start,end) for k in TERMS}
    denominator=sum(integrals.values())
    assert denominator>0
    separate=integrate(data,data['loop.activity_scale_N'],start,end)
    assert np.isclose(denominator,separate,rtol=1e-12,atol=1e-14)
    mask=(data['time_s']>=start)&(data['time_s']<=end)
    return {'start_s':start,'end_s':end,'absolute_integrals_Ns':integrals,
        'absolute_sum_integral_Ns':denominator,
        'share_percent':{k:100*v/denominator for k,v in integrals.items()},
        'peak_magnitude_N':{k:float(np.max(abs(data['loop.'+k+'_N'][mask]))) for k in TERMS},
        'modes':sorted(set(data['mode'][mask].tolist()))}

def prepare(raw):
    raw=raw.resolve();plan=json.loads((INPUT/'run_plan.json').read_text())
    pack={};runs={};source_hashes={};states={};terms={};events={}
    for job in plan:
        name='{case}_{level}_{variant}'.format(**job);p=raw/name
        if not (p/'summary.json').exists():raise RuntimeError('Missing completed result '+name)
        s=json.loads((p/'summary.json').read_text())
        assert s['release_commit']=='7637a38b4fb9ec21dfb953c1c80a27ec5f389654'
        assert s['runtime']['cinder']=='1.1.2'
        for f,h in s['output_sha256'].items():assert sha(p/f)==h,(name,f)
        for f in p.iterdir():
            if f.is_file():source_hashes[str(f.relative_to(raw))]=sha(f)
        states[name]=read_rows(p/'states.csv.gz');terms[name]=read_rows(p/'terms.csv.gz')
        # Early density comparison uses actual positions on each continuous
        # segment, not a difference interpolated through mismatched captures.
        if name in {'flat_tight_full', 'flat_tight_density03'}:
            early=states[name]['time_s']<=.1
            for k in ('time_s','segment_index','shift'):
                pack[name+'__early_states__'+k]=states[name][k][early]
        events[name]=json.loads((p/'events.json').read_text())
        a=s['audit'];d=terms[name]
        a['max_endpoint_vs_equation_residual_N']=float(np.max(abs(d['wrap.endpoint_sum_residual_N']-d['loop.residual_N'])))
        for side in ('primary','secondary'):
            stick=d[side+'.sticking']=='True'
            a[side+'.minimum_static_margin']=float(np.min(.65-abs(d['contact.'+side+'_lambda'][stick]))) if stick.any() else None
        runs[name]=s
        # Keep dimensional, signed channels and masks. Threshold machinery is not plotted.
        if name in PLOT_RUNS:
            for k,v in terms[name].items():
                if k in PLOT_FIELDS:pack[name+'__terms__'+k]=v
    comparisons={}
    for job in plan:
        if job['variant']=='full':continue
        name='{case}_{level}_{variant}'.format(**job);base='{case}_{level}_full'.format(**job)
        d,r=compare(states[base],states[name]);r['events']=event_comparison(events[base],events[name])
        comparisons[name]=r
        if name.endswith('_tight_density03'):
            for k,v in d.items():pack[name+'__comparison__'+k]=v
    refinements={}
    for job in plan:
        if job['level']!='tight':continue
        name='{case}_{level}_{variant}'.format(**job);base=name.replace('_tight_','_nominal_')
        _,r=compare(states[base],states[name]);r['events']=event_comparison(events[base],events[name])
        refinements[name]=r
    term_results={}
    for name,d in terms.items():
        if not name.endswith('_full'):continue
        s=runs[name];cfg=s['boundary_programme'];t=d['time_s']
        summary={'peak_all':{k:peak(d,'loop.'+k+'_N') for k in TERMS},
                 'peak_after_0_1s':{k:peak(d,'loop.'+k+'_N',t>=.1) for k in TERMS},
                 'share_peak_after_0_1s':{k:peak(d,'loop.share.'+k,t>=.1) for k in TERMS}}
        if cfg:
            a=cfg['start_time_s'];b=a+cfg['rise_time_s'];mask=(t>=a)&(t<=b)
            denom=integrate(d,d['loop.activity_scale_N'],a,b)
            summary['load_rise']={'start':a,'end':b,'absolute_activity_integral_Ns':denom,
                'peak':{k:peak(d,'loop.'+k+'_N',mask) for k in TERMS},
                'integrated_share':{k:integrate(d,abs(d['loop.'+k+'_N']),a,b)/denom for k in TERMS}}
        term_results[name]=summary
    regions={}
    for level in ('nominal','tight'):
        name='flat_'+level+'_full';e=events[name]
        first=min(x['time_s'] for x in e if 'cvt:engagement_reached' in x['events'])
        last=max(x['time_s'] for x in e if x['time_s']<.1 and 'cvt:low_ratio_seat_reached' in x['events'])
        # First free, sticking segment after the initial seated interval.
        d=terms[name]
        free=np.array(['CVTShiftConstraint.FREE' in m and 'EngagedContactMode.STICK_STICK:' in m for m in d['mode']])
        release=float(np.min(d['time_s'][free&(d['time_s']>.1)]))
        regions['free_shift_'+level]=regional_balance(d,release,5.)
        regions['engagement_'+level]=regional_balance(d,first,last)
        n='envelope_'+level+'_full';cfg=runs[n]['boundary_programme']
        regions['midshift_load_'+level]=regional_balance(terms[n],cfg['start_time_s'],cfg['start_time_s']+cfg['rise_time_s'])
    np.savez_compressed(INPUT/'belt_publication.npz',**pack)
    (INPUT/'belt_events.json').write_text(json.dumps(events,indent=2,allow_nan=False)+'\n')
    record={'runs':runs,'comparisons':comparisons,'refinement':refinements,'terms':term_results,'regions':regions,
        'raw_sha256':source_hashes,'plot_inputs_sha256':sha(INPUT/'belt_publication.npz'),
        'scope':'Selected integrated trajectories; dense samples within segments, exact incoming/outgoing states. No continuous-domain proof.',
        'difference_definition':'Full minus variant on common physical time; both limits at event times. No interpolation across resets.',
        'script_sha256':sha(Path(__file__))}
    (INPUT/'belt_publication_audit.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print('Prepared',len(runs),'runs,',len(comparisons),'comparisons')

def check(raw):
    a=json.loads((INPUT/'belt_publication_audit.json').read_text())
    assert sha(INPUT/'belt_publication.npz')==a['plot_inputs_sha256']
    raw_verified=0
    if raw.exists():
        for f,h in a['raw_sha256'].items():assert sha(raw/f)==h,f
        raw_verified=len(a['raw_sha256'])
    import cinder
    runtime=json.loads((INPUT/'runtime_source_check.json').read_text())
    pkg=Path(cinder.__file__).resolve().parent
    for f,h in runtime['source_sha256'].items():
        assert sha(pkg/f.removeprefix('cvtModel/src/cinder/'))==h,f
    findings=[]
    for name,s in a['runs'].items():
        assert s['completed'],name
        assert s['audit']['inspection_errors']==0,name
        for k,v in s['audit'].items():
            if ('min_local_normal' in k or 'min_tension' in k) and v<0:findings.append((name,k,v))
        assert s['audit']['max_endpoint_vs_equation_residual_N']<1e-8,name
        assert s['audit']['closure.max_abs_residual']<1e-7,name
    print(json.dumps({'run_count':len(a['runs']),'local_loading_findings':findings,
        'raw_files_verified':raw_verified,'frozen_source_files_verified':len(runtime['source_sha256'])},indent=2))

def main(action,raw,figures=None):
    if action=='prepare':prepare(raw)
    elif action=='check':check(raw)
    elif action=='plot':
        from analysis.publication_plots import plot_all
        plot_all(INPUT,figures or FIGURES)
