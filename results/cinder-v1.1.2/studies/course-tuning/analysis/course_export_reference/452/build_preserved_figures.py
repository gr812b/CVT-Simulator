"""Rebuild the two preserved diagnostic figures from retained Final V3 diagnostics.

Requires pandas, numpy, matplotlib. No simulation or smoothing is performed.
Data filtering is confined to the windows/contact conditions in the captions.
Both vector PDF and 300 dpi PNG files are written to figures/results/course.
"""
from pathlib import Path
from io import BytesIO
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import course_csvframe as pd

ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'figure_source'
OUT=ROOT/'figures/results/course'
OUT.mkdir(parents=True,exist_ok=True)
E=json.loads((DATA/'evidence.json').read_text())
COL={'R00':'#29485F','D01':'#BF7025','D02':'#BD3F46','D02_M':'#7160B4','D02_P':'#238371'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,
 'axes.labelsize':9,'axes.titlesize':9,'legend.fontsize':8,
 'xtick.labelsize':8,'ytick.labelsize':8,'axes.spines.top':False,
 'axes.spines.right':False,'axes.linewidth':.7,'lines.linewidth':1.55,
 'axes.axisbelow':True,'axes.grid':True,'grid.color':'#d6d8dc',
 'grid.alpha':.65,'grid.linewidth':.5,'legend.frameon':False,
 'savefig.facecolor':'white','pdf.fonttype':42})
SEAT=2.4892
CAP=E['D02']['primary_capacity_event']['time_s']
ZERO=E['D02']['zero_vehicle_speed_interpolated']['time_s']
SEAT_TIME=E['D02']['hill_first_seat_event']['time_s']

def frame(case):
 return pd.read_csv(DATA/f'{case}_hill.csv')

def save(fig,name):
 for ext in ['pdf','png']:
  buf=BytesIO();fig.savefig(buf,format=ext,dpi=300)
  f=OUT/f'{name}.{ext}';t=f.with_suffix('.tmp');t.write_bytes(buf.getvalue());t.replace(f)
 plt.close(fig)

def label(ax,text):
 ax.set_title(text,loc='left',pad=5)

# A: chronological forward portions only; D02 rollback is kept in Figure B.
fig,axs=plt.subplots(3,1,figsize=(6.5,4.5),sharex=True)
fig.subplots_adjust(left=.13,right=.985,bottom=.10,top=.915,hspace=.35)
for case in ['R00','D01','D02']:
 d=frame(case)
 if case=='D02':
  d=d[d.time_s.le(ZERO)].copy()
  r=d.iloc[-1].copy()
  r['time_s']=ZERO;r['distance_m']=E[case]['zero_vehicle_speed_interpolated']['distance_m'];r['speed_m_s']=0
  d=pd.concat([d,r.to_frame().T],ignore_index=True)
 for ax,v in zip(axs,['shift_mm','primary_rpm','speed_m_s']):
  ax.plot(d.distance_m.astype(float),d[v].astype(float),color=COL[case],label=case)
for ax in axs:
 ax.axvspan(120,132,color='#edf0f2',zorder=0)
 ax.axvspan(212,224,color='#edf0f2',zorder=0)
 ax.set_xlim(120,224);ax.set_xticks([120,132,150,170,190,212,224])
axs[0].set_ylim(1.3,20.8);axs[0].set_yticks([2.4892,10,19.05],labels=['2.49','10','19.05'])
axs[0].axhline(SEAT,color='#737b80',ls=(0,(3,3)),lw=.8,label='Low-ratio seat')
axs[0].set_ylabel('Shift [mm]');label(axs[0],'(a) Backshift travel')
axs[0].annotate('D01: 0.79 mm above seat',xy=(195,3.2831),xytext=(169,7.2),
 fontsize=8,color=COL['D01'],arrowprops={'arrowstyle':'-','lw':.7,'color':COL['D01']})
