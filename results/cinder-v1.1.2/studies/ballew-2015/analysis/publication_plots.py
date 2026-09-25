"""Publication figures for the frozen Ballew benchmark; no simulation rerun."""
from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))

# --- end results study-local import bootstrap ---

import argparse
import hashlib
from io import BytesIO
import subprocess
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.ticker import MultipleLocator

ROOT = Path(__file__).resolve().parents[1]
BLUE, ORANGE, GREEN, GREY = '#176493', '#b04a28', '#267257', '#666666'
CHANNELS = ('state.primary_angular_speed', 'state.secondary_angular_speed',
    'geometry.effective_ratio_secondary_over_primary',
    'actuation.primary.total_clamp_force', 'observer.primary_slip_dissipation',
    'observer.secondary_slip_dissipation')


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verified_inputs(base):
    manifest = base/'publication_inputs.json'
    if manifest.exists():
        record = json.loads(manifest.read_text())
        for name, h in record['files'].items():
            if digest(base/name) != h:
                raise ValueError(f'Publication input changed: {name}')
        if record['cinder_version'] != '1.1.2':
            raise ValueError('Wrong frozen simulator version')
        return record
    records = {}
    for protocol in ('closed-loop', 'force-replay'):
        d = base/protocol
        r = json.loads((d/'execution_provenance.json').read_text())
        if r['cinder_version'] != '1.1.2':
            raise ValueError(f'Wrong version: {protocol}')
        for name, h in r['output_sha256'].items():
            if digest(d/name) != h:
                raise ValueError(f'Execution output changed: {d/name}')
        records[protocol] = digest(d/'execution_provenance.json')
    return records


def style():
    plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
        'font.size':9, 'axes.labelsize':9, 'axes.titlesize':10,
        'axes.spines.top':False, 'axes.spines.right':False,
        'axes.linewidth':.6, 'lines.linewidth':1.05, 'xtick.labelsize':8.5,
        'ytick.labelsize':8.5, 'legend.fontsize':8.5, 'pdf.fonttype':42,
        'ps.fonttype':42, 'savefig.dpi':220})


def segmented(ax, data, values, color, label=None, lw=.85, alpha=1):
    t, ids = data['time_s'], data['segment_id']
    cuts = np.r_[0, np.flatnonzero(np.diff(ids))+1, t.size]
    pieces = [np.column_stack((t[a:b], values[a:b]))
              for a,b in zip(cuts[:-1],cuts[1:]) if b-a > 1]
    c = LineCollection(pieces, colors=color, linewidths=lw, alpha=alpha,
                       label=label, zorder=2)
    ax.add_collection(c)
    return c


def tidy(ax, letter):
    ax.grid(axis='y', color='#dedede', lw=.45, zorder=0)
    ax.text(.015, .97, f'({letter})', transform=ax.transAxes,
            va='top', fontsize=10)
    ax.tick_params(length=3, width=.6)


def save(fig, out, name):
    # Complete the export in memory before replacing a deliverable. A zero
    # process status alone does not establish that a PDF stream was finalized.
    pdf=BytesIO()
    fig.savefig(pdf,format='pdf',metadata={'CreationDate':None,'ModDate':None})
    data=pdf.getvalue()
    if not data.rstrip().endswith(b'%%EOF'):
        raise RuntimeError(f'Incomplete PDF export: {name}')
    tmp=out/f'{name}.pdf.tmp';tmp.write_bytes(data)
    subprocess.run(['pdfinfo',str(tmp)],check=True,stdout=subprocess.DEVNULL)
    tmp.replace(out/f'{name}.pdf')
    png=BytesIO()
    fig.savefig(png,format='png',metadata={'Software':'CINDER Ballew publication'})
    tmp=out/f'{name}.png.tmp';tmp.write_bytes(png.getvalue());tmp.replace(out/f'{name}.png')
    plt.close(fig)


