"""Results 4.2.4 publication figures from verified, registered evidence.

Use canonical run.py --plot-only. Start markers are not iteration paths.
The selected fold is frozen mechanics, not a simulated time history.
"""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from .evidence import digest, write_json
from .verification import audit, NAMES

BLUE, ORANGE, GREEN, PURPLE, GREY = "#21618c", "#b44e2b", "#38735c", "#86548d", "#888888"
STYLE = {"font.family":"STIXGeneral", "mathtext.fontset":"stix", "font.size":9,
    "axes.labelsize":9, "axes.titlesize":10, "xtick.labelsize":8, "ytick.labelsize":8,
    "legend.fontsize":8, "axes.spines.top":False, "axes.spines.right":False,
    "axes.linewidth":.6, "lines.linewidth":1.2, "pdf.fonttype":42, "savefig.dpi":300}


def save(fig, out, name):
    fig.savefig(out / (name+".pdf"), metadata={"CreationDate":None,"ModDate":None})
    fig.savefig(out / (name+".png"))
    plt.close(fig)


def robustness(values, starts, actual, out):
    fig=plt.figure(figsize=(6.5,3.1))
    gs=fig.add_gridspec(1,2,left=.15,right=.98,bottom=.19,top=.79,wspace=.42,width_ratios=(1.13,1))
    ax=fig.add_subplot(gs[0,0])
    lookup={r["state"]:r for r in values["map_values"]}
    maxima=[lookup[n]["maximum"] for n in NAMES]
    roots=[lookup[n]["root"] for n in NAMES]
    ax.scatter(maxima,range(4),s=34,color=BLUE,label="Map maximum",zorder=3)
    ax.scatter(roots,range(4),s=28,marker="D",facecolors="white",edgecolors=GREEN,label="Accepted root",zorder=4)
    for i,x in enumerate(maxima):
        exponent=int(np.floor(np.log10(x)))
        ax.annotate(rf"${x/10**exponent:.2f}\times10^{{{exponent}}}$",(x,i),xytext=(0,9),
                    textcoords="offset points",ha="center",fontsize=8,color=BLUE)
    ax.set_yticks(range(4),["Low-ratio seat","Mid-shift","Upper stop","Opening, 70%"])
    ax.set(xscale="log",xlim=(2e3,2.8e6),ylim=(3.45,-.65),xlabel=r"Equilibrated $\kappa_2(A_s)$")
    ax.set_xticks([1e4,1e5,1e6]); ax.minorticks_off()
    ax.grid(axis="x",color="#e6e6e6",lw=.6)
    ax.set_title("(a) Fixed-traction response",loc="left",pad=23)
    ax.legend(loc="lower left",bbox_to_anchor=(-.02,1.0),ncol=2,frameon=False,
              handletextpad=.3,columnspacing=.8,borderaxespad=0)
    ax=fig.add_subplot(gs[0,1])
    selected=[r for r in starts if r["state"]=="mid_shift"]
    for accepted,color,marker,label in ((True,BLUE,"o","Accepted (42)"),(False,ORANGE,"x","Not accepted (7)")):
        r=[r for r in selected if r["accepted"]==accepted]
        ax.scatter([x["start_lambda_p"] for x in r],[x["start_lambda_s"] for x in r],
                   s=24,c=color,marker=marker,linewidths=.9,label=label)
    a=actual["mid_shift"]
    ax.scatter(a["lambda_p"],a["lambda_s"],s=62,marker="*",color=GREEN,edgecolors="white",lw=.4,zorder=5)
    ax.annotate("One root",(a["lambda_p"],a["lambda_s"]),xytext=(.12,.10),fontsize=8,color=GREEN,
                arrowprops=dict(arrowstyle="-",color=GREEN,lw=.7))
    ax.set(xlim=(-.73,.73),ylim=(-.73,.73),xlabel=r"Starting $\lambda_p$",ylabel=r"Starting $\lambda_s$")
    ax.set_xticks([-.65,0,.65]);ax.set_yticks([-.65,0,.65])
    ax.set_title("(b) Mid-shift starting guesses",loc="left",pad=23)
    ax.legend(loc="lower left",bbox_to_anchor=(-.07,1.0),ncol=2,frameon=False,
              handletextpad=.25,columnspacing=.65,borderaxespad=0)
    save(fig,out,"closure_robustness")


