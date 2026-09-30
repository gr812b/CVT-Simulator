"""Publication figures for Results 4.4.1; plot verified frozen outputs only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import numpy as np

STUDY=Path(__file__).resolve().parents[1]
BLUE="#126a98";ORANGE="#c65d17";PURPLE="#79558c";GRAY="#66717a"
plt.rcParams.update({"font.family":"serif","font.serif":["STIXGeneral"],"mathtext.fontset":"stix",
                    "font.size":9.2,"axes.labelsize":9.2,"axes.titlesize":10,
                    "xtick.labelsize":8.5,"ytick.labelsize":8.5,"legend.fontsize":8.5,
                    "axes.spines.top":False,"axes.spines.right":False,
                    "axes.linewidth":.65,"lines.linewidth":1.5,"pdf.fonttype":42,
                    "savefig.dpi":300,"figure.facecolor":"white"})


def finish(fig,path):
    fig.savefig(path.with_suffix('.pdf'),metadata={"Creator":"CINDER frozen actuator-dynamics study","CreationDate":None,"ModDate":None})
    fig.savefig(path.with_suffix('.png'),dpi=300)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',type=Path,default=STUDY/'publication_inputs')
    p.add_argument('--figure-dir',type=Path,required=True)
    args=p.parse_args();args.figure_dir.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.input_dir/'primary_publication_audit.json').read_text())
    path=args.input_dir/'primary_publication.npz'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['plot_inputs_sha256']:
        raise ValueError('Publication input hash mismatch')
    z=np.load(path,allow_pickle=False)
    fig,axes=plt.subplots(1,2,figsize=(6.35,2.65),gridspec_kw={"width_ratios":[1.05,1]})
    fig.subplots_adjust(left=.085,right=.99,bottom=.25,top=.86,wspace=.37)
    ax=axes[0]
    for variant,color,label in [('full',BLUE,'Full primary'),('qs',ORANGE,'Quasi-static primary')]:
        pre=f'baseline_tight_{variant}__'
        t=z[pre+'time_s'];v=z[pre+'shift_speed_mm_s'];seg=z[pre+'segment_index']
        te,vpre,vpost=z[pre+'engagement']; first=True
        # Approach through the incoming endpoint only: no interpolation across
        # capture and no connection of different continuous segments.
        for s in np.unique(seg):
            ix=(seg==s)&(t<=te)&(t>=.045)
            if np.count_nonzero(ix)<2:continue
            ax.plot(1000*t[ix],v[ix],color=color,label=label if first else None)
            first=False
        ax.scatter([1000*te],[vpre],s=22,c=color,zorder=5)
        ax.scatter([1000*te],[vpost],s=25,facecolors='white',edgecolors=color,zorder=5)
        ax.plot([1000*te]*2,[vpost,vpre],color=color,lw=.7,ls=':')
        ax.text(1000*te,vpre+35,f'{1000*te:.2f} ms',color=color,fontsize=8,ha='center')
    ax.set(xlim=(45.5,63.4),ylim=(0,750),xlabel='Time from drive start [ms]',ylabel='Primary closing speed [mm/s]')
    ax.set_title('(a) Approach and first engagement',loc='left',pad=8)
    ax.set_xticks([46,50,54,58,62]);ax.grid(axis='y',alpha=.18);ax.legend(loc='upper left',frameon=False)
    ax=axes[1];budget=z['baseline_tight_full__budget_N'];running=0.
    for i,(value,color) in enumerate(zip(budget,[GRAY,ORANGE,PURPLE,BLUE])):
        if i<3:
            bottom=min(running,running+value);height=abs(value);running+=value
        else:bottom=0.;height=value
        ax.bar(i,height,bottom=bottom,width=.58,color=color,alpha=.9)
        if i<3: ax.plot([i+.29,i+.71],[running,running],color='#999999',lw=.7)
    for i,value in enumerate(budget):
        label=(f'{value:+.1f}' if i<3 else f'{value:.1f}').replace('-','−')
        y=[1440,720,300,280][i]
        ax.text(i,y,label,ha='center',fontsize=8.5)
    qs=budget[0]+budget[1]
    ax.hlines(qs,2.3,3.45,linestyle='--',color=GRAY,lw=.8)
    ax.text(3.46,qs,'QS',ha='left',va='center',color=GRAY,fontsize=8)
    ax.set_xticks(range(4),['Centrifugal','Spring','Pivot\nterms','Actuator\nforce'])
    ax.tick_params(axis='x',length=0,pad=7)
    ax.set(ylim=(0,1580),xlim=(-.55,3.8),ylabel='Axial force [N]')
    ax.set_title('(b) Force just after engagement',loc='left',pad=8)
    ax.set_yticks([0,400,800,1200]);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    finish(fig,args.figure_dir/'primary_engagement')

    fig=plt.figure(figsize=(6.35,3.05));gs=fig.add_gridspec(2,2,width_ratios=[1,1.12],height_ratios=[2,1],wspace=.37,hspace=.17)
    fig.subplots_adjust(left=.09,right=.985,bottom=.18,top=.87)
    ax=fig.add_subplot(gs[:,0]);colors=[BLUE,PURPLE,ORANGE]
    for i,(travel,color) in enumerate(zip(z['sweep_travel_percent'],colors)):
        ax.plot(z['sweep_ramp_ms'],z['sweep_maximum_percent'][i],'-o',ms=4,color=color,label=f'{travel:g}% travel')
    ax.set_xscale('log');ax.set_xticks(z['sweep_ramp_ms']);ax.xaxis.set_major_formatter(ScalarFormatter());ax.minorticks_off()
    ax.set(xlim=(4,300),ylim=(0,.056),xlabel='Torque rise time [ms]',ylabel='Peak correction / centrifugal force [%]')
    ax.set_yticks([0,.01,.02,.03,.04,.05]);ax.grid(axis='y',alpha=.18)
    ax.set_title('(a) Changing the torque rise time',loc='left',pad=8)
    ax.legend(loc='upper right',frameon=False,handlelength=1.8)
    ax=fig.add_subplot(gs[0,1]);ms=1000*z['response_time_s']
    for variant,color,label,ls in [('full',BLUE,'Full','-'),('qs',ORANGE,'Quasi-static','--')]:
        ax.plot(ms,z[f'response_tight_{variant}__shift_mm'],ls,color=color,label=label)
    ax.axvspan(0,5,color=GRAY,alpha=.12)
    ax.set(xlim=(0,305),ylim=(0,.9),ylabel='Shift response [mm]')
    ax.tick_params(labelbottom=False)
    ax.set_title('(b) −20 N m over 5 ms, mid travel',loc='left',pad=8)
    ax.legend(loc='lower right',frameon=False,ncol=2,handlelength=1.8,columnspacing=1)
    ax.grid(axis='y',alpha=.18)
    ax=fig.add_subplot(gs[1,1],sharex=ax)
    difference=1000*z['response_tight_difference__shift_mm']
    ax.plot(ms,difference,color=PURPLE)
    ax.axhline(0,color=GRAY,lw=.7);ax.axvspan(0,5,color=GRAY,alpha=.12)
    ax.set(ylim=(min(-.3,difference.min()-.3),difference.max()+.7),xlabel='Time from torque-ramp onset [ms]',ylabel='QS − full [μm]')
    ax.set_yticks([-1,0,1,2]);ax.set_xticks([0,100,200,300]);ax.grid(axis='y',alpha=.18)
    ax.text(.03,.85,f'Maximum {np.max(abs(difference)):.2f} μm',transform=ax.transAxes,ha='left',fontsize=8,color=PURPLE)
    finish(fig,args.figure_dir/'primary_torque_ramps')
    outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.figure_dir.glob('primary_*')) if p.suffix in ['.pdf','.png']}
    (args.figure_dir/'primary_figure_manifest.json').write_text(json.dumps({'input_sha256':manifest['plot_inputs_sha256'],'outputs':outputs},indent=2)+'\n')
    print(json.dumps(outputs,indent=2))


if __name__=='__main__':main()
