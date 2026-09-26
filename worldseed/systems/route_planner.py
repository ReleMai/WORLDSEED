"""Sparse strategic route planning and bounded physical transport projection.

Phase 2 makes the selected regional graph the common road authority. Generated
RegionalRoutePlan records remain rebuildable cache data; mutable condition,
traffic and crossing damage live in LivingWorldState.route_infrastructure.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import heapq
from typing import Iterable

from worldseed.config import ROUTEGEN_VERSION
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import RouteInfrastructureState, TradeRouteState
from worldseed.world.regional_plan import CrossingPlan, RoadSegmentPlan, stable_plan_uid

REGION_SIZE = 512
CARDINALS = ((1,0),(-1,0),(0,1),(0,-1))


@dataclass(slots=True)
class RegionalRoutePlan:
    uid: str
    version: int
    origin: str
    destination: str
    region_path: list[tuple[int, int]] = field(default_factory=list)
    chunk_corridor: list[tuple[int, int]] = field(default_factory=list)
    portals: list[dict] = field(default_factory=list)
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
        row["portals"] = [dict(p) for p in row.get("portals", ())]
        row["crossings"] = [dict(p) for p in row.get("crossings", ())]
        return cls(**row)


class RoutePlanner:
    """Graph-first strategic roads with local terrain-aware materialization."""

    def __init__(self, world, state, region_planner, version: int | None = None):
        self.world = world
        self.state = state
        self.region_planner = region_planner
        self.seed = world.generator.world_seed
        if version is None:
            version = getattr(world, "routegen_version", ROUTEGEN_VERSION)
        self.version = int(version)
        self.cache_source = world.delta_source
        self._cache: dict[str, RegionalRoutePlan] = {}
        self._active_plans: dict[str, RegionalRoutePlan] = {}
        self._material_cache: dict[tuple, tuple[list[tuple[int,int]], list[CrossingPlan]]] = {}

    @staticmethod
    def _edge_uid(a: str, b: str) -> str:
        lo, hi = sorted((str(a), str(b)))
        return stable_plan_uid("regional-route", lo, hi)

    @staticmethod
    def _direction(a: tuple[int,int], b: tuple[int,int]) -> str:
        dx,dy=b[0]-a[0],b[1]-a[1]
        if dx==1:return "east"
        if dx==-1:return "west"
        if dy==1:return "south"
        return "north"

    @staticmethod
    def _opposite(direction: str) -> str:
        return {"north":"south","south":"north","east":"west","west":"east"}[direction]

    def _region_cost(self, rx: int, ry: int) -> int:
        plan = self.region_planner.plan(rx, ry, persist=True)
        cost = 100 + min(90, int(plan.relief) // 700)
        cost += max(0, 55 - int(getattr(plan, "route_value", 0)))
        if plan.control_potential == "bandit_frontier": cost += 30
        if plan.dominant_biome in {"water", "highland"}: cost += 28
        if plan.waters: cost += max(int(w.river_class) for w in plan.waters) * 6
        return max(20, cost)

    def _region_path(self, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
        if start == goal:return [start]
        pad=2
        left,right=min(start[0],goal[0])-pad,max(start[0],goal[0])+pad
        top,bottom=min(start[1],goal[1])-pad,max(start[1],goal[1])+pad
        heap=[(0,0,start)];best={start:0};came={}
        while heap:
            _,cost,cur=heapq.heappop(heap)
            if cost!=best.get(cur):continue
            if cur==goal:
                out=[cur]
                while cur in came:
                    cur=came[cur];out.append(cur)
                return list(reversed(out))
            for dx,dy in CARDINALS:
                nxt=(cur[0]+dx,cur[1]+dy)
                if not(left<=nxt[0]<=right and top<=nxt[1]<=bottom):continue
                nc=cost+self._region_cost(*nxt)
                if nc>=best.get(nxt,1<<60):continue
                best[nxt]=nc;came[nxt]=cur
                h=(abs(goal[0]-nxt[0])+abs(goal[1]-nxt[1]))*70
                heapq.heappush(heap,(nc+h,nc,nxt))
        return [start,goal]

    @staticmethod
    def _bresenham_chunks(a: tuple[int,int], b: tuple[int,int]) -> list[tuple[int,int]]:
        x0,y0=a[0]//32,a[1]//32;x1,y1=b[0]//32,b[1]//32
        dx=abs(x1-x0);dy=-abs(y1-y0);sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1
        err=dx+dy;out=[]
        while True:
            out.append((x0,y0))
            if (x0,y0)==(x1,y1):return out
            e2=2*err
            if e2>=dy:err+=dy;x0+=sx
            if e2<=dx:err+=dx;y0+=sy

    def _chunk_corridor(self,a,b,regions)->list[tuple[int,int]]:
        points=[(int(a.x),int(a.y))]+[(rx*REGION_SIZE+REGION_SIZE//2,ry*REGION_SIZE+REGION_SIZE//2) for rx,ry in regions[1:-1]]+[(int(b.x),int(b.y))]
        out=[]
        for p,q in zip(points,points[1:]):
            segment=self._bresenham_chunks(p,q)
            if out and segment and out[-1]==segment[0]:segment=segment[1:]
            out.extend(segment)
        return out

    def _boundary_cells(self, a: tuple[int,int], b: tuple[int,int], offset: int) -> tuple[tuple[int,int],tuple[int,int]]:
        direction=self._direction(a,b)
        ax0,ay0=a[0]*REGION_SIZE,a[1]*REGION_SIZE
        if direction=="east":
            return (ax0+REGION_SIZE-1,ay0+offset),(ax0+REGION_SIZE,ay0+offset)
        if direction=="west":
            return (ax0,ay0+offset),(ax0-1,ay0+offset)
        if direction=="south":
            return (ax0+offset,ay0+REGION_SIZE-1),(ax0+offset,ay0+REGION_SIZE)
        return (ax0+offset,ay0),(ax0+offset,ay0-1)

    def _boundary_water(self, a: tuple[int,int], b: tuple[int,int]):
        direction=self._direction(a,b)
        plan=self.region_planner.plan(*a,persist=True)
        water=next((w for w in plan.waters if w.direction==direction),None)
        if water is None:
            mate=self.region_planner.plan(*b,persist=True)
            water=next((w for w in mate.waters if w.direction==self._opposite(direction)),None)
        return water

    def _footing_offset(self, route_uid: str, index: int, a: tuple[int,int], b: tuple[int,int]) -> int:
        water=self._boundary_water(a,b)
        if water is not None and water.water_kind!="ocean":
            return max(16,min(REGION_SIZE-17,int(water.offset)))
        candidates=[]
        for offset in range(32,REGION_SIZE-31,24):
            pa,pb=self._boundary_cells(a,b,offset)
            ea=self.world.environment_at(WorldPos(pa[0],pa[1],0))
            eb=self.world.environment_at(WorldPos(pb[0],pb[1],0))
            if ea is None or eb is None:continue
            penalty=int(ea.slope)+int(eb.slope)+int(ea.flood_risk)+int(eb.flood_risk)
            if ea.open_water or eb.open_water:penalty+=160
            tie=int(hash_u64(self.seed,"route-portal-footing",route_uid,index,offset)%1000)
            candidates.append((penalty,tie,offset))
        if candidates:return min(candidates)[2]
        return 32+int(hash_u64(self.seed,"route-portal-offset",route_uid,index)% (REGION_SIZE-64))

    def _portals_and_crossings(self, route_uid: str, regions: list[tuple[int,int]]) -> tuple[list[dict],list[dict]]:
        portals=[];crossings=[]
        for index,(a,b) in enumerate(zip(regions,regions[1:])):
            water=self._boundary_water(a,b)
            offset=self._footing_offset(route_uid,index,a,b)
            from_cell,to_cell=self._boundary_cells(a,b,offset)
            crossing_id=""
            if water is not None and water.water_kind!="ocean":
                kind="ford" if int(water.river_class)<=1 else ("bridge" if int(water.river_class)<=3 else "ferry")
                crossing_id=stable_plan_uid("crossing",route_uid,f"{index}:{offset}:{kind}",[from_cell,to_cell])
                crossings.append({
                    "uid":crossing_id,"from_region":[a[0],a[1]],"to_region":[b[0],b[1]],
                    "x":from_cell[0],"y":from_cell[1],"kind":kind,
                    "river_class":int(water.river_class),"offset":int(offset),
                })
            portals.append({
                "index":index,"from_region":[a[0],a[1]],"to_region":[b[0],b[1]],
                "from_cell":[from_cell[0],from_cell[1]],"to_cell":[to_cell[0],to_cell[1]],
                "direction":self._direction(a,b),"crossing_id":crossing_id,
            })
        return portals,crossings

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

    def plan_by_uid(self, uid: str) -> RegionalRoutePlan | None:
        return self._active_plans.get(str(uid)) or self._cache.get(str(uid)) or self.read_prepared(str(uid))

    def _ensure_infrastructure(self, plan: RegionalRoutePlan) -> RouteInfrastructureState:
        infra=self.state.route_infrastructure.get(plan.uid)
        crossing_ids=[str(x.get("uid","")) for x in plan.crossings if x.get("uid")]
        if infra is None:
            infra=RouteInfrastructureState(plan.uid,crossing_conditions={uid:100 for uid in crossing_ids})
            self.state.route_infrastructure[plan.uid]=infra
        else:
            for uid in crossing_ids:infra.crossing_conditions.setdefault(uid,100)
            infra.blocked_crossings=[uid for uid in infra.blocked_crossings if uid in infra.crossing_conditions]
        infra.condition=max(0,min(100,int(infra.condition)))
        infra.blocked=bool(infra.blocked or infra.condition<=10 or infra.blocked_crossings)
        return infra

    def _build_plan(self,a,b)->RegionalRoutePlan:
        if a.uid>b.uid:a,b=b,a
        uid=self._edge_uid(a.uid,b.uid)
        cached=self.read_prepared(uid)
        if cached is not None:
            self._ensure_infrastructure(cached)
            return cached
        regions=self._region_path((a.region_x,a.region_y),(b.region_x,b.region_y))
        portals,crossings=self._portals_and_crossings(uid,regions) if self.version>=3 else ([],[])
        cost=sum(self._region_cost(*r) for r in regions[1:])
        danger=min(95,max(0,cost//max(1,len(regions))//4+len(crossings)*4))
        route_class="maintained_road" if max(a.population,b.population)>=150 else ("road" if a.population+b.population>=80 else "trail")
        payload={
            "uid":uid,"version":self.version,"origin":a.uid,"destination":b.uid,
            "region_path":regions,"chunk_corridor":self._chunk_corridor(a,b,regions),
            "portals":portals,"crossings":crossings,"route_class":route_class,
            "cost":int(cost),"danger":int(danger),
        }
        plan=RegionalRoutePlan(**payload,fingerprint=canonical_hash(payload))
        self._cache[uid]=plan;self._ensure_infrastructure(plan)
        return plan

    def _candidate_edges(self,settlements):
        rows=sorted(settlements,key=lambda s:s.uid)
        by_region={}
        for s in rows:by_region.setdefault((int(s.region_x),int(s.region_y)),[]).append(s)
        out={}
        for a in rows:
            nearby=[]
            for dy in range(-12,13):
                for dx in range(-12,13):
                    for b in by_region.get((int(a.region_x)+dx,int(a.region_y)+dy),()):
                        if b.uid==a.uid:continue
                        rough=abs(dx)+abs(dy)
                        if rough>12:continue
                        nearby.append((rough,b.uid,b))
            nearby.sort(key=lambda row:(row[0],row[1]))
            for distance,_,b in nearby[:4]:
                lo,hi=sorted((a.uid,b.uid))
                if (lo,hi) in out:continue
                pa=self.region_planner.plan(a.region_x,a.region_y,persist=True)
                pb=self.region_planner.plan(b.region_x,b.region_y,persist=True)
                utility=int(getattr(pa,"route_value",0))+int(getattr(pb,"route_value",0))
                utility+=min(80,a.population+b.population)//2
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
        infra=self._ensure_infrastructure(plan)
        base_minutes=max(180,int(plan.cost)*5)
        condition=max(10,int(infra.condition))
        minutes=base_minutes*100//condition
        class_capacity=160 if plan.route_class=="maintained_road" else 100 if plan.route_class=="road" else 55
        capacity=0 if infra.blocked else max(1,class_capacity*condition//100)
        danger=min(100,int(plan.danger)+(100-condition)//3+(35 if infra.blocked else 0))
        for origin,destination,path,chunks,suffix in (
            (a,b,plan.region_path,plan.chunk_corridor,"a"),
            (b,a,list(reversed(plan.region_path)),list(reversed(plan.chunk_corridor)),"b"),
        ):
            uid=f"{plan.uid}:{suffix}";old=self.state.trade_routes.get(uid)
            self.state.trade_routes[uid]=TradeRouteState(
                uid,origin.uid,destination.uid,max(1,len(path)-1),danger,capacity,
                int(old.last_used_minute) if old else 0,int(old.traffic) if old else 0,
                [f"{rx},{ry}" for rx,ry in path],minutes,[f"{cx},{cy}" for cx,cy in chunks],
                plan.uid,
            )

    def _persist(self, plans: Iterable[RegionalRoutePlan], persist: bool) -> None:
        if not persist:return
        storer=getattr(self.cache_source,"store_generated_route_plan",None)
        if callable(storer):
            for plan in plans:storer(plan.uid,self.version,plan.to_dict())
        commit=getattr(self.cache_source,"commit_generated",None)
        if callable(commit):commit()

    def _sync_rows(self, rows, *, persist: bool, cleanup: bool) -> tuple[RegionalRoutePlan,...]:
        plans=[]
        settlement_by_uid={s.uid:s for s in rows}
        for _,_,_,a,b in self._select_sparse_edges(rows):
            plan=self._build_plan(a,b);plans.append(plan);self._mirror_trade_route(plan,a,b)
        self._persist(plans,persist)
        if cleanup:
            valid={p.uid for p in plans}
            for uid,route in list(self.state.trade_routes.items()):
                if route.physical_route_id and route.physical_route_id not in valid:self.state.trade_routes.pop(uid,None)
            for uid in list(self.state.route_infrastructure):
                if uid not in valid:self.state.route_infrastructure.pop(uid,None)
        self._active_plans={p.uid:p for p in plans}
        self._update_centrality_and_hinterlands(settlement_by_uid,plans)
        return tuple(sorted(plans,key=lambda p:p.uid))

    def sync(self,settlements,center_region:tuple[int,int],radius:int=2,*,persist:bool=True)->tuple[RegionalRoutePlan,...]:
        if self.version<2:return ()
        rx,ry=map(int,center_region)
        selected=sorted((s for s in settlements if abs(int(s.region_x)-rx)<=radius and abs(int(s.region_y)-ry)<=radius),key=lambda s:s.uid)[:32]
        return self._sync_rows(selected,persist=persist,cleanup=False)

    def sync_network(self,settlements,*,persist:bool=True)->tuple[RegionalRoutePlan,...]:
        """Rebuild the sparse graph for already-realized settlements only."""
        if self.version<3:return ()
        rows=sorted(settlements,key=lambda s:s.uid)
        return self._sync_rows(rows,persist=persist,cleanup=True)

    def links_for_settlement(self, settlement_id: str) -> tuple[dict,...]:
        settlement_id=str(settlement_id);out=[]
        for plan in sorted(self._active_plans.values(),key=lambda p:p.uid):
            if len(plan.region_path)<2 or not plan.portals:continue
            if plan.origin==settlement_id:
                portal=plan.portals[0]
                out.append({"route_id":plan.uid,"direction":str(portal["direction"]),
                            "portal_cell":tuple(map(int,portal["from_cell"])),"road_class":plan.route_class,
                            "crossing_id":str(portal.get("crossing_id",""))})
            elif plan.destination==settlement_id:
                portal=plan.portals[-1]
                dest=plan.region_path[-1];prev=plan.region_path[-2]
                out.append({"route_id":plan.uid,"direction":self._direction(dest,prev),
                            "portal_cell":tuple(map(int,portal["to_cell"])),"road_class":plan.route_class,
                            "crossing_id":str(portal.get("crossing_id",""))})
        return tuple(out)

    @staticmethod
    def _gateway_for_route(skeleton, route_id: str, toward: tuple[int,int]) -> tuple[int,int]:
        routed=[r for r in skeleton.roads if str(getattr(r,"route_id",""))==str(route_id) and r.polyline]
        if routed:
            return min((tuple(r.polyline[-1]) for r in routed),key=lambda p:abs(p[0]-toward[0])+abs(p[1]-toward[1]))
        gateways=[tuple(map(int,p)) for p in skeleton.plan.gateway_cells]
        if gateways:return min(gateways,key=lambda p:abs(p[0]-toward[0])+abs(p[1]-toward[1]))
        cells=[tuple(map(int,p)) for p in skeleton.plan.common_cells]
        if cells:return min(cells,key=lambda p:abs(p[0]-toward[0])+abs(p[1]-toward[1]))
        return int(skeleton.plan.anchor_x),int(skeleton.plan.anchor_y)

    def _local_cost(self,x:int,y:int)->int:
        env=self.world.environment_at(WorldPos(int(x),int(y),0))
        if env is None:return 80
        cost=8+int(env.slope)*2+int(env.flood_risk)*2
        if env.open_water:cost+=130
        elif int(env.wetness)>80:cost+=25
        return max(4,cost)

    def _local_path(self,start:tuple[int,int],goal:tuple[int,int],region:tuple[int,int])->list[tuple[int,int]]:
        if start==goal:return [start]
        rx,ry=region;x0,y0=rx*REGION_SIZE,ry*REGION_SIZE
        margin=72
        left=max(x0,min(start[0],goal[0])-margin);right=min(x0+REGION_SIZE-1,max(start[0],goal[0])+margin)
        top=max(y0,min(start[1],goal[1])-margin);bottom=min(y0+REGION_SIZE-1,max(start[1],goal[1])+margin)
        heap=[(0,0,start[1],start[0])];best={start:0};came={}
        while heap:
            _,cost,y,x=heapq.heappop(heap);cur=(x,y)
            if cost!=best.get(cur):continue
            if cur==goal:
                out=[cur]
                while cur in came:cur=came[cur];out.append(cur)
                return list(reversed(out))
            for dx,dy in CARDINALS:
                nx,ny=x+dx,y+dy
                if not(left<=nx<=right and top<=ny<=bottom):continue
                nc=cost+self._local_cost(nx,ny);nxt=(nx,ny)
                if nc>=best.get(nxt,1<<60):continue
                best[nxt]=nc;came[nxt]=cur
                h=(abs(goal[0]-nx)+abs(goal[1]-ny))*8
                heapq.heappush(heap,(nc+h,nc,ny,nx))
        return []

    @staticmethod
    def _chunk_path(path:list[tuple[int,int]])->list[tuple[int,int]]:
        out=[]
        for x,y in path:
            key=(x//32,y//32)
            if not out or out[-1]!=key:out.append(key)
        return out

    def _physical_crossings(self,route_id:str,region:tuple[int,int],path:list[tuple[int,int]],known:list[dict])->list[CrossingPlan]:
        known_by_cell={(int(c.get("x",0)),int(c.get("y",0))):c for c in known}
        runs=[];run=[]
        for cell in path:
            env=self.world.environment_at(WorldPos(cell[0],cell[1],0))
            if env is not None and env.open_water:run.append(cell)
            elif run:runs.append(run);run=[]
        if run:runs.append(run)
        out=[]
        for index,cells in enumerate(runs):
            mid=cells[len(cells)//2]
            nearby=min(known_by_cell,key=lambda p:abs(p[0]-mid[0])+abs(p[1]-mid[1])) if known_by_cell else None
            known_row=known_by_cell.get(nearby) if nearby is not None and abs(nearby[0]-mid[0])+abs(nearby[1]-mid[1])<=3 else None
            if known_row:
                uid=str(known_row["uid"]);kind=str(known_row["kind"]);river_class=int(known_row.get("river_class",1))
            else:
                kind="ford" if len(cells)<=2 else ("bridge" if len(cells)<=5 else "ferry")
                river_class=min(5,max(1,(len(cells)+1)//2))
                uid=stable_plan_uid("crossing",route_id,f"local:{region[0]},{region[1]}:{index}:{kind}",cells)
            out.append(CrossingPlan(uid,route_id,mid[0],mid[1],kind,river_class))
        return out

    def materialize_region(self, region: tuple[int,int], skeletons: dict[str,object]) -> tuple[tuple[RoadSegmentPlan,...],tuple[CrossingPlan,...]]:
        """Create exact local road cells only for one active prepared region."""
        if self.version<3:return (),()
        rx,ry=map(int,region);roads=[];crossings=[]
        for plan in sorted(self._active_plans.values(),key=lambda p:p.uid):
            try:index=plan.region_path.index((rx,ry))
            except ValueError:continue
            if len(plan.region_path)<2:continue
            if index==0:
                portal=plan.portals[0]
                skeleton=skeletons.get(plan.origin)
                start=self._gateway_for_route(skeleton,plan.uid,tuple(portal["from_cell"])) if skeleton is not None else tuple(portal["from_cell"])
            else:
                start=tuple(map(int,plan.portals[index-1]["to_cell"]))
            if index==len(plan.region_path)-1:
                portal=plan.portals[-1]
                skeleton=skeletons.get(plan.destination)
                goal=self._gateway_for_route(skeleton,plan.uid,tuple(portal["to_cell"])) if skeleton is not None else tuple(portal["to_cell"])
            else:
                goal=tuple(map(int,plan.portals[index]["from_cell"]))
            cache_key=(plan.uid,rx,ry,start,goal)
            cached=self._material_cache.get(cache_key)
            if cached is None:
                path=self._local_path(start,goal,(rx,ry))
                if len(path)<2:continue
                local_crossings=self._physical_crossings(plan.uid,(rx,ry),path,plan.crossings)
                self._material_cache[cache_key]=(path,local_crossings)
            else:path,local_crossings=cached
            infra=self._ensure_infrastructure(plan)
            crossing_ids=[c.uid for c in local_crossings]
            blocked=infra.blocked or any(uid in infra.blocked_crossings for uid in crossing_ids)
            uid=stable_plan_uid("regional-road-segment",plan.uid,f"{rx},{ry}",path)
            roads.append(RoadSegmentPlan(
                uid=uid,route_id=plan.uid,road_class=plan.route_class,polyline=list(path),
                chunk_corridor=self._chunk_path(path),width=2 if plan.route_class=="maintained_road" else 1,
                surface="stone" if plan.route_class=="maintained_road" else "earth",
                condition=int(infra.condition),traffic=int(infra.traffic),
                crossing_ids=crossing_ids,blocked=bool(blocked),
                last_maintenance_minute=int(infra.last_maintenance_minute),
            ))
            crossings.extend(local_crossings)
        return tuple(roads),tuple(crossings)

    def record_usage(self,route_id:str,minute:int,amount:int=1)->None:
        plan=self.plan_by_uid(route_id)
        if plan is None:return
        infra=self._ensure_infrastructure(plan)
        before=int(infra.traffic);infra.traffic=max(0,before+max(1,int(amount)));infra.last_used_minute=int(minute)
        wear=infra.traffic//8-before//8
        if wear>0:infra.condition=max(0,infra.condition-wear)
        infra.blocked=bool(infra.condition<=10 or infra.blocked_crossings)

    def damage_route(self,route_id:str,amount:int,*,crossing_id:str="")->None:
        plan=self.plan_by_uid(route_id)
        if plan is None:return
        infra=self._ensure_infrastructure(plan);amount=max(0,int(amount))
        if crossing_id:
            if crossing_id in infra.crossing_conditions:
                infra.crossing_conditions[crossing_id]=max(0,infra.crossing_conditions[crossing_id]-amount)
                if infra.crossing_conditions[crossing_id]<=10 and crossing_id not in infra.blocked_crossings:infra.blocked_crossings.append(crossing_id)
        else:infra.condition=max(0,infra.condition-amount)
        infra.blocked=bool(infra.condition<=10 or infra.blocked_crossings)

    def repair_route(self,route_id:str,amount:int,minute:int,*,crossing_id:str="")->None:
        plan=self.plan_by_uid(route_id)
        if plan is None:return
        infra=self._ensure_infrastructure(plan);amount=max(0,int(amount))
        if crossing_id and crossing_id in infra.crossing_conditions:
            infra.crossing_conditions[crossing_id]=min(100,infra.crossing_conditions[crossing_id]+amount)
            if infra.crossing_conditions[crossing_id]>10:infra.blocked_crossings=[x for x in infra.blocked_crossings if x!=crossing_id]
        else:infra.condition=min(100,infra.condition+amount)
        infra.last_maintenance_minute=int(minute);infra.blocked=bool(infra.condition<=10 or infra.blocked_crossings)

    def monthly_update(self,minute:int)->None:
        """Wear routes and let endpoint factions causally fund bounded repairs."""
        month=int(minute)//(30*1440)
        for plan in sorted(self._active_plans.values(),key=lambda p:p.uid):
            infra=self._ensure_infrastructure(plan)
            marker=f"_route_month:{plan.uid}"
            last=int(getattr(infra,"last_used_minute",0))//(30*1440)
            # Passive exposure is intentionally mild; traffic wear is charged by
            # record_usage. Avoid repeated decay when offline/full cadence lands
            # on the same monthly boundary.
            if last<month and infra.condition>0:infra.condition=max(0,infra.condition-1)
            a=self.state.settlements.get(plan.origin);b=self.state.settlements.get(plan.destination)
            same_faction=bool(a and b and a.faction_id and a.faction_id==b.faction_id)
            faction=self.state.factions.get(a.faction_id) if same_faction and a else None
            if faction is not None and infra.condition<82 and faction.treasury>20:
                repair=min(10,100-infra.condition);cost=max(2,repair*2)
                if faction.treasury>=cost:
                    faction.treasury-=cost;self.repair_route(plan.uid,repair,minute)
            infra.blocked=bool(infra.condition<=10 or infra.blocked_crossings)
            if a is not None and b is not None:self._mirror_trade_route(plan,a,b)

    def _update_centrality_and_hinterlands(self, settlements: dict[str,object], plans: list[RegionalRoutePlan]) -> None:
        degree={uid:0 for uid in settlements}
        route_edges=set();candidate_regions=set()
        for s in settlements.values():
            candidate_regions.add((int(s.region_x),int(s.region_y)))
        for plan in plans:
            degree[plan.origin]=degree.get(plan.origin,0)+1;degree[plan.destination]=degree.get(plan.destination,0)+1
            candidate_regions.update(plan.region_path)
            for a,b in zip(plan.region_path,plan.region_path[1:]):route_edges.add(tuple(sorted((a,b))))
        for region in list(candidate_regions):
            for dx,dy in CARDINALS:candidate_regions.add((region[0]+dx,region[1]+dy))
        for uid,s in settlements.items():
            s.route_centrality=min(100,degree.get(uid,0)*24+sum(1 for p in plans if (int(s.region_x),int(s.region_y)) in p.region_path[1:-1])*12)

        factions={s.faction_id for s in settlements.values() if s.faction_id in self.state.factions}
        for faction_id in factions:
            faction=self.state.factions[faction_id];sources=[s for s in settlements.values() if s.faction_id==faction_id]
            if not sources:continue
            heap=[];best={}
            for s in sources:
                region=(int(s.region_x),int(s.region_y))
                initial=max(0,28-int(s.population)//12-int(getattr(faction,"prominence",0))//8)
                if initial<best.get(region,1<<60):best[region]=initial;heapq.heappush(heap,(initial,region))
            while heap:
                cost,cur=heapq.heappop(heap)
                if cost!=best.get(cur):continue
                for dx,dy in CARDINALS:
                    nxt=(cur[0]+dx,cur[1]+dy)
                    if nxt not in candidate_regions:continue
                    edge=tuple(sorted((cur,nxt)))
                    step=8 if edge in route_edges else 30
                    nc=cost+step
                    if nc>=best.get(nxt,1<<60):continue
                    best[nxt]=nc;heapq.heappush(heap,(nc,nxt))
            faction.influence_regions={
                f"{r[0]},{r[1]}":max(0,100-c)
                for r,c in sorted(best.items()) if c<100
            }

        winners={}
        for faction_id in factions:
            faction=self.state.factions[faction_id]
            for region,score in faction.influence_regions.items():
                row=(int(score),int(getattr(faction,"prominence",0)),faction_id)
                if region not in winners or row>winners[region]:winners[region]=row
        for faction_id in factions:
            faction=self.state.factions[faction_id]
            faction.hinterland_regions=sorted(
                region for region,row in winners.items()
                if row[2]==faction_id and row[0]>=35
            )
