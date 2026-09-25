"""Publication contours for Results 4.2.4; run through canonical run.py.

All fields are dimensional or explicitly identified matrix condition numbers.
Contact masks break zero contours; interpolation across rejected cells cannot
supply a spurious root. No seed markers are presented as iteration paths.
"""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors, patheffects
from matplotlib.lines import Line2D
import numpy as np
from .evidence import digest, write_json
from .verification import audit
from .contour_evidence import retained_mask, verify_contours

BLUE, ORANGE, GREEN, PURPLE, GREY = '#176493', '#b04a28', '#267257', '#8a3674', '#777777'
STYLE = {'font.family':'STIXGeneral', 'mathtext.fontset':'stix', 'font.size':9,
    'axes.labelsize':9, 'axes.titlesize':9.5, 'xtick.labelsize':8, 'ytick.labelsize':8,
    'legend.fontsize':8, 'axes.linewidth':.6, 'lines.linewidth':1.2,
    'axes.spines.top':False, 'axes.spines.right':False, 'pdf.fonttype':42,
    'savefig.dpi':300, 'hatch.linewidth':.3}
HALO = [patheffects.withStroke(linewidth=2.6, foreground='white', alpha=.85)]


def save(fig, out, stem):
    # Fixed physical export size: no tight-bbox rescaling at manuscript width.
    # Publish only closed, complete files so packaging cannot observe a partial
    # export while a regeneration is underway.
    pdf = out / (stem+'.tmp.pdf')
    fig.savefig(pdf, metadata={'Creator':'CINDER closure study', 'CreationDate':None, 'ModDate':None})
    if not pdf.read_bytes().rstrip().endswith(b'%%EOF'):
        raise RuntimeError(f'Incomplete figure PDF: {pdf}')
    pdf.replace(out / (stem+'.pdf'))
    png = out / (stem+'.tmp.png')
    fig.savefig(png, dpi=300, metadata={'Software':'CINDER closure study'})
    png.replace(out / (stem+'.png'))
    plt.close(fig)


def axes_pair(height=3.75):
    fig=plt.figure(figsize=(6.5,height))
    return fig, [fig.add_axes([.087,.29,.358,.535]), fig.add_axes([.595,.29,.358,.535])]


def traction_axes(ax, xlim=(-.65,.65), ylim=(-.65,.65)):
    ax.set(xlim=xlim, ylim=ylim, xlabel=r'Primary traction $\lambda_p$', ylabel=r'Secondary traction $\lambda_s$')
    ax.tick_params(length=3, width=.6)


def residual_field(fig, ax, data, good, bounds, ticks, cbar_rect):
    norm=np.hypot(data['R_p'],data['R_s'])
    ax.set_facecolor('#e6e6e6')
    levels=np.geomspace(*bounds,19)
    field=ax.contourf(data['lambda_p'],data['lambda_s'],np.ma.array(norm,mask=~good),
        levels=levels,norm=colors.LogNorm(*bounds),cmap='PuBuGn',extend='both',corner_mask=False)
    field.set_edgecolor('face')
    # Mask ALL four corners of a cell if any is rejected. A sign change through
    # an inadmissible pole must never masquerade as an acceleration zero.
    for key,col,ls in [('R_p',BLUE,'-'),('R_s',ORANGE,'--')]:
        cs=ax.contour(data['lambda_p'],data['lambda_s'],np.ma.array(data[key],mask=~good),
            levels=[0],colors=[col],linestyles=ls,linewidths=1.3,corner_mask=False)
        cs.set_path_effects(HALO)
    bar=fig.colorbar(field,cax=fig.add_axes(cbar_rect),orientation='horizontal',ticks=ticks)
    bar.set_label(r'Acceleration mismatch $\sqrt{R_p^2+R_s^2}$ [m/s$^2$]',labelpad=3,fontsize=8.5)
    bar.ax.tick_params(labelsize=8,length=2,pad=2)


def zero_legend(fig, x=.59, y=.965):
    fig.legend(handles=[Line2D([],[],color=BLUE,label=r'$R_p=0$'),
        Line2D([],[],color=ORANGE,ls='--',label=r'$R_s=0$')],
        loc='upper left',bbox_to_anchor=(x,y),ncol=2,frameon=False,
        handlelength=1.9,columnspacing=1.3,handletextpad=.5,borderaxespad=0)