axs[0].text(172,16,r'$38^\circ$ hold',ha='center',fontsize=8,color='#60666a')
axs[1].set_ylim(2200,4040);axs[1].set_yticks([2400,3000,3600]);axs[1].set_ylabel('Primary [rpm]')
label(axs[1],'(b) Primary speed')
axs[2].set_ylim(-.5,18.5);axs[2].set_yticks([0,5,10,15]);axs[2].set_ylabel('Vehicle [m/s]')
label(axs[2],'(c) Vehicle speed')
axs[2].plot(E['D02']['zero_vehicle_speed_interpolated']['distance_m'],0,'o',color=COL['D02'],ms=3.8)
axs[2].annotate('D02: zero speed at 192.50 m',xy=(192.4963,0),xytext=(156,8.5),
 fontsize=8,color=COL['D02'],arrowprops={'arrowstyle':'-','lw':.7,'color':COL['D02']})
axs[2].set_xlabel('Road position [m]')
h,l=axs[0].get_legend_handles_labels()
fig.legend(h,l,loc='upper center',bbox_to_anchor=(.55,.999),ncol=4,columnspacing=1.4,handlelength=2.2)
save(fig,'severe_hill_response')

# B: common time axis preserves the order through zero velocity and rollback.
d=frame('D02');d=d[d.time_s.ge(SEAT_TIME)]
fig,axs=plt.subplots(1,2,figsize=(6.5,2.65),sharex=True)
fig.subplots_adjust(left=.10,right=.985,bottom=.19,top=.85,wspace=.34)
for ax in axs:
 ax.axvspan(ZERO,50,color='#f3ecec',zorder=0)
 ax.axvline(CAP,color='#8b3037',ls=(0,(4,3)),lw=.8)
 ax.axvline(ZERO,color='#6a6464',ls=(0,(2,3)),lw=.8)
 ax.set_xlim(SEAT_TIME,50);ax.set_xticks([15,25,35,45])
 ax.set_xlabel('Time since launch [s]')
static=d.primary_static_utilization.where(d.contact_mode.eq('stick_stick') & d.time_s.le(CAP))
axs[0].plot(d.time_s,static,color=COL['D02'],label='Primary, while sticking')
secondary=d.secondary_static_utilization.where(d.contact_mode.str.contains('stick_stick|secondary_stick',regex=True))
axs[0].plot(d.time_s,secondary,color='#287d77',label='Secondary')
axs[0].axhline(1,color='#737b80',lw=.8,ls=(0,(3,3)))
axs[0].plot(CAP,1,'o',color=COL['D02'],ms=3.8)
axs[0].set_ylim(0,1.18);axs[0].set_yticks([0,.5,1]);axs[0].set_ylabel(r'Static use $|\lambda_j|/\mu_s$')
label(axs[0],'(a) Traction while sticking')
axs[0].annotate('17.83 s',xy=(CAP,1),xytext=(22,1.065),fontsize=7.5,color=COL['D02'],arrowprops={'arrowstyle':'-','lw':.6,'color':COL['D02']})
axs[0].legend(loc='lower right',fontsize=7.0)
axs[1].plot(d.time_s,d.primary_boundary_power_W/1000,color=COL['R00'],label='Primary input')
axs[1].plot(d.time_s,d.primary_slip_loss_W/1000,color=COL['D02'],label='Primary slip loss')
axs[1].plot(d.time_s,-d.secondary_boundary_power_W/1000,color='#287d77',label='Output power')
axs[1].axhline(0,color='#737b80',lw=.7)
axs[1].plot(ZERO,7.073466,'o',color=COL['D02'],ms=3.8)
axs[1].set_ylim(-.9,9.8);axs[1].set_yticks([0,4,8]);axs[1].set_ylabel('Power [kW]')
label(axs[1],'(b) Power and slip dissipation')
axs[1].text(41,8.6,'Rollback',ha='center',fontsize=8,color='#796666')
axs[1].annotate('34.22 s',xy=(ZERO,0),xytext=(24,1.25),fontsize=7.5,color='#656565',arrowprops={'arrowstyle':'-','lw':.6,'color':'#656565'})
axs[1].legend(loc='center right',fontsize=7.0)
save(fig,'d02_traction_power')

print('Built the preserved A/B figures from selected diagnostic rows.')
