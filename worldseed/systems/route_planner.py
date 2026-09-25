from __future__ import annotations

from dataclasses import asdict, dataclass, field
import heapq
from typing import Iterable

from worldseed.config import ROUTEGEN_VERSION
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.world.regional_plan import CrossingPlan, RoadSegmentPlan, stable_plan_uid


@dataclass(slots=True)
class StrategicRoutePlan:
    uid: str
    version: int
    origin_id: str
    destination_id: str
    region_path: list[tuple[int, int]] = field(default_factory=list)
    road_segments: list[RoadSegmentPlan] = field(default_factory=list)
    crossings: list[CrossingPlan] = field(default_factory=list)
    utility: int = 0
    travel_cost: int = 0
    fingerprint: str = ""

    def to_dict(self) -> dict:
        payload={
            "uid":self.uid,"version":self.version,
            "origin_id":self.origin_id,"destination_id":self.destination_id,
            "region_path":[list(p) for p in self.region_path],
            "road_segments":[asdict(x) for x in self.road_segments],
            "crossings":[asdict(x) for x in self.crossings],
            "utility":self.utility,"travel_cost":self.travel_cost,
        }
        payload["fingerprint"]=self.fingerprint or canonical_hash(payload)
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> "StrategicRoutePlan":
        segments=[]
        for item in raw.get("road_segments",()):
            row=dict(item)
            row["polyline"]=[tuple(map(int,p)) for p in row.get("polyline",())]
            row["chunk_corridor"]=[tuple(map(int,p)) for p in row.get("chunk_corridor",())]
            segments.append(RoadSegmentPlan(**row))
        crossings=[CrossingPlan(**dict(x)) for x in raw.get("crossings",())]
        return cls(
            uid=str(raw["uid"]),version=int(raw["version"]),
            origin_id=str(raw["origin_id"]),destination_id=str(raw["destination_id"]),
            region_path=[tuple(map(int,p)) for p in raw.get("region_path",())],
            road_segments=segments,crossings=crossings,
            utility=int(raw.get("utility",0)),travel_cost=int(raw.get("travel_cost",0)),
            fingerprint=str(raw.get("fingerprint","")),
        )


