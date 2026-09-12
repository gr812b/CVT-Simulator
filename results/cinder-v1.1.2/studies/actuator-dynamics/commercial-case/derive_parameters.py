from pathlib import Path
import json, math, csv
HERE=Path(__file__).resolve().parent
cfg=json.loads((HERE/'inputs'/'sidewinder_ysr31_provisional.json').read_text())
rho=float(cfg['assumptions']['material_density_kg_m3'])

def calc(name,p,angle):
    Ro,Ri,t,phi=float(p['outer_radius_m']),float(p['inner_radius_m']),float(p['effective_face_thickness_m']),float(p['material_fill_fraction'])
    mh,Rh=float(p['hub_mass_kg']),float(p['hub_radius_m'])
    vf=math.pi*(Ro*Ro-Ri*Ri)*t*phi; mf=rho*vf
    If=.5*mf*(Ro*Ro+Ri*Ri); Ih=.5*mh*Rh*Rh; I=If+Ih
    rh=float(p['helix_radius_m']); H=1/(rh*math.tan(math.radians(angle)))
    return {'estimate_level':name,'helix_angle_deg':angle,'face_mass_kg':mf,'hub_mass_kg':mh,'estimated_total_movable_mass_kg':mf+mh,'face_polar_inertia_kg_m2':If,'hub_polar_inertia_kg_m2':Ih,'movable_member_polar_inertia_kg_m2':I,'helix_radius_m':rh,'helix_motion_ratio_rad_per_m':H,'reflected_axial_inertia_kg':I*H*H}

b=cfg['baja_reference']; Hb=1/(b['helix_radius_m']*math.tan(math.radians(b['helix_angle_deg']))); Mb=b['movable_member_inertia_kg_m2']*Hb*Hb
rows=[]
for name,p in cfg['estimates'].items():
    row=calc(name,p,float(cfg['sourced']['helix_angle_deg'])); row['relative_to_baja_reflected_axial_inertia']=row['reflected_axial_inertia_kg']/Mb; rows.append(row)
angle_rows=[]
for name,p in cfg['estimates'].items():
    for angle,label in [(float(cfg['sourced']['helix_angle_deg']),'YSR31 straight'),(float(cfg['sourced']['alternate_progressive_terminal_angle_deg']),'YSR36/28 local 28-degree segment')]:
        row=calc(name,p,angle); row['angle_case']=label; row['relative_to_baja_reflected_axial_inertia']=row['reflected_axial_inertia_kg']/Mb; angle_rows.append(row)

def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

out=HERE/'derived'; out.mkdir(exist_ok=True)
write_csv(out/'mass_property_estimates.csv',rows); write_csv(out/'angle_sensitivity.csv',angle_rows)
for r in rows:
    print(f"{r['estimate_level']}: I={r['movable_member_polar_inertia_kg_m2']:.6f}, H={r['helix_motion_ratio_rad_per_m']:.3f}, Mref={r['reflected_axial_inertia_kg']:.3f} kg ({r['relative_to_baja_reflected_axial_inertia']:.2f}x Baja)")
payload={'baja':{'helix_motion_ratio_rad_per_m':Hb,'reflected_axial_inertia_kg':Mb},'estimates':rows,'angle_sensitivity':angle_rows}
(out/'derived_parameters.json').write_text(json.dumps(payload,indent=2)+'\n')
