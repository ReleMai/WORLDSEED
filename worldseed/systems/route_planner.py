"""Sparse terrain-aware regional route planning for realized civilization."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import heapq

from worldseed.config import ROUTEGEN_VERSION
from worldseed.core.canonical import canonical_hash
from worldseed.systems.state import TradeRouteState
from worldseed.world.regional_plan import stable_plan_uid


@dataclass(slots=True)
class RegionalRoutePlan:
    uid: str
    version: int
    origin: str
    destination: str
    region_path: list[tuple[int, int]] = field(default_factory=list)
    chunk_corridor: list[tuple[int, int]] = field(default_factory=list)
    crossings: list[dict] = field(default_factory=list)
    route_class: str = "trail"
    cost: int = 0
    danger: int = 0
    fingerprint: str = ""

    def to_dict(self) -> dict:
        raw = asdict(self)
        raw["fingerprint"] = self.fingerprint or canonical_hash({k:v for k,v in raw.items() if k!="fingerprint"})
        return raw

    @classmethod
    def from_dict(cls, raw: dict) -> "RegionalRoutePlan":
        row = dict(raw)
        row["region_path"] = [tuple(map(int, p)) for p in row.get("region_path", ())]
        row["chunk_corridor"] = [tuple(map(int, p)) for p in row.get("chunk_corridor", ())]
        return cls(**row)


class RoutePlanner:
    """Sparse graph first, terrain corridor second."""

    def __init__(self, world, state, region_planner, version: int | None = None):
        self.world = world
        self.state = state
        self.region_planner = region_planner
        if version is None:
            version = getattr(world, "routegen_version", ROUTEGEN_VERSION)
        self.version = int(version)
        self.cache_source = world.delta_source
        self._cache: dict[str, RegionalRoutePlan] = {}

    @staticmethod
    def _edge_uid(a: str, b: str) -> str:
        lo, hi = sorted((str(a), str(b)))
        return stable_plan_uid("regional-route", lo, hi)

    def _region_cost(self, rx: int, ry: int) -> int:
        plan = self.region_planner.plan(rx, ry, persist=True)
        cost = 100 + min(90, int(plan.relief) // 700)
        cost += max(0, 55 - int(getattr(plan, "route_value", 0)))
        if plan.control_potential == "bandit_frontier": cost += 30
        if plan.dominant_biome in {"water", "highland"}: cost += 28
        if plan.waters: cost += max(int(w.river_class) for w in plan.waters) * 6
        return max(20, cost)

    def _region_path(self, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
        if start == goal: return [start]
        pad = 2
        left, right = min(start[0], goal[0]) - pad, max(start[0], goal[0]) + pad
        top, bottom = min(start[1], goal[1]) - pad, max(start[1], goal[1]) + pad
        heap = [(0, 0, start)]
        best = {start: 0}
        came = {}
        while heap:
            _, cost, cur = heapq.heappop(heap)
            if cost != best.get(cur): continue
            if cur == goal:
                out=[cur]
                while cur in came:
                    cur=came[cur];out.append(cur)
                return list(reversed(out))
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nxt=(cur[0]+dx,cur[1]+dy)
                if not (left<=nxt[0]<=right and top<=nxt[1]<=bottom): continue
                nc=cost+self._region_cost(*nxt)
                if nc>=best.get(nxt,1<<60): continue
                best[nxt]=nc;came[nxt]=cur
                h=(abs(goal[0]-nxt[0])+abs(goal[1]-nxt[1]))*70
                heapq.heappush(heap,(nc+h,nc,nxt))
        return [start,goal]

    @staticmethod
    def _bresenham_chunks(a: tuple[int,int], b: tuple[int,int]) -> list[tuple[int,int]]:
        x0,y0=a[0]//32,a[1]//32;x1,y1=b[0]//32,b[1]//32
        dx=abs(x1-x0);dy=-abs(y1-y0);sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1;err=dx+dy;out=[]
        while True:
            out.append((x0,y0))
            if (x0,y0)==(x1,y1): return out
            e2=2*err
            if e2>=dy:err+=dy;x0+=sx
            if e2<=dx:err+=dx;y0+=sy

    def _chunk_corridor(self,a,b,regions)->list[tuple[int,int]]:
        points=[(int(a.x),int(a.y))]+[(rx*512+256,ry*512+256) for rx,ry in regions[1:-1]]+[(int(b.x),int(b.y))]
        out=[]
        for p,q in zip(points,points[1:]):
            segment=self._bresenham_chunks(p,q)
            if out and segment and out[-1]==segment[0]:segment=segment[1:]
            out.extend(segment)
        return out

    @staticmethod
    def _direction(a,b):
        dx,dy=b[0]-a[0],b[1]-a[1]
        if dx==1:return "east"
        if dx==-1:return "west"
        if dy==1:return "south"
        return "north"

    def _crossings(self,regions)->list[dict]:
        out=[];opposite={"north":"south","south":"north","east":"west","west":"east"}
        for a,b in zip(regions,regions[1:]):
            direction=self._direction(a,b)
            plan=self.region_planner.plan(*a,persist=True)
            water=next((w for w in plan.waters if w.direction==direction),None)
            if water is None:
                mate=self.region_planner.plan(*b,persist=True)
                water=next((w for w in mate.waters if w.direction==opposite[direction]),None)
            if water is None or water.water_kind=="ocean":continue
            kind="ford" if int(water.river_class)<=1 else ("bridge_candidate" if int(water.river_class)<=3 else "ferry_candidate")
            out.append({"from_region":[a[0],a[1]],"to_region":[b[0],b[1]],"kind":kind,
                        "river_class":int(water.river_class),"offset":int(water.offset)})
        return out

    def read_prepared(self,uid:str)->RegionalRoutePlan|None:
        if uid in self._cache:return self._cache[uid]
        loader=getattr(self.cache_source,"load_generated_route_plan",None)
        if not callable(loader):return None
        raw=loader(uid,self.version)
        if not raw:return None
        try:
            fp=str(raw.get("fingerprint",""));check=dict(raw);check.pop("fingerprint",None)
            if fp!=canonical_hash(check):return None
            plan=RegionalRoutePlan.from_dict(raw)
            if plan.uid!=uid or plan.version!=self.version:return None
            self._cache[uid]=plan;return plan
        except (KeyError,TypeError,ValueError):return None

    def _build_plan(self,a,b)->RegionalRoutePlan:
        uid=self._edge_uid(a.uid,b.uid)
        cached=self.read_prepared(uid)
        if cached is not None:return cached
        regions=self._region_path((a.region_x,a.region_y),(b.region_x,b.region_y))
        cost=sum(self._region_cost(*r) for r in regions[1:])
        crossings=self._crossings(regions)
        danger=min(95,max(0,cost//max(1,len(regions))//4+len(crossings)*4))
        route_class="maintained_road" if max(a.population,b.population)>=150 else ("road" if a.population+b.population>=80 else "trail")
        payload={"uid":uid,"version":self.version,"origin":min(a.uid,b.uid),"destination":max(a.uid,b.uid),
                 "region_path":regions,"chunk_corridor":self._chunk_corridor(a,b,regions),"crossings":crossings,
                 "route_class":route_class,"cost":int(cost),"danger":int(danger)}
        plan=RegionalRoutePlan(**payload,fingerprint=canonical_hash(payload));self._cache[uid]=plan;return plan

    def _candidate_edges(self,settlements):
        rows=sorted(settlements,key=lambda s:s.uid);out={}
        for a in rows:
            nearby=sorted((b for b in rows if b.uid!=a.uid),
                          key=lambda b:(abs(a.region_x-b.region_x)+abs(a.region_y-b.region_y),b.uid))[:3]
            for b in nearby:
                lo,hi=sorted((a.uid,b.uid))
                if (lo,hi) in out:continue
                pa=self.region_planner.plan(a.region_x,a.region_y,persist=True)
                pb=self.region_planner.plan(b.region_x,b.region_y,persist=True)
                distance=abs(a.region_x-b.region_x)+abs(a.region_y-b.region_y)
                utility=int(getattr(pa,"route_value",0))+int(getattr(pb,"route_value",0))+min(60,a.population+b.population)//2
                out[(lo,hi)]=(distance*100-utility,lo,hi,a,b)
        return sorted(out.values(),key=lambda row:(row[0],row[1],row[2]))

    def _select_sparse_edges(self,settlements):
        rows=sorted(settlements,key=lambda s:s.uid)
        if len(rows)<2:return []
        parent={s.uid:s.uid for s in rows};degree={s.uid:0 for s in rows}
        def find(x):
            while parent[x]!=x:
                parent[x]=parent[parent[x]];x=parent[x]
            return x
        selected=[];candidates=self._candidate_edges(rows)
        for edge in candidates:
            _,_,_,a,b=edge;ra,rb=find(a.uid),find(b.uid)
            if ra==rb:continue
            parent[rb]=ra;selected.append(edge);degree[a.uid]+=1;degree[b.uid]+=1
        extras=max(1,len(rows)//3)
        for edge in candidates:
            if edge in selected:continue
            _,_,_,a,b=edge
            if degree[a.uid]>=4 or degree[b.uid]>=4:continue
            selected.append(edge);degree[a.uid]+=1;degree[b.uid]+=1;extras-=1
            if extras<=0:break
        return selected

    def _mirror_trade_route(self,plan,a,b)->None:
        minutes=max(180,int(plan.cost)*5)
        capacity=160 if plan.route_class=="maintained_road" else 100 if plan.route_class=="road" else 55
        for origin,destination,path,chunks,suffix in (
            (a,b,plan.region_path,plan.chunk_corridor,"a"),
            (b,a,list(reversed(plan.region_path)),list(reversed(plan.chunk_corridor)),"b"),
        ):
            uid=f"{plan.uid}:{suffix}";old=self.state.trade_routes.get(uid)
            self.state.trade_routes[uid]=TradeRouteState(
                uid,origin.uid,destination.uid,max(1,len(path)-1),int(plan.danger),capacity,
                int(old.last_used_minute) if old else 0,int(old.traffic) if old else 0,
                [f"{rx},{ry}" for rx,ry in path],minutes,[f"{cx},{cy}" for cx,cy in chunks],
            )

    def sync(self,settlements,center_region:tuple[int,int],radius:int=2,*,persist:bool=True)->tuple[RegionalRoutePlan,...]:
        rx,ry=map(int,center_region)
        selected=sorted((s for s in settlements if abs(int(s.region_x)-rx)<=radius and abs(int(s.region_y)-ry)<=radius),key=lambda s:s.uid)[:24]
        plans=[]
        for _,_,_,a,b in self._select_sparse_edges(selected):
            plan=self._build_plan(a,b);plans.append(plan)
            if persist:
                storer=getattr(self.cache_source,"store_generated_route_plan",None)
                if callable(storer):storer(plan.uid,self.version,plan.to_dict())
            self._mirror_trade_route(plan,a,b)
        if persist and plans:
            commit=getattr(self.cache_source,"commit_generated",None)
            if callable(commit):commit()
        return tuple(sorted(plans,key=lambda p:p.uid))
