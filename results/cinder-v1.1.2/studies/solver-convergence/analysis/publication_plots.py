"""Final 4.2.3 figures from registered CINDER 1.1.2 outputs.
Canonical command: python studies/solver-convergence/run.py --plot-only
No simulation, interpolation across resets, or fitted convergence order.
"""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import LogNorm
from matplotlib.ticker import NullFormatter
import numpy as np
from .evidence import REPO, STUDY, digest, gross_rms, read_json, write_json
from .verification import audit, formal_module
from .supporting_plots import STYLE, save, sci, absolute_tolerance_panel

BLUE, GREEN, ORANGE = '#21618c', '#38735c', '#b44e2b'
RUNS = (('reference', 'Tight reference', BLUE, '-'),
        ('canonical', 'Intermediate', GREEN, (0, (5, 2))),
        ('selected', 'Loose', ORANGE, (0, (1.5, 1.5))))
KEYS = ('primary_omega_rad_s', 'secondary_omega_rad_s', 'belt_speed_m_s', 'shift_m', 'shift_speed_m_s')


def segments(cache):
    unpack = formal_module().unpack_segment_trace
    return [unpack(cache['payload'], i) for i in range(len(cache['segments']))]


def contact_kind(mode):
    if 'DEADZONE:' in mode:
        return 'Primary separated'
    if 'LOW_RATIO_SEAT:' in mode:
        return 'Low-ratio support'
    return 'Engaged, free shift'


def reader_values(values, main, caches, artifacts):
    data = {name: segments(cache) for name, cache in caches.items()}
    dimensions = {}
    for key in KEYS:
        deltas = [c[key]-r[key] for c,r in zip(data['canonical'],data['reference'],strict=True)]
        maximum = max(float(np.max(np.abs(x))) for x in deltas)
        expected = values['canonical'][key+'_max_abs_normalized']*values['state_scales'][key]
        assert np.isclose(maximum, expected, rtol=2e-11, atol=1e-16)
        dimensions[key] = maximum
    case = read_json(artifacts / 'execution_inputs/results/cinder-v1.1.2/defaults/baja/simulation_case.json')
    engagement = case['assembly']['geometry']['deadzone_shift_m']
    histories = {}
    for name, cache in caches.items():
        first = next(e['time_s'] for e in cache['events'] if e['fired_event_names']=='cvt:engagement_reached')
        excursions=[]
        for seg, trace in zip(cache['segments'], data[name], strict=True):
            if seg['start_time_s']>=first and seg['end_time_s']<.1 and contact_kind(seg['mode'])=='Primary separated':
                excursions.append({'start_s':seg['start_time_s'], 'end_s':seg['end_time_s'],
                    'duration_us':(seg['end_time_s']-seg['start_time_s'])*1e6,
                    'sampled_depth_um':(engagement-float(trace['shift_m'].min()))*1e6})
        histories[name]={'seating_ms':next(e['time_s']*1000 for e in cache['events'] if 'LOW_RATIO_SEAT:' in e['next_mode']),
                         'excursions':excursions}
    assert [len(histories[n]['excursions']) for n in ('reference','canonical','selected')]==[5,5,3]
    completed=[r for r in main if r['run_status']=='completed']
    assert len(completed)==39 and all(r['transition_signature_match'] for r in completed)
    assert all(max(KEYS,key=lambda k:r[k+'_max_abs_normalized'])=='shift_speed_m_s' for r in completed)
    assert all(r['passes_review_guards'] for r in main if r['relative_tolerance']<=1e-4)
    values['reader_values']={'aligned_dimensional_sampled_maxima':dimensions,
        'engagement_position_m':engagement, 'histories':histories,
        'dominant_scaled_peak_component_all_completed_formal_rows':'shift_speed_m_s',
        'research_mode_mismatch_duration_us':values['canonical']['regime_mismatch_fraction']*10*1e6}
    # Publication ranges use every completed cap, never a selected cap or an
    # average masquerading as an observed run. Failed rows have no ordinate.
    ranges=[]
    metrics={'rms':('trajectory_rms_normalized',1),
             'shift_speed_peak_mm_s':('shift_speed_m_s_max_abs_normalized',values['state_scales']['shift_speed_m_s']*1000),
             'shift_position_peak_um':('shift_m_max_abs_normalized',values['state_scales']['shift_m']*1e6),
             'event_time_max_us':('maximum_event_time_error_s',1e6)}
    for rtol in sorted({r['relative_tolerance'] for r in main},reverse=True):
        group=[r for r in completed if r['relative_tolerance']==rtol]
        row={'relative_tolerance':rtol,'completed_caps_s':sorted(r['max_step'] for r in group)}
        for name,(key,scale) in metrics.items():
            observed=[r[key]*scale for r in group]
            assert all(np.isfinite(observed)) and min(observed)>0
            row[name]={'min':min(observed),'max':max(observed)}
        ranges.append(row)
    assert [len(r['completed_caps_s']) for r in ranges]==[4,5,5,5,5,5,5,5]
    values['reader_values']['formal_ranges_across_completed_caps']=ranges
    return data