def protocols(base, out):
    refs = [np.genfromtxt(ROOT/'reference'/name,delimiter=',',names=True)
            for name in ('figure_41_input_rpm.csv','figure_41_output_rpm.csv',
                         'figure_45_primary_force.csv')]
    fig, axes = plt.subplots(3,2,figsize=(6.5,5.5),sharex=True)
    fig.subplots_adjust(left=.105,right=.985,bottom=.09,top=.88,wspace=.17,hspace=.23)
    fig.text(.325,.967,'Reconstructed feedback',ha='center',fontsize=11)
    fig.text(.795,.967,'Published force replay',ha='center',fontsize=11)
    for j, name in enumerate(('closed-loop','force-replay')):
        d=np.load(base/name/'segmented_report.npz')
        native=np.load(base/name/'native_trace.npz')
        for i, key in enumerate(CHANNELS[:2]):
            # Full native state CVT indices are recorded by retention; use
            # exported native angular speed channels when prepared.
            values = native[key] if key in native.files else native['full_state'][i]
            segmented(axes[i,j],native,values*30/np.pi,BLUE,label='CINDER')
            r=refs[i]
            axes[i,j].plot(r[r.dtype.names[0]],r[r.dtype.names[1]],'o',color=GREY,
                          markersize=2.2,markeredgewidth=0,label='Ballew, digitized',zorder=3)
        if j==0:
            segmented(axes[2,j],d,d['actuation.primary.total_clamp_force']/1000,
                      BLUE,label='CINDER')
        else:
            r=refs[2]
            axes[2,j].plot(r[r.dtype.names[0]],r[r.dtype.names[1]]/1000,
                          color=ORANGE,lw=1.2,label='Prescribed input')
        r=refs[2]
        axes[2,j].plot(r[r.dtype.names[0]][1:],r[r.dtype.names[1]][1:]/1000,
                      'o',color=GREY,markersize=1.8,markeredgewidth=0,zorder=3)
        for i in range(3):
            tidy(axes[i,j],'abcdef'[2*i+j]); axes[i,j].set_xlim(0,5)
            axes[i,j].set_ylim([(0,2900),(0,1400),(0,3.3)][i])
            axes[i,j].yaxis.set_major_locator(MultipleLocator([1000,400,1][i]))
            if j: axes[i,j].tick_params(labelleft=False)
        axes[2,j].set_xlabel('Time (s)')
    for ax,label in zip(axes[:,0],('Primary speed (rpm)','Secondary speed (rpm)','Primary clamp (kN)')):
        ax.set_ylabel(label)
    handles, labels = axes[0,0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.55,.946),
               ncol=2, frameon=False, handlelength=2)
    axes[2,1].text(.96,.10,'Prescribed input',transform=axes[2,1].transAxes,
                   ha='right',color=ORANGE,fontsize=9)
    axes[2,0].text(.96,.10,'Controller output',transform=axes[2,0].transAxes,
                   ha='right',color=BLUE,fontsize=9)
    # A same-history detail, not a smoothed overlay, resolves the feedback ripple.
    inset=axes[0,0].inset_axes([.47,.16,.49,.46])
    d=np.load(base/'closed-loop'/'native_trace.npz')
    values=d['state.primary_angular_speed'] if 'state.primary_angular_speed' in d.files else d['full_state'][0]
    segmented(inset,d,values*30/np.pi,BLUE,lw=.8)
    inset.set_xlim(4,4.10);inset.set_ylim(2290,2750)
    inset.set_xticks([4,4.05,4.1]);inset.set_xticklabels(['4.00','4.05','4.10'])
    inset.set_yticks([2300,2500,2700]);inset.tick_params(labelsize=7,length=2)
    inset.set_title('Resolved interval',fontsize=8,pad=2)
    save(fig,out,'protocol_comparison')


