"""Coast v2 mouth geometry derived exclusively from prepared drainage edges.

No river network is solved here. Every fan references an existing land-to-sea
edge; bounded geometry remains within its prepared halo. Runtime caches are
rebuildable and never contain player/history mutations.
"""
from collections import OrderedDict
from dataclasses import dataclass
from math import isqrt
from worldseed.core.coords import WorldPos
from worldseed.world.landforms import SEA_LEVEL_REFERENCE as SEA


@dataclass(frozen=True, slots=True)
class MouthPlan:
    source: tuple[int,int]
    target: tuple[int,int]
    watershed: int
    river_class: int
    discharge: int
    primary: tuple
    branches: tuple
    branch_discharge: tuple
    barrier: tuple
    lagoon: tuple
    width: int
    mixing_width: int
    sediment: int
    shelter: int
    bounds: tuple[int,int,int,int]


def along_segment(x,y,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=max(1,dx*dx+dy*dy)
    t=max(0,min(length,(x-a[0])*dx+(y-a[1])*dy))
    # Integer squared distance in fixed-point coordinates.
    ox=(x-a[0])*length-dx*t;oy=(y-a[1])*length-dy*t
    return ox*ox+oy*oy,length,t


def contains(path,x,y,width,end_width=None):
    for i,(a,b) in enumerate(zip(path,path[1:])):
        dist,length,t=along_segment(x,y,a,b)
        radius=width if end_width is None else width+(end_width-width)*(i*length+t)//max(1,(len(path)-1)*length)
        if dist<=radius*radius*length*length:return True
    return False


class CoastalMouths:
    def __init__(self,generator):
        self.generator=generator
        self._indexes=OrderedDict()

    def _elevation(self,p):
        return self.generator.landforms_v8.sample(*p).elevation

    def _safe_branch(self,path):
        if self._elevation(path[-1])>=SEA:return False
        for a,b in zip(path,path[1:]):
            count=max(abs(b[0]-a[0]),abs(b[1]-a[1]),1)
            for i in range(count+1):
                p=(a[0]+(b[0]-a[0])*i//count,a[1]+(b[1]-a[1])*i//count)
                if self._elevation(p)>SEA+450:return False
        return True

    def _plan(self,domain,idx):
        hydro=self.generator.hydrology;target=domain.flow_to[idx]
        cls=domain.river_class[idx]
        if cls<=0 or target<0:return None
        a,b=domain.world_xy(idx),domain.world_xy(target)
        if not (domain.elevation[idx]>=SEA>domain.elevation[target]):return None
        # Exact geology must agree with the prepared mouth's land/sea crossing.
        if not (self._elevation(a)>=SEA>self._elevation(b)):return None
        gx,gy=domain.global_node_xy(idx);tx,ty=domain.global_node_xy(target)
        acc=domain.accumulation[idx];fp=domain.floodplain_strength[idx]
        gradient=domain.channel_gradient[idx] if domain.channel_gradient else max(0,domain.elevation[idx]-domain.elevation[target])
        primary,_,width,_=hydro._channel_paths(gx,gy,tx,ty,gradient,cls,acc,fp,hydro._upstream_river_count(domain,idx))
        coast=self.generator.coast_v8.sample(WorldPos(*b,0),prepared_only=True)
        shelter=coast.shelter;sediment=coast.sediment_potential
        mixing=width+min(8,cls+shelter//20)
        branches=[]
        dx,dy=b[0]-a[0],b[1]-a[1];norm=max(1,isqrt(dx*dx+dy*dy))
        split=primary[-2]
        if cls>=2 and acc>=650 and gradient<=180 and shelter>=35:
            for side in (-1,1):
                for spread in (16,12,8):
                    end=(b[0]+dx*16//norm-side*dy*spread//norm,
                         b[1]+dy*16//norm+side*dx*spread//norm)
                    mid=((split[0]+end[0])//2-side*dy*3//norm,
                         (split[1]+end[1])//2+side*dx*3//norm)
                    path=(split,mid,end)
                    if self._safe_branch(path):branches.append(path);break
        barrier=();lagoon=()
        # Longshore transport can deposit a narrow spit/barrier beside a
        # sediment-rich mouth. Geometry follows the shoreline tangent and
        # physical prevailing wind, never an independent coast noise sheet.
        exposure=100-shelter
        if cls>=2 and acc>=400 and gradient<=300 and 22<=exposure<=65 and sediment>=60:
            climate=self.generator.climate_at(WorldPos(*b,0))
            wind_x=int(getattr(climate,'prevailing_wind_dx',0))
            wind_y=int(getattr(climate,'prevailing_wind_dy',0))
            drift=(-dy)*wind_x+dx*wind_y
            if drift:
                side=1 if drift>0 else -1
                # Start outside the main estuary aperture, then follow the
                # coastal tangent. Deposits are clipped to shallow substrate.
                points=[];inner=[]
                for distance in (mixing+5,mixing+21,mixing+37):
                    points.append((b[0]+dx*8//norm-side*dy*distance//norm,
                                   b[1]+dy*8//norm+side*dx*distance//norm))
                    inner.append((b[0]-side*dy*distance//norm,
                                  b[1]+side*dx*distance//norm))
                if all(SEA-600<=self._elevation(p)<SEA for p in points):
                    barrier=tuple(points);lagoon=tuple(inner)
        count=len(branches)+1
        discharges=tuple(acc//count+(1 if i<acc%count else 0) for i in range(count))
        points=list(primary)+[p for path in branches for p in path]+list(barrier)+list(lagoon)
        pad=mixing+4
        bounds=(min(p[0] for p in points)-pad,min(p[1] for p in points)-pad,
                max(p[0] for p in points)+pad,max(p[1] for p in points)+pad)
        return MouthPlan(a,b,domain.watershed_id[idx],cls,acc,primary,tuple(branches),
                         discharges,barrier,lagoon,width,mixing,sediment,shelter,bounds)

    def plans(self,domain):
        key=(domain.domain_x,domain.domain_y,domain.fingerprint)
        cached=self._indexes.get(key)
        if cached is not None:self._indexes.move_to_end(key);return cached
        plans=[];buckets={}
        # Halo edges are included: either side of a prepared-domain seam sees
        # the same crossing and integer path, regardless of generation order.
        for idx,cls in enumerate(domain.river_class):
            if not cls:continue
            plan=self._plan(domain,idx)
            if plan is None:continue
            plans.append(plan)
            x0,y0,x1,y1=plan.bounds
            for y in range(y0//32,y1//32+1):
                for x in range(x0//32,x1//32+1):buckets.setdefault((x,y),[]).append(plan)
        result=(tuple(plans),{k:tuple(v) for k,v in buckets.items()})
        if len(self._indexes)>=12:self._indexes.popitem(last=False)
        self._indexes[key]=result
        return result

    def at(self,pos,domain,*,prepared_only=False):
        if domain is None or pos.z!=0:return None
        if prepared_only:
            cached=self._indexes.get((domain.domain_x,domain.domain_y,domain.fingerprint))
            if cached is None:return None
            _,buckets=cached
        else:
            _,buckets=self.plans(domain)
        candidates=buckets.get((pos.x//32,pos.y//32),())
        if not candidates:return None
        elevation=self._elevation((pos.x,pos.y))
        if elevation>SEA+1200:return None
        deposit=None
        for plan in sorted(candidates,key=lambda p:(-p.discharge,p.source)):
            paths=(plan.primary,)+plan.branches
            for i,path in enumerate(paths):
                radius=plan.width if i==0 else max(2,plan.width-2)
                outer=plan.mixing_width if i==0 else radius
                if contains(path,pos.x,pos.y,radius,outer):
                    deep=contains(path,pos.x,pos.y,max(1,radius-2)) and plan.river_class>=2
                    return ('core:estuary_deep' if deep else 'core:estuary_shallow',plan,i)
            # Shallow depositional lobes adjoin real distributaries. Never fill
            # deep water or invent an isolated land mass beyond the fan.
            if plan.branches and SEA-350<=elevation<=SEA+100 and plan.sediment>=55:
                if any(contains(path,pos.x,pos.y,plan.width+3) for path in plan.branches):
                    deposit=('core:tidal_flat',plan,-2)
            if plan.barrier and SEA-600<=elevation<SEA:
                if contains(plan.barrier,pos.x,pos.y,2):deposit=('core:shore',plan,-2)
                elif contains(plan.lagoon,pos.x,pos.y,3):deposit=('core:estuary_shallow',plan,-1)
        return deposit