def motion_figure(data, caches, values, out):
    fig=plt.figure(figsize=(6.5,3.15))
    gs=fig.add_gridspec(2,1,height_ratios=(.58,1.25),left=.13,right=.98,bottom=.14,top=.83,hspace=.76)
    overview=fig.add_subplot(gs[0]); detail=fig.add_subplot(gs[1])
    fig.legend([Line2D([],[],color=c,ls=ls,lw=1.5) for _,_,c,ls in RUNS],
               [label for _,label,_,_ in RUNS],ncol=3,loc='upper center',bbox_to_anchor=(.55,1),frameon=False,columnspacing=1.8)
    engagement=values['reader_values']['engagement_position_m']
    for name,label,color,style in RUNS:
        for seg in data[name]:
            times=seg['start_time_s']+seg['phase']*(seg['end_time_s']-seg['start_time_s'])
            overview.plot(times,seg['shift_m']*1000,color=color,ls=style,lw=1.2)
            if seg['end_time_s']>=.06194 and seg['start_time_s']<=.0663:
                detail.plot(times*1000,(seg['shift_m']-engagement)*1e6,color=color,ls=style,lw=1.25)
    overview.set(xlim=(0,10),ylim=(-.7,20.5),yticks=(0,10,20),ylabel='Shift [mm]',xlabel='Time [s]')
    overview.set_title('(a) Complete acceleration',loc='left',pad=5)
    detail.set(xlim=(61.94,66.3),ylim=(-55,43),yticks=(-50,-25,0,25),ylabel='Shift from engagement\nposition [µm]',xlabel='Time [ms]')
    detail.axhline(0,color='.4',lw=.6,zorder=0)
    detail.set_title('(b) Early sheave motion',loc='left',pad=5)
    detail.text(64.25,4,'engagement position',ha='center',va='bottom',fontsize=7.5,color='.35')
    for (name,label,color,_),marker,size in zip(RUNS,('o','+','o'),(6.5,6,5)):
        # Seating is read from the outgoing support mode in the event ledger,
        # never inferred from a flat position trace. Exact timestamps are used:
        # reference and intermediate marks nearly coincide at manuscript size.
        seated=values['reader_values']['histories'][name]['seating_ms']
        event=next(e for e in caches[name]['events'] if 'LOW_RATIO_SEAT:' in e['next_mode'])
        assert seated == event['time_s']*1000
        detail.plot(seated,0,marker=marker,ms=size,mfc='white',mec=color,mew=1.1,zorder=6)
    detail.text(.98,.92,'Markers: low-ratio seating',transform=detail.transAxes,ha='right',va='top',fontsize=7.5,color='.25')
    for ax in (overview,detail):ax.grid(color='.92',lw=.4)
    save(fig,out,'gross_motion_hybrid_history')