def fold(values, curve, artifacts, out):
    fig=plt.figure(figsize=(6.5,3.2))
    gs=fig.add_gridspec(1,2,left=.095,right=.98,bottom=.19,top=.79,wspace=.43)
    ax=fig.add_subplot(gs[0,0])
    with np.load(artifacts / "selected_audit/focused_residual_map.npz",allow_pickle=False) as d:
        ax.contour(d["lambda_p"],d["lambda_s"],d["R_p"],levels=[0],colors=[BLUE],linewidths=1.4)
        ax.contour(d["lambda_p"],d["lambda_s"],d["R_s"],levels=[0],colors=[ORANGE],linewidths=1.4,linestyles="--")
    roots=values["selected_roots"]
    for r,color in zip(roots,(GREEN,PURPLE)):
        ax.scatter(r["lambda_p"],r["lambda_s"],s=35,color=color,zorder=5,edgecolors="white",lw=.5)
        ax.annotate(f"Root {int(r['root_id'])}",(r["lambda_p"],r["lambda_s"]),xytext=(6,7),
                    textcoords="offset points",color=color,fontsize=8)
    ax.set(xlim=(-.310,-.258),ylim=(.30,.59),xlabel=r"Primary traction $\lambda_p$",ylabel=r"Secondary traction $\lambda_s$")
    ax.set_xticks([-.30,-.28,-.26])
    ax.set_title("(a) Both sticking conditions",loc="left",pad=24)
    ax.legend(handles=[Line2D([],[],color=BLUE,label=r"$a_{\rm rel,p}=0$"),
                       Line2D([],[],color=ORANGE,ls="--",label=r"$a_{\rm rel,s}=0$")],
        loc="lower left",bbox_to_anchor=(-.025,1.0),ncol=2,frameon=False,handlelength=1.6,columnspacing=.7)
    ax=fig.add_subplot(gs[0,1])
    x=np.array([r["lambda_s"] for r in curve]); y=np.array([r["secondary_boundary_torque_Nm"] for r in curve])
    physical=np.array([r["physical"] for r in curve],dtype=bool)
    # Keep the mathematical continuation visible but distinct after lift-off.
    ax.plot(x,y,color=GREY,ls=":",lw=1.2)
    ax.plot(x,np.where(physical,y,np.nan),color=BLUE,lw=1.5)
    ts=values["frozen"]["selected_secondary_torque_Nm"]
    ax.axhline(ts,color=ORANGE,ls="--",lw=1.)
    for r,color in zip(roots,(GREEN,PURPLE)):
        ax.scatter(r["lambda_s"],ts,s=35,color=color,zorder=5,edgecolors="white",lw=.5)
        ax.annotate(f"{int(r['root_id'])}",(r["lambda_s"],ts),xytext=(0,-12),textcoords="offset points",ha="center",color=color)
    f=values["frozen"]["fold"]
    ax.scatter(f["lambda_s"],f["secondary_boundary_torque_Nm"],s=32,marker="^",color="#333333",zorder=5)
    ax.annotate("Fold",(f["lambda_s"],f["secondary_boundary_torque_Nm"]),xytext=(7,0),textcoords="offset points",fontsize=8)
    ax.text(.475,ts+.5,f"{ts:.2f} N m",fontsize=8,color=ORANGE)
    ax.set(xlim=(.30,.59),ylim=(179,199.8),xlabel=r"Secondary traction $\lambda_s$",ylabel=r"Required $\tau_{\mathrm{B},s}$ [N m]")
    ax.set_xticks([.3,.4,.5,.58]);ax.set_yticks([180,185,190,195])
    ax.set_title("(b) One branch, two intersections",loc="left",pad=24)
    ax.legend(handles=[Line2D([],[],color=BLUE,label="Admissible"),Line2D([],[],color=GREY,ls=":",label="Fails contact")],
        loc="lower left",bbox_to_anchor=(-.025,1.0),ncol=2,frameon=False,handlelength=1.5,columnspacing=.7)
    fig.text(.5,.965,rf"Frozen state: $\tau_{{\mathrm{{B}},p}}={values['frozen']['fixed_primary_torque_Nm']:.2f}$ N m; "
             rf"panel (a): $\tau_{{\mathrm{{B}},s}}={ts:.2f}$ N m",ha="center",fontsize=9)
    save(fig,out,"sticking_closure_fold")


def build(artifacts, out):
    artifacts,out=Path(artifacts),Path(out)
    values, starts, actual, curve=audit(artifacts)
    out.mkdir(parents=True,exist_ok=True)
    with plt.rc_context(STYLE):
        robustness(values, starts, actual, out)
        fold(values, curve, artifacts, out)
    write_json(out / "closure_values.json",values)
    write_json(out / "closure_figure_provenance.json",{
        "run_id":values["run_id"],
        "source_script":"results/cinder-v1.1.2/studies/closure-conditioning/analysis/publication_plots.py",
        "plot_script_sha256":digest(Path(__file__)),
        "command":"python studies/closure-conditioning/run.py --plot-only --artifacts-dir <reviewed-evidence> --figure-dir <output>",
        "figures":{
            "closure_robustness.pdf":{"label":"fig:verification_closure_robustness", "panels":[
                "Unmasked 241-square static-map maxima contrasted with root-only values; same equilibrated eight-variable matrix.",
                "All 49 mid-shift starts and actual acceptance outcomes. No iteration paths or inferred basin boundary."]},
            "sticking_closure_fold.pdf":{"label":"fig:verification_closure_fold", "panels":[
                "Focused dimensional acceleration-zero contours at the exact selected pair of shaft-boundary torques.",
                "Locally corrected open fixed-primary-torque branch, parameterized by secondary traction, with the same two roots/load slice. Failed contact portions dotted."]}},
        "scope":"Frozen algebraic mechanics; no hybrid time traces, event alignment or physical-state continuation in these plots.",
        "retained_sources":str((Path("results/cinder-v1.1.2/studies/closure-conditioning/provenance/retained_archives.json"))),
        "output_sha256":{p.name:digest(p) for p in sorted(out.iterdir()) if p.name in
            ("closure_robustness.pdf","closure_robustness.png","sticking_closure_fold.pdf","sticking_closure_fold.png","closure_values.json")}})
    print(f"Publication figures checked and written: {out}")
