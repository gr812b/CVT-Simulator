"""A shared, C2 distance-indexed grade profile. Distance is road arc length."""
from __future__ import annotations
from dataclasses import dataclass
from math import cos, sin, pi, radians, isfinite
from typing import Any


def smooth(u: float) -> float:
    u=min(1.,max(0.,float(u)))
    return u*u*u*(10.+u*(-15.+6.*u))


def smooth_derivative(u: float) -> float:
    if u<=0. or u>=1.: return 0.
    return 30.*u*u*(1.-u)*(1.-u)


@dataclass(frozen=True)
class Sector:
    name: str
    start_m: float
    end_m: float
    kind: str
    start_deg: float=0.
    end_deg: float=0.


class Course:
    def __init__(self, config: dict[str, Any]):
        self.config=config
        for name in ('hill_angle_deg','cyclic_amplitude_deg','downhill_angle_deg'):
            v=float(config[name])
            if not isfinite(v) or abs(v)>=89.: raise ValueError(f'{name} must be finite and below 89 degrees in magnitude')
        if float(config['hill_angle_deg'])<0: raise ValueError('hill_angle_deg must be nonnegative')
        self.wavelength=float(config['cyclic_wavelength_m'])
        self.count=int(config['cyclic_count'])
        self.envelope_periods=float(config['cyclic_envelope_periods'])
        if self.wavelength<=0 or self.count<2 or not 0<self.envelope_periods<=self.count/2:
            raise ValueError('Invalid cyclic wavelength/count/envelope')
        sectors=[]; x=0.
        def add(name,length,kind='flat',a=0.,b=0.):
            nonlocal x
            length=float(length)
            if not isfinite(length) or length<=0: raise ValueError(f'{name}: length must be positive')
            sectors.append(Sector(name,x,x+length,kind,a,b));x+=length
        L=config['lengths_m']; h=float(config['hill_angle_deg']); down=float(config['downhill_angle_deg'])
        add('launch_flat',L['launch_flat'])
        add('hill_entry',L['hill_entry'],'ramp',0.,h)
        add('hill_hold',L['hill_hold'],'constant',h,h)
        add('hill_exit',L['hill_exit'],'ramp',h,0.)
        add('recovery_flat',L['recovery_flat'])
        add('cyclic',self.wavelength*self.count,'cyclic')
        add('post_cyclic_flat',L['post_cyclic_flat'])
        add('descent_entry',L['descent_entry'],'ramp',0.,down)
        add('descent_hold',L['descent_hold'],'constant',down,down)
        add('descent_exit',L['descent_exit'],'ramp',down,0.)
        add('finish_flat',L['finish_flat'])
        self.sectors=tuple(sectors); self.finish_m=x

    def sector(self,x:float) -> Sector:
        for s in self.sectors:
            if x<s.end_m: return s
        return self.sectors[-1]

    def grade_and_gradient(self,x:float) -> tuple[float,float]:
        """Return gamma [rad] and dgamma/distance [rad/m], analytically."""
        if not isfinite(x): raise ValueError('Distance must be finite')
        if x<0. or x>=self.finish_m: return 0.,0.
        s=self.sector(x); q=x-s.start_m; length=s.end_m-s.start_m
        if s.kind=='flat': return 0.,0.
        if s.kind=='constant': return radians(s.start_deg),0.
        if s.kind=='ramp':
            u=q/length; span=radians(s.end_deg-s.start_deg)
            return radians(s.start_deg)+span*smooth(u),span*smooth_derivative(u)/length
        # A sinusoidal grade with a smooth envelope at both ends.
        env_len=self.envelope_periods*self.wavelength
        a=q/env_len; b=(length-q)/env_len
        left=smooth(a); right=smooth(b)
        env=left*right
        env_d=(smooth_derivative(a)*right-left*smooth_derivative(b))/env_len
        k=2*pi/self.wavelength; amp=radians(float(self.config['cyclic_amplitude_deg']))
        return amp*env*sin(k*q),amp*(env_d*sin(k*q)+env*k*cos(k*q))

    def sample(self,*,vehicle_distance:float):
        from cinder.model.boundaries.vehicle.road_profile import RoadProfileSample
        g,_=self.grade_and_gradient(float(vehicle_distance))
        return RoadProfileSample(vehicle_distance=float(vehicle_distance),grade_angle=g)

    def table(self) -> list[dict]:
        return [vars(s) for s in self.sectors]

    def profile_rows(self,step_m:float=.1) -> list[dict]:
        import numpy as np
        x=np.linspace(0.,self.finish_m,max(2,int(self.finish_m/step_m)+1))
        g=np.asarray([self.grade_and_gradient(float(v))[0] for v in x])
        height=np.r_[0.,np.cumsum(.5*(np.sin(g[:-1])+np.sin(g[1:]))*np.diff(x))]
        horizontal=np.r_[0.,np.cumsum(.5*(np.cos(g[:-1])+np.cos(g[1:]))*np.diff(x))]
        return [{'distance_m':float(v),'horizontal_distance_m':float(xx),'elevation_m':float(h),'grade_deg':float(gg*180/pi),'sector':self.sector(float(v)).name} for v,xx,h,gg in zip(x,horizontal,height,g)]
