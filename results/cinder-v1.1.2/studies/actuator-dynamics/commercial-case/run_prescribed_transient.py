from pathlib import Path
import subprocess,sys,json,math,csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(HERE/'derive_parameters.py')],check=True)
cfg=json.loads((HERE/'inputs'/'sidewinder_ysr31_provisional.json').read_text())
d=json.loads((HERE/'derived'/'derived_parameters.json').read_text())
rows=[]
for est in d['estimates']:
    I=est['movable_member_polar_inertia_kg_m2']; H=est['helix_motion_ratio_rad_per_m']
    for T in cfg['prescribed_transient_sensitivity']['event_durations_s']:
        xdd=4*cfg['prescribed_transient_sensitivity']['axial_travel_m']/(T*T)
        alpha=(2*math.pi/60)*cfg['prescribed_transient_sensitivity']['secondary_speed_change_rpm']/T
        for tq in cfg['prescribed_transient_sensitivity']['quasi_static_helix_torque_scales_Nm']:
            po=I*abs(alpha)/abs(tq); px=I*abs(H*xdd)/abs(tq)
            rows.append({'estimate_level':est['estimate_level'],'event_duration_s':T,'quasi_static_helix_torque_scale_Nm':tq,'prescribed_axial_acceleration_m_s2':xdd,'prescribed_secondary_acceleration_rad_s2':alpha,'Pi_s_omega':po,'Pi_s_axial':px,'Pi_s_curvature':0.0,'worst_reinforcing_sum':po+px})
out=HERE/'artifacts'; out.mkdir(exist_ok=True)
with (out/'prescribed_transient_sensitivity.csv').open('w',newline='',encoding='utf-8') as h:
    w=csv.DictWriter(h,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
nom=[r for r in rows if r['estimate_level']=='nominal' and r['quasi_static_helix_torque_scale_Nm']==120.0]
fig,ax=plt.subplots(figsize=(8.5,5.5)); x=[1000*r['event_duration_s'] for r in nom]
ax.plot(x,[100*r['Pi_s_omega'] for r in nom],label=r'$\Pi_{s,\omega}$')
ax.plot(x,[100*r['Pi_s_axial'] for r in nom],label=r'$\Pi_{s,x}$')
ax.plot(x,[100*r['worst_reinforcing_sum'] for r in nom],label='worst-reinforcing sum')
ax.set_xlabel('Prescribed transient duration [ms]'); ax.set_ylabel('Dynamic correction [% of QS helix force]'); ax.set_title('Provisional Sidewinder/YSR31 transient sensitivity'); ax.grid(True,alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(out/'nominal_transient_sensitivity.png',dpi=180); plt.close(fig)
# angle sensitivity figure
ar=d['angle_sensitivity']; fig,ax=plt.subplots(figsize=(8.5,5.5))
levels=['low','nominal','high']; X=range(len(levels)); width=.34
v31=[next(r for r in ar if r['estimate_level']==lv and r['helix_angle_deg']==31.0)['relative_to_baja_reflected_axial_inertia'] for lv in levels]
v28=[next(r for r in ar if r['estimate_level']==lv and r['helix_angle_deg']==28.0)['relative_to_baja_reflected_axial_inertia'] for lv in levels]
ax.bar([i-width/2 for i in X],v31,width,label='YSR31 straight'); ax.bar([i+width/2 for i in X],v28,width,label='YSR36/28 local 28° segment'); ax.axhline(1,ls='--',linewidth=1); ax.set_xticks(list(X),levels); ax.set_ylabel('Reflected axial inertia / Baja [-]'); ax.set_title('Commercial secondary estimate: effect of OTS helix angle'); ax.grid(True,axis='y',alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(out/'angle_sensitivity_vs_baja.png',dpi=180); plt.close(fig)
summary={'illustrative_points':[r for r in nom if r['event_duration_s'] in [0.05,0.075,0.1]],'angle_sensitivity':ar,'note':'Prescribed kinematics are sensitivity inputs, not measured Sidewinder behavior.'}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(f'Wrote provisional commercial-case artifacts to {out}')