def robustness(values, actual, artifacts, out):
    fig, (left,right)=axes_pair(3.3)
    with np.load(artifacts/'full/states/upper_stop/physical_map.npz') as d:
        good=retained_mask(d)
        cs=left.contourf(d['lambda_p'],d['lambda_s'],d['cond_A_scaled'],
            levels=np.geomspace(1e3,2e6,24),norm=colors.LogNorm(1e3,2e6),cmap='cividis')
        cs.set_edgecolor('face')
        # Keep the sensitivity peak visible while identifying rejected trials.
        shade=left.contourf(d['lambda_p'],d['lambda_s'],(~good).astype(float),
            levels=[.5,1.5],colors=['#ffffff55'],hatches=['///'],corner_mask=False)
        shade.set_edgecolor('#777777');shade.set_linewidth(0)
        ij=np.unravel_index(np.argmax(d['cond_A_scaled']),d['cond_A_scaled'].shape)
        xy=(d['lambda_p'][ij[1]],d['lambda_s'][ij[0]])
        left.scatter(*xy,marker='x',s=32,color='#982a26',linewidths=1.3,zorder=7)
        left.annotate(r'Maximum: $1.05\times10^6$',xy,xytext=(-.60,-.55),
            fontsize=8,color='#7d2421',arrowprops=dict(arrowstyle='-',color='#7d2421',lw=.7),
            bbox=dict(facecolor='white',alpha=.88,edgecolor='none',pad=1.5))
    a=actual['upper_stop']
    left.scatter(a['lambda_p'],a['lambda_s'],marker='*',s=68,c='white',edgecolors='#222222',lw=.6,zorder=8)
    left.annotate(r'Operating pair'+'\n'+r'$8.56\times10^3$',(a['lambda_p'],a['lambda_s']),
        xytext=(.19,.30),fontsize=8,arrowprops=dict(arrowstyle='-',color='#222222',lw=.7),
        bbox=dict(facecolor='white',alpha=.9,edgecolor='none',pad=2))
    traction_axes(left);left.set_xticks([-.6,-.3,0,.3,.6]);left.set_yticks([-.6,-.3,0,.3,.6])
    left.set_title('(a) Fixed-traction solve: upper stop',loc='left',pad=10)
    cb=fig.colorbar(cs,cax=fig.add_axes([.087,.115,.358,.031]),orientation='horizontal',ticks=[1e3,1e4,1e5,1e6])
    cb.set_label(r'Equilibrated matrix condition number $\kappa_2(A_s)$',fontsize=8.5,labelpad=3)
    cb.ax.tick_params(labelsize=8,length=2,pad=2)
    fig.text(.087,.934,'Hatching: fails belt or support conditions',fontsize=8,color='#444444')
    with np.load(artifacts/'full/states/mid_shift/physical_map.npz') as d:
        residual_field(fig,right,d,retained_mask(d),(1,1e5),[1,1e2,1e4], [.595,.115,.358,.031])
    a=actual['mid_shift']
    right.scatter(a['lambda_p'],a['lambda_s'],marker='*',s=70,c=GREEN,edgecolors='white',lw=.7,zorder=8)
    right.annotate('Sticking solution',(a['lambda_p'],a['lambda_s']),xytext=(-.54,.33),fontsize=8,
        arrowprops=dict(arrowstyle='-',color=GREEN,lw=.7),color=GREEN,
        bbox=dict(facecolor='white',alpha=.95,edgecolor='none',pad=2))
    traction_axes(right);right.set_xticks([-.6,-.3,0,.3,.6]);right.set_yticks([-.6,-.3,0,.3,.6])
    right.set_title('(b) Sticking condition: mid-shift',loc='left',pad=10)
    zero_legend(fig)
    save(fig,out,'closure_robustness')


