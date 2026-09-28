"""Publication belt figures from checked, segment-preserving frozen outputs."""
import hashlib
import json
from pathlib import Path
import tempfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

BLUE='#126a98'; ORANGE='#c65d17'; PURPLE='#79558c'; GRAY='#66717a'; GREEN='#327459'
# One order, symbol and colour for each part of the five-term balance.
PARTS=[('normal_contact',GRAY,r'Contact loading  $F_N$','-'),
       ('tangential_belt_acceleration',BLUE,r'Changing belt speed  $F_{\dot v_b}$','--'),
       ('radial_shift_acceleration',ORANGE,r'Changing shift speed  $F_{\ddot s}$','-.'),
       ('radial_geometry_curvature',PURPLE,'Changing radius–shift\nrelationship  '+r'$F_{\dot s^2}$',':'),
       ('tangential_shifting_radius',GREEN,'Circulation during shifting  '+r'$F_{\dot s v_b}$',(0,(5,2,1,2)))]
plt.rcParams.update({'font.family':'serif','font.serif':['STIXGeneral'],'mathtext.fontset':'stix',
 'font.size':9.2,'axes.labelsize':9.2,'axes.titlesize':10,'xtick.labelsize':8.5,
 'ytick.labelsize':8.5,'legend.fontsize':8.5,'axes.spines.top':False,'axes.spines.right':False,
 'axes.linewidth':.65,'lines.linewidth':1.45,'pdf.fonttype':42,'svg.hashsalt':'cinder-belt-1.1.2',
 'savefig.dpi':300,'figure.facecolor':'white'})

def save(fig,path):
    with tempfile.TemporaryDirectory(prefix='belt-export-',dir=path.parent) as tmp:
        for suffix in ('pdf','png','svg'):
            f=Path(tmp)/('figure.'+suffix)
            metadata={'Creator':'CINDER frozen belt study'}
            if suffix=='pdf':metadata.update(CreationDate=None,ModDate=None)
            if suffix=='svg':metadata={'Date':None}
            fig.savefig(f,metadata=metadata,bbox_inches='tight',pad_inches=.04)
            if suffix=='pdf':assert f.read_bytes().rstrip().endswith(b'%%EOF')
            f.replace(path.with_suffix('.'+suffix))
    plt.close(fig)

def columns(z,name,kind='terms'):
    prefix=name+'__'+kind+'__'
    return {k[len(prefix):]:z[k] for k in z.files if k.startswith(prefix)}

def line(ax,d,key,color,label=None,*,scale=1.,offset=0.,window=None,ls='-',lw=1.45,xscale=1.):
    t=d['time_s'];s=d['segment_index'];m=np.ones(len(t),bool)
    if window is not None:m=(t>=window[0])&(t<=window[1])
    first=True
    for seg in np.unique(s[m]):
        q=m&(s==seg)
        ax.plot(xscale*(t[q]-offset),scale*d[key][q],linestyle=ls,color=color,lw=lw,label=label if first else None)
        first=False

def style(axes):
    for ax in axes:
        ax.axhline(0,color=GRAY,lw=.55,zorder=0)
        ax.grid(axis='y',alpha=.17);ax.set_axisbelow(True)