def internal(base,out):
    d=np.load(base/'closed-loop'/'segmented_report.npz')
    shaft=d[CHANNELS[0]]/d[CHANNELS[1]]
    geometric=d[CHANNELS[2]]
    fig=plt.figure(figsize=(6.5,4.25))
    gs=fig.add_gridspec(2,2,left=.105,right=.985,bottom=.105,top=.925,
                       hspace=.55,wspace=.30,height_ratios=[1,1])
    a=fig.add_subplot(gs[0,:]);b=fig.add_subplot(gs[1,0]);c=fig.add_subplot(gs[1,1])
    for ax in (a,b):
        segmented(ax,d,geometric,BLUE,r'Radius ratio $r_{s,\mathrm{eff}}/r_{p,\mathrm{eff}}$',lw=.6)
        segmented(ax,d,shaft,ORANGE,r'Shaft-speed ratio $\omega_p/\omega_s$',lw=.95)
        ax.set_ylim(.25,2.75);ax.set_ylabel('Ratio');ax.set_xlabel('Time (s)')
        ax.set_yticks([.5,1,1.5,2,2.5])
    a.set_xlim(0,5);b.set_xlim(4,4.10)
    a.axvspan(4,4.1,facecolor='#eeeeee',edgecolor='none',zorder=0)
    a.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,frameon=False,
             borderaxespad=0,handlelength=2)
    b.set_xticks([4,4.025,4.05,4.075,4.1]);b.set_xticklabels(['4.000','4.025','4.050','4.075','4.100'])
    b.set_title('Resolved interval',loc='left',pad=7)
    p=d[CHANNELS[4]]/1000;s=d[CHANNELS[5]]/1000
    c.fill_between(d['time_s'],0,p,color=BLUE,alpha=.25,lw=0,label='Primary')
    c.fill_between(d['time_s'],p,p+s,color=GREEN,alpha=.25,lw=0,label='Secondary')
    segmented(c,d,p,BLUE,lw=.85);segmented(c,d,p+s,GREEN,lw=.85)
    c.set_xlim(0,5);c.set_ylim(0,21.5);c.set_yticks([0,5,10,15,20])
    c.set_xlabel('Time (s)');c.set_ylabel('Cumulative slip loss (kJ)')
    c.text(4.95,20.6,f'Total {p[-1]+s[-1]:.1f} kJ',ha='right',fontsize=8.5)
    c.legend(loc='upper left',frameon=False,bbox_to_anchor=(.09,.97),handlelength=1)
    for ax,letter in zip((a,b,c),'abc'):tidy(ax,letter)
    save(fig,out,'internal_response')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,default=ROOT/'publication_inputs')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--figure',choices=('all','protocol-comparison','internal-response'),
                        default='all',help='regenerate only the selected figure, or both')
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    record=verified_inputs(args.input_dir)
    provenance=args.output_dir/'plot_provenance.json'
    previous=json.loads(provenance.read_text()) if provenance.exists() else {}
    selected={'protocol-comparison':('protocol_comparison',protocols),
              'internal-response':('internal_response',internal)}
    regenerated=[]
    style()
    for choice,(name,draw) in selected.items():
        if args.figure in ('all',choice):
            draw(args.input_dir,args.output_dir)
            regenerated.extend(f'{name}.{suffix}' for suffix in ('pdf','png'))
    outputs={p.name:digest(p) for p in sorted(args.output_dir.glob('*'))
             if p.suffix in ('.pdf','.png')}
    # Retained figures keep their original generator attribution. Selecting one
    # figure does not imply that the other was regenerated by the current code.
    sources={}
    for name,h in outputs.items():
        if name in regenerated:
            sources[name]=digest(Path(__file__))
        elif previous.get('outputs',{}).get(name)==h:
            sources[name]=previous.get('output_plotter_sha256',{}).get(
                name,previous.get('plotter_sha256'))
        else:
            raise ValueError(f'Unverified retained figure: {name}')
    manifest={'input_manifest':record,'plotter_sha256':digest(Path(__file__)),
              'figure_width_inches':6.5,'event_segments_drawn_separately':True,
              'smoothing_applied':False,
              'regenerated_outputs':regenerated,'output_plotter_sha256':sources,
              'outputs':outputs}
    provenance.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Exported {args.figure}; no simulation rerun.')

if __name__=='__main__':
    main()