def refinement_figure(main, values, out):
    fig=plt.figure(figsize=(6.5,4.3))
    axes=[fig.add_axes((.13,y,.75,h)) for y,h in ((.69,.23),(.405,.18),(.12,.18))]
    cax=fig.add_axes((.903,.69,.019,.23))
    ranges=values['reader_values']['formal_ranges_across_completed_caps']
    rtols=np.array([r['relative_tolerance'] for r in ranges])
    steps=sorted({r['max_step'] for r in main},reverse=True)
    lookup={(r['relative_tolerance'],r['max_step']):r for r in main}
    edges=np.r_[rtols[0]*np.sqrt(rtols[0]/rtols[1]),
                np.sqrt(rtols[:-1]*rtols[1:]),rtols[-1]/np.sqrt(rtols[-2]/rtols[-1])]
    error=np.array([[lookup[r,s]['trajectory_rms_normalized'] for r in rtols] for s in steps])
    cmap=plt.get_cmap('viridis').copy();cmap.set_bad('#eeeeee')
    im=axes[0].pcolormesh(edges,np.arange(6)-.5,np.ma.masked_invalid(error),
                         cmap=cmap,norm=LogNorm(1e-7,1e-3),shading='flat',rasterized=True)
    axes[0].set(ylim=(4.5,-.5),yticks=range(5),yticklabels=[f'{s*1000:g}' for s in steps],
                ylabel='Maximum step [ms]')
    axes[0].set_title('(a) Discrepancy over the complete motion',loc='left',pad=6)
    for iy,cap in enumerate(steps):
        for rtol in rtols:
            row=lookup[rtol,cap]
            if row['run_status']!='completed':
                axes[0].text(rtol,iy,'F',ha='center',va='center',color=ORANGE)
            else:
                assert row['transition_signature_match'] and np.isfinite(row['trajectory_rms_normalized'])
    cb=fig.colorbar(im,cax=cax,ticks=[1e-7,1e-5,1e-3]);cb.set_label('Five-state RMS',fontsize=8)
    for ax,key,color,title,units in (
        (axes[1],'shift_speed_peak_mm_s',BLUE,'(b) Largest aligned shift-speed difference','mm/s'),
        (axes[2],'event_time_max_us',GREEN,'(c) Largest event-time difference','µs')):
        lower=np.array([r[key]['min'] for r in ranges]);upper=np.array([r[key]['max'] for r in ranges])
        ax.fill_between(rtols,lower,upper,color=color,alpha=.17,lw=0)
        ax.plot(rtols,lower,color=color,lw=.9)
        ax.plot(rtols,upper,color=color,lw=.9)
        ax.vlines(rtols,lower,upper,color=color,lw=1)
        ax.plot(rtols,lower,ls='none',marker='_',ms=6,color=color)
        ax.plot(rtols,upper,ls='none',marker='_',ms=6,color=color)
        ax.set(yscale='log',ylabel=f'Difference [{units}]')
        ax.set_title(title,loc='left',pad=6);ax.grid(axis='y',color='.92',lw=.4)
    axes[1].set(ylim=(.002,40),yticks=[.01,.1,1,10])
    axes[2].set(ylim=(.3,15000),yticks=[1,10,100,1000,10000])
    axes[1].text(.98,.92,'Range across completed step caps',ha='right',va='top',
                 transform=axes[1].transAxes,fontsize=7.7,color='.25')
    for ax in axes:
        ax.set(xscale='log',xlim=(edges[0],edges[-1]))
        ax.set_xticks(rtols,[sci(r) for r in rtols]);ax.minorticks_off()
    for ax in axes[:2]:ax.tick_params(labelbottom=False)
    axes[2].set_xlabel(r'Relative tolerance; absolute tolerance $=10^{-3}\,\mathrm{rtol}$')
    save(fig,out,'solver_refinement')


def refinement_support(main, atol, values, out):
    # The main figure now carries RMS and local peaks. This support resolves
    # the cap identities hidden by its timing range and adds the atol sweep.
    rtols=sorted({r['relative_tolerance'] for r in main},reverse=True)
    steps=sorted({r['max_step'] for r in main})
    lookup={(r['relative_tolerance'],r['max_step']):r for r in main}
    fig=plt.figure(figsize=(6.5,4.3))
    time_ax=fig.add_axes((.145,.615,.835,.21))
    atol_ax=fig.add_axes((.145,.115,.835,.22))
    colors=['#4f83a5',GREEN,'#aa6d35','#806998','#555555'];markers=['v','o','s','^','D']
    for cap,color,marker in zip(steps,colors,markers):
        rows=[lookup[r,cap] for r in rtols]
        time_ax.plot(rtols,[r['maximum_event_time_error_s']*1e6 for r in rows],
                     color=color,marker=marker,ms=3,lw=.8,label=f'{cap*1000:g} ms')
    time_ax.set(xscale='log',yscale='log',xlim=(.017,2e-6),ylim=(.3,20000),
                ylabel='Difference [µs]',yticks=[1,10,100,1000,10000])
    time_ax.set_title('(a) Largest event-time difference by step cap',loc='left',pad=6)
    time_ax.grid(axis='y',color='.92',lw=.4);time_ax.minorticks_off()
    time_ax.set_xticks(rtols,[sci(r) for r in rtols])
    time_ax.set_xlabel(r'Relative tolerance; absolute tolerance $=10^{-3}\,\mathrm{rtol}$')
    fig.legend(*time_ax.get_legend_handles_labels(),loc='upper center',ncol=5,
               bbox_to_anchor=(.55,.995),frameon=False,title='Maximum adaptive step',
               columnspacing=1.2,handlelength=1.5)
    absolute_tolerance_panel(atol_ax,atol,values,title='(b) Independent absolute-tolerance sweep')
    save(fig,out,'solver_acceptance_support')