def plot_all(input_dir,output):
    a=json.loads((input_dir/'belt_publication_audit.json').read_text())
    source=input_dir/'belt_publication.npz'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==a['plot_inputs_sha256']
    z=np.load(source,allow_pickle=False);output.mkdir(parents=True,exist_ok=True)
    # Appendix: later-travel extension; not a competing main load narrative.
    fig,axes=plt.subplots(1,2,figsize=(6.35,3.4))
    fig.subplots_adjust(left=.09,right=.985,bottom=.18,top=.72,wspace=.35)
    d=columns(z,'envelope_tight_full')
    region=a['regions']['midshift_load_tight'];onset=region['start_s']
    rise=region['end_s']-onset;window=(onset-.02,onset+.12)
    line(axes[0],d,'shift_speed',GRAY,scale=1000,offset=onset,window=window,xscale=1000)
    for key,col,label,ls in PARTS:
        line(axes[1],d,'loop.'+key+'_N',col,label,offset=onset,window=window,xscale=1000,ls=ls)
    for ax in axes:
        ax.axvspan(0,1000*rise,color=GRAY,alpha=.10,lw=0,zorder=0)
        ax.set(xlim=(-20,120),xlabel='Time from load onset [ms]')
    axes[0].set(ylabel='Shift speed [mm/s]',ylim=(-3.5,4.5))
    axes[1].set(ylabel='Five-term balance contributions [N]',ylim=(-.12,.12))
    axes[0].set_title('(a) Upshift changes to backshift',loc='left',pad=10)
    axes[1].set_title('(b) Signed force contributions',loc='left',pad=10)
    handles,labels=axes[1].get_legend_handles_labels()
    labels=[label.replace('\n',' ') for label in labels]
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.53,1.01),ncol=2,
               frameon=False,fontsize=8.3,columnspacing=1.5,handlelength=2.9)
    style(axes);save(fig,output/'belt_shift_transient')

    # Main: input, motion, dimensional force, and the signed instantaneous balance.
    rate_cases=[('rise800',.8,'#999999',':','800 ms'),
                ('rise200',.2,'#626262','--','200 ms'),
                ('rise50',.05,'#222222','-','50 ms')]
    fig,axes=plt.subplots(2,2,figsize=(6.35,4.95))
    fig.subplots_adjust(left=.09,right=.985,bottom=.17,top=.94,wspace=.40,hspace=.54)
    ax_grade,ax_motion,ax_radial,ax_terms=axes.ravel()
    ts=np.linspace(-.05,1.05,2201)
    for case,rise,col,ls,label in rate_cases:
        u=np.clip(ts/rise,0,1)
        ax_grade.plot(ts,18*(3*u*u-2*u*u*u),color=col,ls=ls,label=label)
        d=columns(z,case+'_tight_full')
        line(ax_motion,d,'shift_speed',col,scale=1000,offset=1.5,window=(1.45,2.55),ls=ls)
        line(ax_radial,d,'loop.radial_shift_acceleration_N',col,scale=1000,
             offset=1.5,window=(1.45,2.55),ls=ls)
    for ax in (ax_grade,ax_motion,ax_radial):
        ax.set(xlim=(-.05,1.05),xlabel='Time from load onset [s]')
        ax.axvline(0,color=GRAY,lw=.6,ls=':')
    ax_grade.set(ylabel='Road grade [deg]',ylim=(-1,20),yticks=[0,6,12,18])
    ax_grade.legend(loc='lower right',frameon=False,fontsize=8.5,title='Rise time',title_fontsize=8.5)
    ax_motion.set(ylabel='Shift speed [mm/s]',ylim=(-1,9))
    ax_radial.set(ylabel=r'$F_{\ddot s}$ [mN]',ylim=(-3,38))
    d=columns(z,'rise50_tight_full')
    total_absolute=sum(abs(d['loop.'+key+'_N']) for key,_,_,_ in PARTS)
    displayed=(d['time_s']>=1.48)&(d['time_s']<=1.62)
    assert np.all(total_absolute[displayed]>0)
    for key,col,label,ls in PARTS:
        symbol='$'+label.split('$')[1]+'$'
        # A time-varying denominator requires new curves, not a secondary axis.
        field='signed_percent.'+key
        d[field]=np.divide(100*d['loop.'+key+'_N'],total_absolute,
                           out=np.full_like(total_absolute,np.nan),where=total_absolute>0)
        line(ax_terms,d,field,col,symbol,
             offset=1.5,window=(1.48,1.62),xscale=1000,ls=ls)
    ax_terms.axvspan(0,50,color=GRAY,alpha=.10,lw=0,zorder=0)
    ax_terms.set(xlim=(-20,120),xlabel='Time from load onset [ms]',
                 ylabel='Signed instantaneous\ncontribution [%]',ylim=(-55,55),
                 yticks=[-50,-25,0,25,50])
    ax_terms.legend(loc='upper center',ncol=3,frameon=False,fontsize=9,
                    bbox_to_anchor=(.5,-.34),columnspacing=1.1,handlelength=2.0)
    ax_grade.set_title('(a) Applied road grade',loc='left',pad=9,fontsize=9.2)
    ax_motion.set_title('(b) Shift response',loc='left',pad=9,fontsize=9.2)
    ax_radial.set_title('(c) Shift-acceleration contribution',loc='left',pad=9,fontsize=9.2)
    ax_terms.set_title('(d) Balance during the 50 ms rise',loc='left',pad=9,fontsize=9.2)
    style(axes.ravel());save(fig,output/'belt_load_rate')

    # A simultaneous coefficient/driver map uses every state, not separate maxima.
    events=json.loads((input_dir/'belt_events.json').read_text())['contact_combined_tight_full']
    seat=next(e['time_s'] for e in events if e['time_s']>1.8 and 'cvt:low_ratio_seat_reached' in e['events'])
    fig,axes=plt.subplots(1,2,figsize=(6.35,3.2))
    fig.subplots_adjust(left=.105,right=.985,bottom=.21,top=.85,wspace=.39)
    ax=axes[0]
    xx=np.linspace(-.96,.11,450);yy=np.linspace(-.115,.155,450);X,Y=np.meshgrid(xx,yy)
    cs=ax.contour(X,Y,1000*X*Y,levels=[-20,-10,10,20],colors='#8f989f',linewidths=.65)
    ax.clabel(cs,fmt=lambda v:f'{v:+g} mN',fontsize=7.5,inline=True,manual=[(-.78,.0128),(-.77,.026),(-.77,-.013),(-.43,-.0465)])
    for name,col,label in [('flat',GRAY,'Reference'),('contact',BLUE,'Primary 45%'),('contact_combined',ORANGE,'Primary 40%, secondary 20%')]:
        d=columns(z,name+'_tight_full')
        ax.scatter(d['loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2'],
            d['loop.driver.tangential_shifting_radius_m2ps2'],s=4,color=col,alpha=.65,lw=0,label=label,rasterized=True)
    ax.set(xlim=(-.96,.11),ylim=(-.115,.155),xlabel='Moving-radius coefficient [kg/m]',ylabel=r'Simultaneous $\dot s v_b$ [m$^2$/s$^2$]')
    ax.set_title('(a) Coefficient with its actual motion',loc='left',pad=10)
    ax.axvline(0,color=GRAY,lw=.55);ax.axhline(0,color=GRAY,lw=.55)
    ax.annotate('Early engagement',xy=(-.85,-.019),xytext=(-.90,-.075),fontsize=8,
        arrowprops={'arrowstyle':'-','lw':.6})
    ax.annotate('Held shift',xy=(-.51,0),xytext=(-.69,.08),fontsize=8,
        arrowprops={'arrowstyle':'-','lw':.6})
    ax=axes[1];d=columns(z,'contact_combined_tight_full')
    line(ax,d,'loop.tangential_shifting_radius_N',ORANGE,scale=1000,window=(1.6,2.08))
    ax.axvspan(1.8,1.9,color=ORANGE,alpha=.10,lw=0)
    ax.axhline(0,color=GRAY,lw=.55)
    ax.set(xlim=(1.6,2.08),ylim=(-8.5,8.5),xlabel='Time from start [s]',ylabel=r'Moving-radius term $F_{\dot s v_b}$ [mN]')
    ax.set_title('(b) Load, backshift and seating',loc='left',pad=10)
    ax.annotate('Seat arrival\nand brief returns',xy=(seat,7.1),xytext=(1.67,5.5),fontsize=8,
        arrowprops={'arrowstyle':'-','lw':.6})
    ax.grid(axis='y',alpha=.17);ax.set_axisbelow(True)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.52,.0),ncol=3,frameon=False,
        fontsize=8,markerscale=2,handletextpad=.45,columnspacing=1.1)
    save(fig,output/'belt_coefficient_driver')

    # Appendix: density changes all belt inertia and has a separate event effect.
    fig,axes=plt.subplots(1,2,figsize=(6.35,2.90))
    fig.subplots_adjust(left=.105,right=.985,bottom=.19,top=.85,wspace=.35)
    engagement_position=next(e['pre_state'][3] for e in json.loads((input_dir/'belt_events.json').read_text())['flat_tight_full']
                             if 'cvt:engagement_reached' in e['events'])
    for variant,col,ls,label in [('full',GRAY,'-','Reference density'),('density03',GREEN,'--','3% density')]:
        d=columns(z,'flat_tight_'+variant,'early_states')
        d['from_engagement']=d['shift']-engagement_position
        line(axes[0],d,'from_engagement',col,label,scale=1000,window=(.0619,.0661),xscale=1000,ls=ls)
    axes[0].set(xlim=(61.9,66.1),xticks=[62,63,64,65,66],xlabel='Time from start [ms]',
                ylabel='Shift from engagement position [mm]')
    axes[0].legend(loc='upper right',frameon=False,fontsize=8)
    for case,col,ls,label in [('flat',GRAY,'-','Level ground'),('loading',ORANGE,'--','Rapid loading'),('unloading',BLUE,':','Rapid unloading')]:
        name=case+'_tight_density03';pre=name+'__comparison__'
        t=z[pre+'time_s'];dd=z[pre+'difference'];left=z[pre+'left_difference'];segs=np.c_[z[pre+'full_segment'],z[pre+'variant_segment']]
        splits=np.r_[0,np.flatnonzero(np.any(np.diff(segs,axis=0)!=0,axis=1))+1,len(t)]
        first=True
        for i,j in zip(splits[:-1],splits[1:]):
            tx=t[i:j];yy=dd[i:j]
            if j<len(t):
                tx=np.r_[tx,t[j]];yy=np.vstack([yy,left[j]])
            mask=tx>=.1
            if mask.any():
                axes[1].plot(tx[mask],-1000*yy[mask,3],ls,color=col,label=label if first else None)
                first=False
    axes[1].set(xlim=(.1,5),xlabel='Time from start [s]',ylabel='Shift difference, 3% minus reference [mm]')
    axes[1].legend(loc='upper right',frameon=False,fontsize=8)
    axes[0].set_title('(a) First engagement',loc='left',pad=10)
    axes[1].set_title('(b) Later response to road loading',loc='left',pad=10)
    style(axes);save(fig,output/'belt_density_response')
    names=['belt_load_rate','belt_shift_transient','belt_coefficient_driver','belt_density_response']
    (input_dir/'figure_hashes.json').write_text(json.dumps({n+'.'+ext:hashlib.sha256((output/(n+'.'+ext)).read_bytes()).hexdigest()
        for n in names for ext in ('pdf','png','svg')},indent=2)+'\n')