def fold(values, curve, artifacts, out):
    fig,(left,right)=axes_pair()
    with np.load(artifacts/'contour_audit/focused_contact_map.npz') as d:
        residual_field(fig,left,d,d['admissible'],(.1,200),[.1,1,10,100], [.087,.115,.358,.031])
    for r,col in zip(values['selected_roots'],(GREEN,PURPLE)):
        left.scatter(r['lambda_p'],r['lambda_s'],s=38,color=col,edgecolors='white',lw=.7,zorder=8)
        left.annotate(f"Root {int(r['root_id'])}",(r['lambda_p'],r['lambda_s']),xytext=(7,8),
            textcoords='offset points',fontsize=8,color=col,
            bbox=dict(facecolor='white',alpha=.9,edgecolor='none',pad=1))
    traction_axes(left,(-.310,-.258),(.30,.59));left.set_xticks([-.30,-.28,-.26])
    left.set_title('(a) Two intersections at one load',loc='left',pad=10)
    zero_legend(fig,x=.087,y=.965)
    x=np.array([r['lambda_s'] for r in curve]);y=np.array([r['secondary_boundary_torque_Nm'] for r in curve])
    good=np.array([r['physical'] for r in curve],dtype=bool)
    right.plot(x,y,color=GREY,ls=':',lw=1.4)
    right.plot(x,np.where(good,y,np.nan),color=BLUE,lw=1.5)
    ts=values['frozen']['selected_secondary_torque_Nm']
    right.axhline(ts,color=ORANGE,ls='--',lw=1.)
    right.text(.43,ts+.6,f'Selected load: {ts:.2f} N m',ha='center',fontsize=8,color=ORANGE,
        bbox=dict(facecolor='white',edgecolor='none',pad=1,alpha=.8))
    for r,col in zip(values['selected_roots'],(GREEN,PURPLE)):
        right.scatter(r['lambda_s'],ts,s=38,color=col,edgecolors='white',lw=.7,zorder=8)
        right.annotate(f"Root {int(r['root_id'])}\n"+rf"$N_s={r['N_s_N']/1000:.3f}$ kN",
            (r['lambda_s'],ts),xytext=((-3 if r['root_id']==1 else 3),-28),
            textcoords='offset points',ha=('left' if r['root_id']==1 else 'right'),fontsize=8,color=col)
    f=values['frozen']['fold']
    right.scatter(f['lambda_s'],f['secondary_boundary_torque_Nm'],marker='^',s=24,color='#333333',zorder=7)
    right.annotate(f"Turn: {f['secondary_boundary_torque_Nm']:.2f} N m",
        (f['lambda_s'],f['secondary_boundary_torque_Nm']),xytext=(.453,198.9),fontsize=8,
        arrowprops=dict(arrowstyle='-',color='#333333',lw=.6))
    right.set(xlim=(.30,.59),ylim=(179,201),xlabel=r'Secondary traction $\lambda_s$',
        ylabel=r'Required secondary boundary torque [N m]')
    right.set_xticks([.3,.4,.5,.58]);right.set_yticks([180,185,190,195,200])
    right.set_title('(b) One connected sticking branch',loc='left',pad=10)
    fig.legend(handles=[Line2D([],[],color=BLUE,label='Admissible'),
        Line2D([],[],color=GREY,ls=':',label='Fails wrap contact')],
        loc='upper left',bbox_to_anchor=(.595,.965),ncol=2,frameon=False,handlelength=1.5,
        handletextpad=.4,columnspacing=.8,borderaxespad=0)
    fig.text(.595,.12,r'Fixed primary boundary torque: $-81.15$ N m',fontsize=8)
    fig.text(.595,.078,'Grey in (a): fails local wrap compression.',fontsize=8,color='#555555')
    save(fig,out,'sticking_closure_fold')


def build(artifacts,out):
    artifacts,out=Path(artifacts),Path(out)
    values,starts,actual,curve=audit(artifacts)
    contours=verify_contours(artifacts)
    values['contour_execution']=contours['run_id']
    values['operating_root_condition_range']=[min(r['A_condition_scaled'] for r in actual.values()),
        max(r['A_condition_scaled'] for r in actual.values())]
    out.mkdir(parents=True,exist_ok=True)
    with plt.rc_context(STYLE):
        robustness(values,actual,artifacts,out)
        fold(values,curve,artifacts,out)
    write_json(out/'closure_values.json',values)
    write_json(out/'closure_figure_provenance.json',{
        'run_id':values['run_id'],'contour_run_id':contours['run_id'],
        'source_script':'results/cinder-v1.1.2/studies/closure-conditioning/analysis/publication_plots.py',
        'plot_script_sha256':digest(Path(__file__)),
        'command':'python studies/closure-conditioning/run.py --plot-only --artifacts-dir <reviewed-evidence> --figure-dir <output>',
        'figures':{
            'closure_robustness.pdf':{'label':'fig:verification_closure_robustness','panels':[
                'Upper-stop static-capacity grid: unmasked equilibrated condition field, independently rejected trials hatched, sampled maximum and accepted pair.',
                'Mid-shift dimensional joint acceleration mismatch, both zero contours, solved operating root; contact-inadmissible cells masked.']},
            'sticking_closure_fold.pdf':{'label':'fig:verification_closure_fold','panels':[
                'Selected frozen opening state at the exact selected signed bench loads: dimensional mismatch, both zero contours and both admissible roots.',
                'Locally corrected open branch versus secondary traction, fixed primary boundary torque; same roots and selected secondary torque. Failed wrap contact dotted.']}},
        'scope':'Frozen algebraic mechanics; no new transient, root census or full map. No interpolation across rejected contour cells.',
        'output_sha256':{p.name:digest(p) for p in sorted(out.iterdir()) if p.name in
            ('closure_robustness.pdf','closure_robustness.png','sticking_closure_fold.pdf','sticking_closure_fold.png','closure_values.json')}})
    print(f'Publication figures checked and written: {out}')