def population_figure(dense,values,out):
    fig,ax=plt.subplots(figsize=(6.5,2.7))
    fig.subplots_adjust(left=.11,right=.98,bottom=.18,top=.91)
    complete=[r for r in dense if r['run_status']=='completed']
    for status,color,label in ((True,'#aeb5bb','Matching history (4,072)'),(False,ORANGE,'Different history (609)')):
        group=[r for r in complete if r['transition_signature_match']==status]
        ax.scatter([r['native_solver_point_count'] for r in group],[gross_rms(r) for r in group],
            s=5,alpha=.6,color=color,lw=0,rasterized=True,label=label)
    ax.scatter(values['selected_archived_native_point_count'],values['selected_archived_gross_rms'],
        marker='*',s=80,facecolor='#e4bf56',edgecolor='.25',lw=.5,label='Selected loose setting',zorder=5)
    ax.set(xscale='log',yscale='log',xlabel='Native solver points',ylabel='Four-state gross RMS')
    ax.set_xticks([200,500,1000,2000],['200','500','1,000','2,000']);ax.xaxis.set_minor_formatter(NullFormatter())
    ax.legend(loc='upper right',frameon=False,markerscale=1.2,fontsize=8);ax.grid(color='.92',lw=.4)
    save(fig,out,'solver_population_support')


def publish(artifacts,out=None):
    artifacts=Path(artifacts)
    out=Path(out) if out is not None else REPO/'docs/CVT_Module_Formulation/figures/results/verification'
    out.mkdir(parents=True,exist_ok=True)
    values,main,atol,dense,caches=audit(artifacts)
    data=reader_values(values,main,caches,artifacts)
    with plt.rc_context(STYLE):
        motion_figure(data,caches,values,out)
        refinement_figure(main,values,out)
        refinement_support(main,atol,values,out)
        population_figure(dense,values,out)
    write_json(out/'solver_convergence_values.json',values)
    write_json(out/'solver_convergence_provenance.json',{
        'run_id':values['run_id'],'mechanics_version':'1.1.2',
        'mechanics_commit':'7637a38b4fb9ec21dfb953c1c80a27ec5f389654',
        'command':'.venv/bin/python studies/solver-convergence/run.py --plot-only',
        'evidence_record_sha256':digest(artifacts/'execution_provenance.json'),
        'code_sha256':{str(p.relative_to(REPO)):digest(p) for p in [STUDY/'run.py',STUDY/'study.json',*sorted((STUDY/'analysis').glob('*.py'))]},
        'figure_width_inches':6.5,
        'figures':{
            'gross_motion_hybrid_history':'Three retained/replayed runs; segmentwise whole and signed local shift. Seating markers use exact outgoing-support events; no displacement of nearly coincident times, interpolation across resets or widening of tiny regimes.',
            'solver_refinement':'40 formal cells: five-state aligned RMS colour, explicit failed cell; no acceptance circles or selected-setting highlight. Dimensional peak shift-speed and absolute event-time ranges across all completed caps at each tolerance; 4 at the coarsest and 5 otherwise. Bands are numerical-setting ranges, not statistical uncertainty. No fitted order.',
            'solver_acceptance_support':'Cap-specific event-time trends underlying the main timing range; seven independent absolute-tolerance rows. Main RMS and local peaks are not duplicated. The failed main row and different-history comparisons have no corresponding-event ordinate. Guard decisions and all 47 rows remain audited.',
            'solver_population_support':'4681 completed exploratory rows, exact signature grouping; 264 failures have no norm. Four-state compact gross metric is not formal acceptance; native points are not function evaluations.'},
        'verification_scope':values['scope'],'new_simulations':0,
        'canonical_note':'Retained literal-atol intermediate cache (historically named research); the proportional-atol main-grid row differs in late digits. No mixing of unrounded execution metrics.'})
    print(f"Verified and published four figures from {values['run_id']} to {out}")
