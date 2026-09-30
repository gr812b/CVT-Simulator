"""Build the three-panel hill correction comparison from final diagnostic rows.

Requires pandas, NumPy and Matplotlib. No simulation, smoothing, interpolation
of plotted curves, sorting by position, or extrapolation is performed.
"""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import platform
import numpy as np
import course_csvframe as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA=Path(__file__).resolve().parent
OUT=DATA.parent/'figures/results/course'
OUT.mkdir(parents=True,exist_ok=True)
E=json.loads((DATA/'evidence.json').read_text())
COL={'D02':'#BD3F46','D02_M':'#7160B4','D02_P':'#238371','D02_M170':'#303940'}
LS={'D02':'-','D02_M':'-','D02_P':'-','D02_M170':(0,(5,2,1.3,2))}
SEAT=2.4892
CAP=E['D02']['primary_capacity_event']['time_s']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,
 'axes.labelsize':9,'axes.titlesize':9,'legend.fontsize':8,
 'xtick.labelsize':8,'ytick.labelsize':8,'axes.spines.top':False,
 'axes.spines.right':False,'axes.linewidth':.7,'lines.linewidth':1.55,
 'axes.axisbelow':True,'axes.grid':True,'grid.color':'#d6d8dc',
 'grid.alpha':.65,'grid.linewidth':.5,'legend.frameon':False,
 'savefig.facecolor':'white','pdf.fonttype':42})
frames={c:pd.read_csv(DATA/f'{c}_hill.csv') for c in COL}
checks={'plotting_environment':{'python':platform.python_version(),'numpy':np.__version__,
        'pandas':pd.__version__,'matplotlib':matplotlib.__version__},'cases':{}}

fig=plt.figure(figsize=(6.5,3.65))
gs=fig.add_gridspec(2,2,height_ratios=[.95,1.15],left=.105,right=.975,
                  bottom=.145,top=.885,hspace=.66,wspace=.37)
axs=[fig.add_subplot(gs[0,:]),fig.add_subplot(gs[1,0]),fig.add_subplot(gs[1,1])]

for case in COL:
    d=frames[case]
    motion_mask=d.distance_m.between(120,212)
    if case=='D02':motion_mask &= d.time_s.le(CAP)
    q=d.loc[motion_mask]
    assert q.time_s.is_monotonic_increasing and q.distance_m.is_monotonic_increasing
    axs[0].plot(q.distance_m,q.shift_mm,color=COL[case],ls=LS[case],label=case)
    checks['cases'][case]={'motion_rows':len(q),'motion_end_time_s':float(q.time_s.iloc[-1]),
                          'motion_end_distance_m':float(q.distance_m.iloc[-1])}
    hold=d[d.distance_m.between(132,212)]
    mask=(d.distance_m.between(132,212)&d.shift_constraint.eq('low_ratio_seat')
          &d.contact_mode.eq('stick_stick')&d.primary_rpm.le(3200))
    if case=='D02':mask &= d.time_s.le(CAP)
    seated=d.loc[mask]
    checks['cases'][case]['matched_eligible_rows']=len(seated)
    if case=='D02_M170':
        assert not hold.shift_constraint.eq('low_ratio_seat').any()
        assert len(seated)==0
        assert hold.contact_mode.eq('stick_stick').all()
        r200=hold[hold.distance_m.ge(200)].iloc[0]
        checks['cases'][case].update({
            'constant_grade_seated_rows':int(hold.shift_constraint.eq('low_ratio_seat').sum()),
            'constant_grade_all_contacts_stick':bool(hold.contact_mode.eq('stick_stick').all()),
            'minimum_shift_on_hold_mm':float(hold.shift_mm.min()),
            'near_200m':{k:float(r200[k]) for k in ['time_s','distance_m','shift_mm',
                  'primary_rpm','speed_m_s','normal_primary_N','primary_static_utilization',
                  'primary_boundary_power_W']},
            'gap_near_200m_mm':float(r200.shift_mm-SEAT)})
        continue
    arrival=E[case]['hill_first_seat_event']
    axs[0].plot(arrival['distance_m'],SEAT,'o',ms=3.2,color=COL[case])
    # Missing values keep distinct physical branches disconnected.
    x=d.primary_rpm.where(mask)
    axs[1].plot(x,d.normal_primary_N.where(mask)/1000,color=COL[case])
    axs[2].plot(x,d.primary_static_utilization.where(mask),color=COL[case])
    r=E['repair_same_speed_hill']['states'][case]
    actual=seated.loc[(seated.primary_rpm-E['repair_same_speed_hill']['target_primary_rpm']).abs().idxmin()]
    for key in ['time_s','primary_rpm','normal_primary_N','primary_static_utilization']:
        assert np.isclose(actual[key],r[key],rtol=1e-12,atol=1e-9),(case,key)
    axs[1].plot(r['primary_rpm'],r['normal_primary_N']/1000,'o',color=COL[case],ms=3.5)
    axs[2].plot(r['primary_rpm'],r['primary_static_utilization'],'o',color=COL[case],ms=3.5)
    checks['cases'][case].update({
        'matched_marker_time_s':float(actual.time_s),'matched_primary_rpm':float(actual.primary_rpm),
        'matched_normal_N':float(actual.normal_primary_N),'matched_static_use':float(actual.primary_static_utilization),
        'max_grade_error_deg':float((seated.grade_deg-38).abs().max()),
        'max_shift_difference_from_seat_mm':float((seated.shift_mm-SEAT).abs().max())})

