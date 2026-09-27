"""Secondary publication figures from hashed release-1.1.2 outputs.

No smoothing or force interpolation. Continuous segments are drawn separately;
the first failed local-contact state ends the admissible response, even if the
formal continuation later returns to positive loading.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

STUDY=Path(__file__).resolve().parents[1]
BLUE='#126a98'; ORANGE='#c65d17'; PURPLE='#79558c'; GRAY='#66717a'
plt.rcParams.update({'font.family':'serif','font.serif':['STIXGeneral'],'mathtext.fontset':'stix',
 'font.size':9.2,'axes.labelsize':9.2,'axes.titlesize':10,'xtick.labelsize':8.5,
 'ytick.labelsize':8.5,'legend.fontsize':8.5,'axes.spines.top':False,'axes.spines.right':False,
 'axes.linewidth':.65,'lines.linewidth':1.5,'pdf.fonttype':42,'savefig.dpi':300,'figure.facecolor':'white'})


def save(fig,path):
    # Complete both exports before replacing an existing publication asset.
    # An interrupted render must not leave a truncated PDF in the manuscript.
    with tempfile.TemporaryDirectory(prefix='secondary-export-',dir=path.parent) as tmp:
        pdf=Path(tmp)/'figure.pdf';png=Path(tmp)/'figure.png'
        fig.savefig(pdf,metadata={'Creator':'CINDER frozen secondary study','CreationDate':None,'ModDate':None})
        fig.savefig(png,dpi=300)
        if not pdf.read_bytes().rstrip().endswith(b'%%EOF'):
            raise RuntimeError('Incomplete secondary PDF export')
        pdf.replace(path.with_suffix('.pdf'));png.replace(path.with_suffix('.png'))
    plt.close(fig)


def segments(ax,z,prefix,field,*,color,label,offset=.03,valid_only=False,style='-',scale=1.):
    t=z[prefix+'__time_s']; seg=z[prefix+'__segment_index']; y=z[prefix+'__'+field]
    stop=int(z[prefix+'__first_invalid_index']) if valid_only else len(t)
    for i,s in enumerate(np.unique(seg[:stop])):
        ix=np.flatnonzero((seg==s)&(np.arange(len(t))<stop))
        ax.plot((t[ix]-offset)*1000,scale*y[ix],style,color=color,label=label if i==0 else None)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',type=Path,default=STUDY/'publication_inputs')
    p.add_argument('--figure-dir',type=Path,required=True)
    args=p.parse_args();args.figure_dir.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.input_dir/'secondary_publication_audit.json').read_text())
    source=args.input_dir/'secondary_publication.npz'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=manifest['plot_inputs_sha256']:
        raise ValueError('Secondary plot input hash mismatch')
    z=np.load(source,allow_pickle=False)
    fig=plt.figure(figsize=(6.35,3.55));gs=fig.add_gridspec(2,2,width_ratios=[1,1.08],hspace=.26,wspace=.39)
    fig.subplots_adjust(left=.085,right=.985,bottom=.15,top=.90)
    ax=fig.add_subplot(gs[:,0]);pre='commercial_tight_full_stress__'
    time=(z[pre+'time_s']-.05)*1000; H=z[pre+'helix_motion_ratio_rad_per_m']
    shaft=-H*z[pre+'dynamic_torque_omega_Nm']; axial=-H*z[pre+'dynamic_torque_axial_Nm']
    ax.plot(time,shaft,color=BLUE,label='Shaft acceleration')
    ax.plot(time,axial,color=ORANGE,label='Sheave acceleration')
    ax.plot(time,z[pre+'helix_dynamic_force_correction_N'],'--',color='#252525',lw=1.,label='Total correction')
    ax.axhline(0,color=GRAY,lw=.55);ax.axvspan(0,25,color=GRAY,alpha=.12)
    ax.set(xlim=(0,375),ylim=(-40,101),xlabel='Time from added load [ms]',ylabel='Helix-force correction [N]')
    ax.set_title('(a) Contributions to closing force',loc='left',pad=10)
    ax.legend(frameon=False,loc='center right',bbox_to_anchor=(1,.42),handlelength=2.)
    ax.grid(axis='y',alpha=.17)
    time=z['commercial_response_time_s']*1000
    for row,field,title,ylab in [(0,'shift_mm','(b) Extra shift','Shift response [mm]'),(1,'primary_rpm','(c) Primary-speed change','Speed response [rpm]')]:
        ax=fig.add_subplot(gs[row,1])
        for v,c,l,ls in [('full',BLUE,'Full','-'),('qs',ORANGE,'Quasi-static','--')]:
            ax.plot(time,z[f'commercial_response_tight_{v}__'+field],ls,color=c,label=l)
        ax.axvspan(0,25,color=GRAY,alpha=.12);ax.axhline(0,color=GRAY,lw=.5)
        ax.set(xlim=(0,375),ylabel=ylab);ax.set_title(title,loc='left',pad=7);ax.grid(axis='y',alpha=.17)
        if row==0:ax.tick_params(labelbottom=False);ax.legend(frameon=False,loc='upper right',ncol=2,handlelength=1.5,columnspacing=1.)
        else:ax.set_xlabel('Time from added load [ms]')
    save(fig,args.figure_dir/'secondary_continuous_response')

    # The reference cases precede the hardware extension in the manuscript.
    # Left: rapid loading can have opposing dynamic terms and a small response.
    # Right: close positions do not settle arrival at a contact limit.
    fig,axes=plt.subplots(2,2,figsize=(6.35,4.2))
    fig.subplots_adjust(left=.10,right=.985,bottom=.115,top=.925,wspace=.38,hspace=.68)
    ax=axes[0,0];pre='stock_tight_full'
    t=z[pre+'__time_s'];seg=z[pre+'__segment_index']
    shaft=z[pre+'__e58_helix_physical_shaft_term_Nm']
    relative=(z[pre+'__e58_helix_physical_shift_term_Nm']
              +z[pre+'__e58_helix_physical_curvature_term_Nm'])
    for values,c,label,ls in [(shaft,BLUE,'Shaft acceleration','-'),
        (relative,ORANGE,'Relative sheave motion','-'),
        (shaft+relative,'#252525','Total correction','--')]:
        for i,s in enumerate(np.unique(seg)):
            ix=np.flatnonzero(seg==s)
            ax.plot(1000*(t[ix]-.03),values[ix],ls,color=c,
                    lw=1. if ls=='--' else 1.5,label=label if i==0 else None)
    ax.axvspan(0,2,color=GRAY,alpha=.12);ax.axhline(0,color=GRAY,lw=.55)
    ax.set(xlim=(0,8),ylim=(-1.05,.8),xlabel='Time from added load [ms]',
           ylabel='Helix-torque correction [N m]')
    ax.set_title('(a) Rapid load: signed contributions',loc='left',pad=10)
    ax.legend(frameon=True,facecolor='white',edgecolor='none',framealpha=.95,
              fontsize=7.8,loc='lower right',handlelength=1.6)
    ax=axes[1,0]
    ax.plot(1000*z['stock_tight_response_time_s'],z['stock_tight_shift_difference_mm'],color=BLUE)
    ax.axhline(0,color=GRAY,lw=.6)
    ax.set(xlim=(0,352),ylim=(-.06,.015),xlabel='Time from added load [ms]',
           ylabel='Full − quasi-static shift [mm]')
    ax.set_title('(b) Rapid load: motion difference',loc='left',pad=10)
    ax=axes[0,1]
    for v,c,l,ls in [('full',BLUE,'Full','-'),('qs',ORANGE,'Quasi-static','--')]:
        pre=f'severe_tight_{v}'
        stop=int(z[pre+'__first_invalid_index'])
        assert stop==int(z[pre+'__exit_index'])
        assert z[pre+'__sample_location'][stop-1]=='segment_end'
        assert abs(abs(z[pre+'__lambda_primary'][stop-1])-.65)<1e-8
        assert np.all(z[pre+'__primary_min_local_normal_N_per_rad'][:stop]>0)
        t=1000*(z[pre+'__time_s'][:stop]-.03)
        demand=np.abs(z[pre+'__lambda_primary'][:stop])/.65
        ax.plot(t,demand,ls,color=c,label=l)
        t=t[-1];y=demand[-1]
        ax.scatter([t],[y],s=24,color=c,zorder=5)
        ax.plot([t,t],[1.,1.046],color=c,ls=':',lw=.8)
    ax.axhline(1,color=GRAY,lw=.7)
    ax.text(350.8,1.006,'Sticking limit',fontsize=8,color=GRAY,va='bottom')
    ax.set(xlim=(350,400),ylim=(.83,1.075),xlabel='Time from torque-change onset [ms]',
           ylabel=r'Primary static demand $|\lambda_p|/\mu_s$')
    ax.set_title('(c) Reversal: approach to slip',loc='left',pad=10)
    ax.legend(frameon=False,loc='lower right',handlelength=1.5)
    times=[1000*(z[f'severe_tight_{v}__time_s'][int(z[f'severe_tight_{v}__exit_index'])]-.03) for v in ('qs','full')]
    ax.annotate('',xy=(times[0],1.042),xytext=(times[1],1.042),
                arrowprops={'arrowstyle':'|-|','lw':.8,'color':'#252525'})
    ax.text(sum(times)/2,1.053,f'{times[1]-times[0]:.2f} ms',ha='center',fontsize=8)
    ax=axes[1,1];budget=z['severe_inertia_budget_kg']
    ax.bar([0,1],budget,color=[BLUE,GRAY],width=.58)
    for x,y in enumerate(budget):ax.text(x,y+.2,f'{y:.2f} kg',ha='center')
    ax.text(0,4.1,f'{budget[0]/sum(budget):.0%}\nof total',ha='center',va='center',color='white',fontsize=8.5)
    ax.set_xticks([0,1],['Helix reflection','Other direct\ncontributions'])
    ax.tick_params(axis='x',length=0,pad=8);ax.set(ylim=(0,9.5),ylabel='Direct shift-inertia coefficient [kg]')
    ax.set_title('(d) Reversal: direct shift inertia',loc='left',pad=10)
    for ax in axes.ravel():ax.grid(axis='y',alpha=.17);ax.set_axisbelow(True)
    save(fig,args.figure_dir/'secondary_sensitive_transient')

    fig,axes=plt.subplots(2,2,figsize=(6.35,5.05))
    fig.subplots_adjust(left=.10,right=.985,bottom=.105,top=.93,wspace=.38,hspace=.57)
    ax=axes[0,0]
    for v,c,l,ls in [('full',BLUE,'Full','-'),('qs',ORANGE,'Quasi-static','--')]:
        pre=f'stock_tight_{v}'
        segments(ax,z,pre,'shift_mm',color=c,label=l,style=ls)
    ax.set(xlim=(0,352),xlabel='Time from load onset [ms]',ylabel='Shift position [mm]')
    ax.set_title('(a) Stock case: absolute motion',loc='left',pad=10);ax.legend(frameon=False)
    ax=axes[0,1]
    ax.plot(1000*z['stock_tight_response_time_s'],z['stock_tight_shift_difference_mm'],color=BLUE)
    ax.axhline(0,color=GRAY,lw=.6)
    ax.set(xlim=(0,352),xlabel='Time from load onset [ms]',ylabel='Full − quasi-static shift [mm]')
    ax.set_title('(b) Stock case: resolved separation',loc='left',pad=10)
    ax=axes[1,0];pre='severe_tight_full'
    for field,c,l,ls in [('e58_helix_qs_margin_Nm',GRAY,'Quasi-static diagnostic','--'),('e58_helix_physical_shift_term_Nm',ORANGE,'Shift contribution',':'),('e58_helix_actual_margin_Nm',BLUE,'Total reaction','-')]:
        segments(ax,z,pre,field,color=c,label=l,style=ls)
    ti=1000*(z[pre+'__time_s'][int(z[pre+'__first_invalid_index'])]-.03)
    ax.axvspan(ti,400,color=GRAY,alpha=.12);ax.axhline(0,color=GRAY,lw=.5)
    ax.set(xlim=(390,400),ylim=(-3.5,3),xlabel='Time from torque-change onset [ms]',ylabel='Helix torque [N m]')
    ax.set_title('(c) Severe case: algebraic continuation',loc='left',pad=10)
    ax.legend(frameon=False,loc='lower left',fontsize=8,handlelength=1.5)
    ax=axes[1,1]
    for v,c,l,ls in [('full',BLUE,'Full','-'),('qs',ORANGE,'Quasi-static','--')]:
        pre=f'severe_tight_{v}'
        segments(ax,z,pre,'primary_min_local_normal_N_per_rad',color=c,label=l,style=ls)
        i=int(z[pre+'__first_invalid_index']); t=(z[pre+'__time_s'][i]-.03)*1000;y=z[pre+'__primary_min_local_normal_N_per_rad'][i]
        ax.scatter(t,y,s=25,facecolors='white',edgecolors=c,zorder=5)
    ax.axhspan(-1,0,color='#b95b51',alpha=.12);ax.axhline(0,color=GRAY,lw=.5)
    ax.set(xlim=(386,398),ylim=(-.85,.8),xlabel='Time from torque-change onset [ms]',ylabel='Minimum primary loading [N/rad]')
    ax.set_title('(d) Local contact limit',loc='left',pad=10)
    ax.legend(frameon=False,loc='upper right')
    for ax in axes.ravel():ax.grid(axis='y',alpha=.17)
    save(fig,args.figure_dir/'secondary_support')
    print('Exported two main figures and secondary_support (PDF and PNG).')


if __name__=='__main__':main()