class StrategicRoutePlanner:
    """Sparse civilization route planner.

    The strategic graph is chosen from settlement geography first. Selected
    edges are converted into deterministic terrain-aware region corridors and
    persisted as generated route plans. Exact local road refinement can consume
    the same stable route IDs later without changing economic authority.
    """

    def __init__(self, world, state, region_planner, version: int | None = None):
        self.world=world
        self.state=state
        self.region_planner=region_planner
        self.seed=world.generator.world_seed
        self.cache_source=world.delta_source
        self.version=int(ROUTEGEN_VERSION if version is None else version)
        self._cache:dict[str,StrategicRoutePlan]={}

    @staticmethod
    def _distance(a,b)->int:
        return abs(int(a.region_x)-int(b.region_x))+abs(int(a.region_y)-int(b.region_y))

    def _region_cost(self, rx:int, ry:int)->int:
        plan=self.region_planner.plan(rx,ry,persist=True)
        cost=100
        cost+=min(180,int(plan.relief)//80)
        if "rugged" in plan.wilderness_tags:cost+=90
        if "dry" in plan.wilderness_tags:cost+=20
        if plan.dominant_biome=="water":cost+=900
        elif plan.dominant_biome=="highland":cost+=160
        elif plan.dominant_biome=="forest":cost+=35
        if plan.settlement_present:cost=max(45,cost-35)
        return cost

    def _regional_path(self,start:tuple[int,int],goal:tuple[int,int],max_nodes:int=1200)->tuple[list[tuple[int,int]],int]:
        if start==goal:return [start],0
        minx,maxx=sorted((start[0],goal[0]));miny,maxy=sorted((start[1],goal[1]))
        margin=3
        bounds=(minx-margin,miny-margin,maxx+margin,maxy+margin)
        heap=[(0,0,start)]
        best={start:0};came={}
        nodes=0
        while heap and nodes<max_nodes:
            _,cost,cur=heapq.heappop(heap);nodes+=1
            if cost!=best.get(cur):continue
            if cur==goal:break
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nxt=(cur[0]+dx,cur[1]+dy)
                if not (bounds[0]<=nxt[0]<=bounds[2] and bounds[1]<=nxt[1]<=bounds[3]):continue
                step=self._region_cost(*nxt)
                ncost=cost+step
                if ncost>=best.get(nxt,1<<60):continue
                best[nxt]=ncost;came[nxt]=cur
                h=(abs(nxt[0]-goal[0])+abs(nxt[1]-goal[1]))*70
                heapq.heappush(heap,(ncost+h,ncost,nxt))
        if goal not in best:return [],1<<30
        out=[goal]
        while out[-1]!=start:out.append(came[out[-1]])
        out.reverse()
        return out,best[goal]

    def _chunk_corridor(self,a,b,regions:list[tuple[int,int]])->list[tuple[int,int]]:
        """Create a deterministic chunk corridor through selected macro regions."""
        start=(int(a.x)//32,int(a.y)//32);goal=(int(b.x)//32,int(b.y)//32)
        way=[start]
        for rx,ry in regions[1:-1]:
            block=self.region_planner.plan(rx,ry,persist=True)
            if block.settlement_anchor is not None:
                way.append((block.settlement_anchor[0]//32,block.settlement_anchor[1]//32))
            else:
                way.append((rx*16+8,ry*16+8))
        way.append(goal)
        out=[]
        for p0,p1 in zip(way,way[1:]):
            x0,y0=p0;x1,y1=p1
            dx=abs(x1-x0);dy=-abs(y1-y0);sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1;err=dx+dy
            while True:
                if not out or out[-1]!=(x0,y0):out.append((x0,y0))
                if (x0,y0)==(x1,y1):break
                e2=2*err
                if e2>=dy:err+=dy;x0+=sx
                if e2<=dx:err+=dx;y0+=sy
        return out

    def _crossings(self,route_uid:str,chunks:Iterable[tuple[int,int]])->list[CrossingPlan]:
        hydro=getattr(self.world.generator,"hydrology",None)
        if hydro is None:return []
        out=[]
        for cx,cy in chunks:
            x,y=cx*32+16,cy*32+16
            surface=hydro.surface_at(WorldPos(x,y,0),prepared_only=True)
            cls=int(getattr(surface,"river_class",0) or 0) if surface is not None else 0
            if cls<=0:continue
            kind="ford" if cls<=2 else "bridge"
            uid=stable_plan_uid("crossing",route_uid,f"{cx}:{cy}:{kind}",[(x,y)])
            out.append(CrossingPlan(uid,route_uid,x,y,kind,cls))
        return out

    def _edge_utility(self,a,b)->int:
        dist=max(1,self._distance(a,b))
        complement=0
        for good in set(a.stocks)|set(b.stocks):
            complement+=abs(int(a.stocks.get(good,0))-int(b.stocks.get(good,0)))
        same_faction=35 if a.faction_id==b.faction_id else 0
        return max(1,220-dist*24+min(90,complement//12)+same_faction)

    def candidate_edges(self, settlements:Iterable, neighbors:int=4)->list[tuple[int,str,str,object,object]]:
        towns=sorted(settlements,key=lambda s:s.uid)
        pairs={}
        for a in towns:
            ranked=sorted(
                ((self._distance(a,b),b.uid,b) for b in towns if b.uid!=a.uid),
                key=lambda row:(row[0],row[1]),
            )[:max(1,int(neighbors))]
            for _,_,b in ranked:
                lo,hi=sorted((a.uid,b.uid));pairs[(lo,hi)]=(a,b) if a.uid==lo else (b,a)
        rows=[]
        for (lo,hi),(a,b) in pairs.items():
            utility=self._edge_utility(a,b)
            rows.append((-utility,self._distance(a,b),lo,hi,a,b))
        rows.sort(key=lambda r:(r[0],r[1],r[2],r[3]))
        return [( -r[0],r[2],r[3],r[4],r[5]) for r in rows]

    def select_sparse_graph(self, settlements:Iterable, extra_edges:int|None=None)->list[tuple[object,object,int]]:
        towns=sorted(settlements,key=lambda s:s.uid)
        if len(towns)<2:return []
        edges=self.candidate_edges(towns)
        parent={t.uid:t.uid for t in towns}
        def find(x):
            while parent[x]!=x:
                parent[x]=parent[parent[x]];x=parent[x]
            return x
        chosen=[];used=set()
        for utility,lo,hi,a,b in sorted(edges,key=lambda r:(self._distance(r[3],r[4]),-r[0],r[1],r[2])):
            ra,rb=find(lo),find(hi)
            if ra==rb:continue
            parent[rb]=ra;chosen.append((a,b,utility));used.add((lo,hi))
        budget=max(1,len(towns)//4) if extra_edges is None else max(0,int(extra_edges))
        for utility,lo,hi,a,b in edges:
            if budget<=0:break
            if (lo,hi) in used:continue
            chosen.append((a,b,utility));used.add((lo,hi));budget-=1
        return chosen

    def _route_uid(self,a,b)->str:
        lo,hi=sorted((a.uid,b.uid))
        return stable_plan_uid("route","regional-civilization",f"{lo}>{hi}")

    def read_prepared(self,route_uid:str)->StrategicRoutePlan|None:
        route_uid=str(route_uid)
        if route_uid in self._cache:return self._cache[route_uid]
        loader=getattr(self.cache_source,"load_generated_route_plan",None)
        if not callable(loader):return None
        raw=loader(route_uid,self.version)
        if not raw:return None
        try:
            fingerprint=str(raw.get("fingerprint",""));check=dict(raw);check.pop("fingerprint",None)
            if fingerprint!=canonical_hash(check):return None
            plan=StrategicRoutePlan.from_dict(raw)
            if plan.uid!=route_uid or plan.version!=self.version:return None
            self._cache[route_uid]=plan;return plan
        except (KeyError,TypeError,ValueError):
            return None

    def plan_edge(self,a,b,*,persist:bool=True,refresh:bool=False)->StrategicRoutePlan:
        uid=self._route_uid(a,b)
        if not refresh:
            prepared=self.read_prepared(uid)
            if prepared is not None:return prepared
        regions,cost=self._regional_path((a.region_x,a.region_y),(b.region_x,b.region_y))
        chunks=self._chunk_corridor(a,b,regions)
        segment=RoadSegmentPlan(
            uid=stable_plan_uid("road-segment",uid,0,chunks),
            route_id=uid,road_class="road",chunk_corridor=chunks,width=1,surface="earth",
        )
        crossings=self._crossings(uid,chunks)
        segment.crossing_ids=[x.uid for x in crossings]
        plan=StrategicRoutePlan(
            uid=uid,version=self.version,origin_id=a.uid,destination_id=b.uid,
            region_path=regions,road_segments=[segment],crossings=crossings,
            utility=self._edge_utility(a,b),travel_cost=cost,
        )
        raw=plan.to_dict();plan.fingerprint=raw["fingerprint"]
        self._cache[uid]=plan
        if persist:
            storer=getattr(self.cache_source,"store_generated_route_plan",None)
            if callable(storer):
                storer(uid,self.version,raw)
                commit=getattr(self.cache_source,"commit_generated",None)
                if callable(commit):commit()
        return plan

    def plan_network(self, settlements:Iterable, *, persist:bool=True)->list[StrategicRoutePlan]:
        plans=[]
        for a,b,_ in self.select_sparse_graph(settlements):
            plans.append(self.plan_edge(a,b,persist=persist))
        return plans