axs[0].set_xlim(120,212);axs[0].set_xticks([120,132,150,170,190,212]);axs[0].set_ylim(.8,21)
axs[0].set_yticks([2.4892,10,19.05],labels=['2.49','10','19.05']);axs[0].set_ylabel('Shift [mm]')
axs[0].axvspan(120,132,color='#edf0f2',zorder=0)
axs[0].axhline(SEAT,color='#737b80',lw=.8,ls=(0,(3,3)),zorder=.8)
axs[0].text(167,4.8,'Low-ratio seat',fontsize=8,color='#656565')
gap=checks['cases']['D02_M170']['gap_near_200m_mm']
r200=checks['cases']['D02_M170']['near_200m']
axs[0].annotate(f'D02_M170: {gap:.2f} mm above seat',xy=(r200['distance_m'],r200['shift_mm']),
                xytext=(171,12.0),fontsize=8,color=COL['D02_M170'],
                arrowprops={'arrowstyle':'-','lw':.65,'color':COL['D02_M170']})
axs[0].set_xlabel('Road position [m]');axs[0].set_title('(a) Approach to the seat',loc='left',pad=5)
h,l=axs[0].get_legend_handles_labels()
fig.legend(h,l,loc='upper center',bbox_to_anchor=(.55,1.005),ncol=4,columnspacing=1.4,handlelength=2.4)
for ax in axs[1:]:
    ax.set_xlim(3200,2825);ax.set_xticks([3200,3100,3000,2900])
    ax.axvline(E['repair_same_speed_hill']['target_primary_rpm'],color='#a1a7ab',lw=.75,ls=(0,(2,3)))
axs[1].set_ylim(.65,4.4);axs[1].set_yticks([1,2,3,4]);axs[1].set_ylabel(r'$N_p$ [kN]')
axs[1].set_title('(b) Seated normal load',loc='left',pad=5)
for case,x,y in [('D02_M',2932,3.55),('D02_P',2932,1.95),('D02',3085,.78)]:
    r=E['repair_same_speed_hill']['states'][case]
    axs[1].annotate(f"{r['normal_primary_N']/1000:.2f}",xy=(r['primary_rpm'],r['normal_primary_N']/1000),
                   xytext=(x,y),fontsize=8,color=COL[case],arrowprops={'arrowstyle':'-','lw':.65,'color':COL[case]})
axs[2].set_ylim(.15,1.15);axs[2].set_yticks([.25,.5,.75,1]);axs[2].set_ylabel(r'Static use $|\lambda_p|/\mu_s$')
axs[2].axhline(1,color='#737b80',lw=.8,ls=(0,(3,3)))
axs[2].set_title('(c) Seated static traction',loc='left',pad=5)
axs[2].annotate('D02 loses sticking',xy=(2975.071,1),xytext=(3190,1.055),fontsize=8,color=COL['D02'],
                arrowprops={'arrowstyle':'-','color':COL['D02'],'lw':.65})
for case,x,y in [('D02_P',3110,.50),('D02_M',3040,.18)]:
    r=E[case]['near_200m_hill']
    axs[2].annotate(f"{r['primary_static_utilization']:.2f} at 200 m",xy=(r['primary_rpm'],r['primary_static_utilization']),
                  xytext=(x,y),fontsize=8,color=COL[case],arrowprops={'arrowstyle':'-','lw':.65,'color':COL[case]})
axs[1].set_xlabel('Primary speed [rpm]');axs[2].set_xlabel('Primary speed [rpm]')
for ext in ['pdf','png']:
    b=BytesIO();fig.savefig(b,format=ext,dpi=300)
    (OUT/f'd02_hill_repairs.{ext}').write_bytes(b.getvalue())
plt.close(fig)
checks['figure']={'filename_stem':'d02_hill_repairs','width_in':6.5,'height_in':3.65,
                  'main_panels':3,'insets':0,'png_dpi':300}
checks['output_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(OUT.glob('*')) if p.suffix in ['.png','.pdf']}
(DATA/'figure_build_checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
