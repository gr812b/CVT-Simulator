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


def story_figures(args):
    source=args.input_dir/'secondary_story.npz'
    audit=json.loads((args.input_dir/'secondary_story_audit.json').read_text())
    assert audit['release_commit']=='7637a38b4fb9ec21dfb953c1c80a27ec5f389654'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==audit['plot_inputs_sha256']
    z=np.load(source,allow_pickle=False)
    fig,axes=plt.subplots(1,2,figsize=(6.35,2.8))
    fig.subplots_adjust(left=.09,right=.985,bottom=.24,top=.865,wspace=.38)
    pre='launch_tight__';i=audit['launch']['tight']['first_engaged_index']
    qs=z[pre+'helix_qs_reaction_force_N'][i]
    shaft=z[pre+'helix_dynamic_shaft_accel_force_N'][i]
    relative=z[pre+'helix_dynamic_shift_accel_force_N'][i]+z[pre+'helix_dynamic_curvature_force_N'][i]
    full=z[pre+'helix_full_reaction_force_N'][i]
    ax=axes[0]
    ax.bar([0,3],[qs,full],color=[GRAY,BLUE],width=.62)
    ax.bar(1,shaft,bottom=qs,color=BLUE,width=.62)
    ax.bar(2,relative,bottom=qs+shaft,color=ORANGE,width=.62)
    for x,y in [(0,qs),(1,qs+shaft),(2,full)]:ax.plot([x+.31,x+.69],[y,y],color=GRAY,lw=.65)
    ax.text(0,qs+90,f'{qs:.0f}',ha='center',fontsize=8.5)
    ax.annotate(f'{shaft:.2f}',xy=(1,qs+shaft/2),xytext=(1.08,2520),ha='center',fontsize=8.5,
                arrowprops={'arrowstyle':'-','lw':.6})
    ax.text(2,qs+shaft+relative/2,f'{relative:.0f}',ha='center',va='center',color='white',fontsize=9)
    ax.text(3,full+90,f'{full:.0f}',ha='center',fontsize=8.5)
    ax.set_xticks(range(4),['Quasi-static','Shaft\nacceleration','Relative sheave\nacceleration','Full'])
    ax.tick_params(axis='x',length=0,pad=8,labelsize=8)
    ax.set(ylim=(0,2800),ylabel='Helix closing force [N]')
    ax.set_title('(a) Immediately after engagement',loc='left',pad=10)
    ax=axes[1];t=z[pre+'time_s'];seg=z[pre+'segment_index'];mask=t>=.1
    for field,c,label,ls in [('helix_dynamic_shaft_accel_force_N',BLUE,'Shaft acceleration','-'),
                           ('relative',ORANGE,'Relative sheave acceleration','-'),
                           ('helix_dynamic_total_correction_N','#222222','Total correction','--')]:
        y=(z[pre+'helix_dynamic_shift_accel_force_N']+z[pre+'helix_dynamic_curvature_force_N']) if field=='relative' else z[pre+field]
        first=True
        for s in np.unique(seg[mask]):
            ix=np.flatnonzero(mask&(seg==s))
            ax.plot(t[ix],y[ix],ls,color=c,lw=1.0 if ls=='--' else 1.5,label=label if first else None);first=False
    ax.axhline(0,color=GRAY,lw=.55)
    ax.set(xlim=(.1,10),ylim=(-29,4),xlabel='Time from start [s]',ylabel='Helix-force correction [N]')
    ax.set_title('(b) Subsequent motion',loc='left',pad=10)
    ax.legend(loc='lower right',frameon=False,fontsize=7.6,handlelength=1.8)
    for ax in axes:ax.grid(axis='y',alpha=.17);ax.set_axisbelow(True)
    save(fig,args.figure_dir/'secondary_launch')

    fig,axes=plt.subplots(1,2,figsize=(6.35,2.85))
    fig.subplots_adjust(left=.095,right=.985,bottom=.20,top=.865,wspace=.37)
    for torque,c,ls in [(120,GRAY,':'),(240,BLUE,'--'),(480,PURPLE,'-')]:
        pre=f'm{torque}_tight__';t=(z[pre+'time_s']-.05)*1000;mask=t>=0
        assert len(np.unique(z[pre+'segment_index']))==1
        axes[0].plot(t[mask],z[pre+'helix_dynamic_total_correction_N'][mask],ls,color=c,label=f'{torque} N m added resistance')
        response=f'response_m{torque}_tight__'
        assert np.array_equal(z[pre+'time_s'],z[response+'time_s'])
        axes[1].plot(t[mask],z[response+'full_minus_qs_shift_mm'][mask],ls,color=c)
    axes[0].set(xlim=(0,100),ylim=(-20,185),ylabel='Helix-force correction [N]')
    axes[0].set_title('(a) Increasing resisting torque',loc='left',pad=10)
    axes[0].legend(loc='center right',bbox_to_anchor=(1,.63),frameon=False,fontsize=7.6,handlelength=2)
    axes[1].set(xlim=(0,100),ylim=(-.20,.01),
        ylabel='Shift-response difference [mm]\n(full − quasi-static)')
    axes[1].set_yticks([-.20,-.15,-.10,-.05,0])
    axes[1].set_title('(b) Effect on backshift',loc='left',pad=10)
    axes[1].text(4,-.187,'Negative: more backshift in full model',fontsize=7.7,color=GRAY)
    for ax in axes:
        ax.axvspan(0,10,color=GRAY,alpha=.12)
        ax.axhline(0,color=GRAY,lw=.55)
        ax.set_xlabel('Time from added load [ms]');ax.grid(axis='y',alpha=.17)
    save(fig,args.figure_dir/'secondary_backshift')


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
    fig=plt.figure(figsize=(6.35,3.15));gs=fig.add_gridspec(2,2,width_ratios=[1,1.08],hspace=.26,wspace=.39)
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

    story_figures(args)

    fig,axes=plt.subplots(2,2,figsize=(6.35,4.4))
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
    print('Exported three main figures and secondary_support (PDF and PNG).')


if __name__=='__main__':main()
