/* Geometry is compiled once in section.py and shared with the PNG renderer.
   This file only projects those coordinates and translates rigid assemblies. */
function renderSection(scene, point, dynamics) {
  const s = scene.section, f = point.section;
  const host = document.getElementById('geometry');
  const W=920, H=670, pad={left:72,right:55,top:25,bottom:58};
  const [z0,z1,r0,r1]=s.bounds;
  const scale=Math.min((W-pad.left-pad.right)/(z1-z0),(H-pad.top-pad.bottom)/(r1-r0));
  const ox=pad.left+(W-pad.left-pad.right-scale*(z1-z0))/2, oy=pad.top;
  const X=z=>ox+(z-z0)*scale, Y=r=>oy+(r1-r)*scale;
  const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const col={fixed:'#167586',moving:'#bb6827',block:'#345f91',belt:'#303b49',shaft:'#9aa7b5'};
  const fill={fixed:'url(#fixedHatch)',moving:'url(#movingHatch)',block:'#b2c8e2',belt:'#455366',shaft:'#e5e9ee'};
  const text=(z,r,t,opts='')=>`<text x="${X(z)}" y="${Y(r)}" ${opts}>${esc(t)}</text>`;
  const line=(a,b,color,width=1,dash='')=>`<path d="M${X(a[0])},${Y(a[1])} L${X(b[0])},${Y(b[1])}" fill="none" stroke="${color}" stroke-width="${width}" ${dash?`stroke-dasharray="${dash}"`:''}/>`;
  const path=(points,dz=0)=>points.map(([z,r],i)=>`${i?'L':'M'}${X(z+dz)},${Y(r)}`).join(' ');
  const body=(name,pts,kind,dz=0)=>`<path data-part="${esc(name)}" d="${path(pts,dz)} Z" fill="${fill[kind]}" stroke="${col[kind]}" stroke-width="1.4" stroke-linejoin="round"><title>${esc(name)}</title></path>`;
  const circle=(z,r,radius,color)=>`<circle cx="${X(z)}" cy="${Y(r)}" r="${radius}" fill="${color}" stroke="white" stroke-width="1.4"/>`;
  const arrow=(a,b,color,dashed=false)=>{
    const ax=X(a[0]),ay=Y(a[1]),bx=X(b[0]),by=Y(b[1]),theta=Math.atan2(by-ay,bx-ax),k=8;
    return `<path d="M${ax},${ay}L${bx},${by}" stroke="${color}" fill="none" stroke-width="2.2" ${dashed?'stroke-dasharray="5 4"':''}/><path d="M${bx},${by}L${bx-k*Math.cos(theta-.4)},${by-k*Math.sin(theta-.4)}L${bx-k*Math.cos(theta+.4)},${by-k*Math.sin(theta+.4)}Z" fill="${color}"/>`;
  };
  let out=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="sectionTitle sectionDesc">
    <title id="sectionTitle">Primary meridional section at ${f.x_mm.toFixed(1)} mm closure</title>
    <desc id="sectionDesc">Horizontal shaft at radius zero. The orange sheave moves right, the fixed cup stays still, and the weight slides between their finite contact faces.</desc>
    <defs><pattern id="fixedHatch" width="9" height="9" patternUnits="userSpaceOnUse"><rect width="9" height="9" fill="#e5f0f1"/><path d="M-2,2L2,-2M0,9L9,0M7,11L11,7" stroke="#bdd4d8" stroke-width=".8"/></pattern>
    <pattern id="movingHatch" width="9" height="9" patternUnits="userSpaceOnUse"><rect width="9" height="9" fill="#fff0df"/><path d="M-2,7L2,11M0,0L9,9M7,-2L11,2" stroke="#e7c7a4" stroke-width=".8"/></pattern></defs>
    <rect width="${W}" height="${H}" fill="white"/>
    <g font-family="system-ui, sans-serif" font-size="12" fill="#607086">`;
  for(let r=0;r<=s.rim;r+=20){
    out+=line([z0,r],[z1,r],'#edf1f5');
    out+=text(z0-2,r,String(r),'text-anchor="end" dominant-baseline="middle"');
  }
  for(let z=Math.ceil(z0/20)*20;z<=z1;z+=20){
    out+=line([z,r0],[z,s.rim],'#f2f4f7');
    out+=text(z,r0-5,String(z),'text-anchor="middle"');
  }
  out+=`<text x="${(X(z0)+X(z1))/2}" y="${H-9}" text-anchor="middle">Axial position z [mm]</text>`;
  out+=`<text x="24" y="${H/2}" transform="rotate(-90,24,${H/2})" text-anchor="middle">Radius r [mm]</text>`;
  for(const b of s.bodies) out+=body(b.name,b.points,b.kind,b.moving?f.x_mm:0);
  out+=body('Belt',f.belt,'belt');
  out+=text((f.belt[0][0]+f.belt[1][0])/2,f.belt_radius,'BELT','text-anchor="middle" fill="white" font-size="11" font-weight="700"');
  for(const t of s.tracks) out+=`<path d="${path(t.points,t.moving?f.x_mm:0)}" fill="none" stroke="${col[t.kind]}" stroke-width="3.5"/>`;
  if(document.getElementById('path-toggle').checked && s.path.length) out+=`<path d="${path(s.path)}" fill="none" stroke="#527aa3" stroke-width="1.4" stroke-dasharray="3 4"/>`;
  if(f.block.length) out+=body('Sliding weight',f.block,'block');
  for(const [z,r] of f.spring_centers) out+=`<circle data-part="Spring wire" cx="${X(z)}" cy="${Y(r)}" r="${.8*scale}" fill="#66798e" stroke="#455365" stroke-width=".8"/>`;
  out+=line([z0,0],[z1,0],'#667789',1,'9 4 2 4');
  out+=text(z0+2,-2,'SHAFT AXIS · r = 0','font-size="11"');
  out+=text((s.spring_start+f.x_mm+s.spring_end)/2,-14,'COAXIAL SPRING','text-anchor="middle" font-size="11" font-weight="600"');
  for(const lab of s.labels) out+=text(lab.at[0]+(lab.kind==='moving'?f.x_mm:0),lab.at[1],lab.text,`text-anchor="middle" font-size="11" fill="${col[lab.kind]}" font-weight="700"`);
  out+=arrow([s.moving_root_z+f.x_mm-2,19],[s.moving_root_z+f.x_mm+6,19],col.moving);
  out+=text(s.moving_root_z+f.x_mm+2,22,'+x','text-anchor="middle" fill="#bb6827" font-size="13" font-weight="700"');
  if(f.com){
    out+=circle(...f.com,4.2,'#203247');
    if(document.getElementById('contacts-toggle').checked){
      for(const [c,N,kind] of [[point.lower,dynamics?.Nlo,'fixed'],[point.upper,dynamics?.Nhi,'moving']]){
        const pos=[c.Z*1000,c.R*1000], sign=N<0?-1:1;
        out+=circle(...pos,5,col[kind]);
        if(Number.isFinite(N))out+=arrow(pos,[pos[0]+6*sign*c.norm[1],pos[1]+6*sign*c.norm[0]],N<0?'#ba3448':col[kind],N<0);
      }
    }
    if(dynamics && !dynamics.valid){
      out+=`<path d="${path(f.block)}Z" fill="none" stroke="#ba3448" stroke-width="2.8" stroke-dasharray="6 4"/>`;
    }
  }else{
    out+=text((s.bodies[1].points[0][0]+s.moving_root_z)/2,48,'NO COMPATIBLE WEIGHT POSE','text-anchor="middle" fill="#a32839" font-size="11" font-weight="700"');
  }
  out+='</g></svg>';
  host.innerHTML=out;
}
