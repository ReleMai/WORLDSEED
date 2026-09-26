"""Sparse strategic route planning, dynamic transport and frontier control.

Generated route geometry is reconstructable cache data. Mutable condition,
crossing damage, detours, tolls and patrol state live in LivingWorldState so
weather, fire and war can change travel without inventing a second road graph.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import heapq
from typing import Iterable

from worldseed.config import ROUTEGEN_VERSION
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import BorderPostState, RouteInfrastructureState, TradeRouteState
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
        if self.version < 3:
            raw.pop("portals", None)
        raw["fingerprint"] = self.fingerprint or canonical_hash(
            {k:v for k,v in raw.items() if k!="fingerprint"}
        )
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
    """Graph-first roads with bounded local materialization and dynamic detours."""

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

    @staticmethod
    def _region_token(region: tuple[int,int]) -> str:
        return f"{int(region[0])},{int(region[1])}"

    @staticmethod
    def _parse_region(token: str) -> tuple[int,int]:
        a,b=str(token).split(",",1)
        return int(a),int(b)

    @staticmethod
    def _transition(a: tuple[int,int], b: tuple[int,int]) -> tuple[tuple[int,int],tuple[int,int]]:
        return tuple(sorted((tuple(a),tuple(b))))  # type: ignore[return-value]

    def _region_cost(self, rx: int, ry: int) -> int:
        plan = self.region_planner.plan(rx, ry, persist=True)
        cost = 100 + min(90, int(plan.relief) // 700)
        cost += max(0, 55 - int(getattr(plan, "route_value", 0)))
        if plan.control_potential == "bandit_frontier": cost += 30
        if plan.dominant_biome in {"water", "highland"}: cost += 28
        if plan.waters: cost += max(int(w.river_class) for w in plan.waters) * 6
        return max(20, cost)

    def _region_path(self, start: tuple[int,int], goal: tuple[int,int]) -> list[tuple[int,int]]:
        return self._region_path_dynamic(start,goal,set(),set(),pad=2,fallback=True)

    def _region_path_dynamic(
        self,
        start: tuple[int,int],
        goal: tuple[int,int],
        blocked_edges: set[tuple[tuple[int,int],tuple[int,int]]],
        hazard_regions: set[tuple[int,int]],
        *,
        pad: int = 4,
        fallback: bool = False,
    ) -> list[tuple[int,int]]:
        if start==goal:return [start]
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
                if self._transition(cur,nxt) in blocked_edges:continue
                nc=cost+self._region_cost(*nxt)
                if nxt in hazard_regions and nxt not in {start,goal}:nc+=260
                if nc>=best.get(nxt,1<<60):continue
                best[nxt]=nc;came[nxt]=cur
                h=(abs(goal[0]-nxt[0])+abs(goal[1]-nxt[1]))*70
                heapq.heappush(heap,(nc+h,nc,nxt))
        return [start,goal] if fallback else []

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
        points=[(int(a.x),int(a.y))]
        points += [(rx*REGION_SIZE+REGION_SIZE//2,ry*REGION_SIZE+REGION_SIZE//2) for rx,ry in regions[1:-1]]
        points += [(int(b.x),int(b.y))]
        out=[]
        for p,q in zip(points,points[1:]):
            segment=self._bresenham_chunks(p,q)
            if out and segment and out[-1]==segment[0]:segment=segment[1:]
            out.extend(segment)
        return out

    def _boundary_cells(self,a:tuple[int,int],b:tuple[int,int],offset:int)->tuple[tuple[int,int],tuple[int,int]]:
        direction=self._direction(a,b);ax0,ay0=a[0]*REGION_SIZE,a[1]*REGION_SIZE
        if direction=="east":return (ax0+REGION_SIZE-1,ay0+offset),(ax0+REGION_SIZE,ay0+offset)
        if direction=="west":return (ax0,ay0+offset),(ax0-1,ay0+offset)
        if direction=="south":return (ax0+offset,ay0+REGION_SIZE-1),(ax0+offset,ay0+REGION_SIZE)
        return (ax0+offset,ay0),(ax0+offset,ay0-1)

    def _boundary_water(self,a:tuple[int,int],b:tuple[int,int]):
        direction=self._direction(a,b)
        plan=self.region_planner.plan(*a,persist=True)
        water=next((w for w in plan.waters if w.direction==direction),None)
        if water is None:
            mate=self.region_planner.plan(*b,persist=True)
            water=next((w for w in mate.waters if w.direction==self._opposite(direction)),None)
        return water

    def _footing_offset(self,route_uid:str,index:int,a:tuple[int,int],b:tuple[int,int])->int:
        water=self._boundary_water(a,b)
        if water is not None and water.water_kind!="ocean":
            return max(16,min(REGION_SIZE-17,int(water.offset)))
        transition=self._transition(a,b)
        candidates=[]
        for offset in range(32,REGION_SIZE-31,24):
            pa,pb=self._boundary_cells(a,b,offset)
            ea=self.world.environment_at(WorldPos(pa[0],pa[1],0))
            eb=self.world.environment_at(WorldPos(pb[0],pb[1],0))
            if ea is None or eb is None:continue
            penalty=int(ea.slope)+int(eb.slope)+int(ea.flood_risk)+int(eb.flood_risk)
            if ea.open_water or eb.open_water:penalty+=160
            tie_args=(route_uid,index,offset) if self.version==3 else (
                route_uid,transition[0][0],transition[0][1],transition[1][0],transition[1][1],offset
            )
            tie=int(hash_u64(self.seed,"route-portal-footing",*tie_args)%1000)
            candidates.append((penalty,tie,offset))
        if candidates:return min(candidates)[2]
        seed_args=(route_uid,index) if self.version==3 else (
            route_uid,transition[0][0],transition[0][1],transition[1][0],transition[1][1]
        )
        return 32+int(hash_u64(self.seed,"route-portal-offset",*seed_args)%(REGION_SIZE-64))

    def _portals_and_crossings(self,route_uid:str,regions:list[tuple[int,int]])->tuple[list[dict],list[dict]]:
        portals=[];crossings=[]
        for index,(a,b) in enumerate(zip(regions,regions[1:])):
            water=self._boundary_water(a,b);offset=self._footing_offset(route_uid,index,a,b)
            from_cell,to_cell=self._boundary_cells(a,b,offset);crossing_id=""
            if water is not None and water.water_kind!="ocean":
                kind="ford" if int(water.river_class)<=1 else ("bridge" if int(water.river_class)<=3 else "ferry")
                if self.version==3:
                    slot=f"{index}:{offset}:{kind}"
                else:
                    pair=self._transition(a,b)
                    slot=f"{pair[0][0]},{pair[0][1]}>{pair[1][0]},{pair[1][1]}:{offset}:{kind}"
                crossing_id=stable_plan_uid("crossing",route_uid,slot,[from_cell,to_cell])
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

    def active_plans(self)->tuple[RegionalRoutePlan,...]:
        return tuple(self._active_plans[key] for key in sorted(self._active_plans))

    def plan_by_uid(self,uid:str)->RegionalRoutePlan|None:
        return self._active_plans.get(str(uid)) or self._cache.get(str(uid)) or self.read_prepared(str(uid))

    def _ensure_infrastructure(self,plan:RegionalRoutePlan)->RouteInfrastructureState:
        infra=self.state.route_infrastructure.get(plan.uid)
        crossing_ids=[str(x.get("uid","")) for x in plan.crossings if x.get("uid")]
        if infra is None:
            infra=RouteInfrastructureState(plan.uid,crossing_conditions={uid:100 for uid in crossing_ids})
            self.state.route_infrastructure[plan.uid]=infra
        else:
            for uid in crossing_ids:infra.crossing_conditions.setdefault(uid,100)
            if self.version<4:
                infra.blocked_crossings=[uid for uid in infra.blocked_crossings if uid in infra.crossing_conditions]
        infra.condition=max(0,min(100,int(infra.condition)))
        self._refresh_blocked(plan,infra,int(getattr(self.state,"clock_minute",0)))
        return infra

    def _effective_regions(self,plan:RegionalRoutePlan)->list[tuple[int,int]]:
        infra=self.state.route_infrastructure.get(plan.uid)
        if self.version>=4 and infra and infra.detour_regions:
            try:return [self._parse_region(x) for x in infra.detour_regions]
            except (TypeError,ValueError):pass
        return list(plan.region_path)

    def _effective_portals(self,plan:RegionalRoutePlan)->list[dict]:
        infra=self.state.route_infrastructure.get(plan.uid)
        return list(infra.detour_portals) if self.version>=4 and infra and infra.detour_regions and infra.detour_portals else list(plan.portals)

    def _effective_crossings(self,plan:RegionalRoutePlan)->list[dict]:
        infra=self.state.route_infrastructure.get(plan.uid)
        return list(infra.detour_crossings) if self.version>=4 and infra and infra.detour_regions else list(plan.crossings)

    def _effective_condition(self,infra:RouteInfrastructureState)->int:
        if self.version>=4 and infra.detour_regions and infra.condition<45:return 45
        return max(0,min(100,int(infra.condition)))

    def _hard_blocked_crossings(self,infra:RouteInfrastructureState,minute:int)->set[str]:
        blocked=set(str(x) for x in infra.blocked_crossings)
        for uid,until in list(infra.temporary_crossing_closures.items()):
            if int(until)>int(minute):blocked.add(str(uid))
            else:infra.temporary_crossing_closures.pop(uid,None)
        return blocked

    def _refresh_blocked(self,plan:RegionalRoutePlan,infra:RouteInfrastructureState,minute:int)->None:
        hard=self._hard_blocked_crossings(infra,minute)
        route_failure=infra.condition<=10 or int(infra.closed_until_minute)>int(minute)
        infra.blocked=bool(route_failure or (hard and not infra.detour_regions))

    def _legacy_crossings(self,regions)->list[dict]:
        out=[];opposite={"north":"south","south":"north","east":"west","west":"east"}
        for a,b in zip(regions,regions[1:]):
            direction=self._direction(a,b);plan=self.region_planner.plan(*a,persist=True)
            water=next((w for w in plan.waters if w.direction==direction),None)
            if water is None:
                mate=self.region_planner.plan(*b,persist=True)
                water=next((w for w in mate.waters if w.direction==opposite[direction]),None)
            if water is None or water.water_kind=="ocean":continue
            kind="ford" if int(water.river_class)<=1 else ("bridge_candidate" if int(water.river_class)<=3 else "ferry_candidate")
            out.append({"from_region":[a[0],a[1]],"to_region":[b[0],b[1]],"kind":kind,
                        "river_class":int(water.river_class),"offset":int(water.offset)})
        return out

    def _build_plan(self,a,b)->RegionalRoutePlan:
        if self.version<3:
            uid=self._edge_uid(a.uid,b.uid);cached=self.read_prepared(uid)
            if cached is not None:return cached
            regions=self._region_path((a.region_x,a.region_y),(b.region_x,b.region_y))
            cost=sum(self._region_cost(*r) for r in regions[1:]);crossings=self._legacy_crossings(regions)
            danger=min(95,max(0,cost//max(1,len(regions))//4+len(crossings)*4))
            route_class="maintained_road" if max(a.population,b.population)>=150 else ("road" if a.population+b.population>=80 else "trail")
            payload={"uid":uid,"version":self.version,"origin":min(a.uid,b.uid),"destination":max(a.uid,b.uid),
                     "region_path":regions,"chunk_corridor":self._chunk_corridor(a,b,regions),"crossings":crossings,
                     "route_class":route_class,"cost":int(cost),"danger":int(danger)}
            plan=RegionalRoutePlan(**payload,fingerprint=canonical_hash(payload));self._cache[uid]=plan;return plan

        if a.uid>b.uid:a,b=b,a
        uid=self._edge_uid(a.uid,b.uid);cached=self.read_prepared(uid)
        if cached is not None:
            self._ensure_infrastructure(cached);return cached
        regions=self._region_path((a.region_x,a.region_y),(b.region_x,b.region_y))
        portals,crossings=self._portals_and_crossings(uid,regions)
        cost=sum(self._region_cost(*r) for r in regions[1:])
        danger=min(95,max(0,cost//max(1,len(regions))//4+len(crossings)*4))
        route_class="maintained_road" if max(a.population,b.population)>=150 else ("road" if a.population+b.population>=80 else "trail")
        payload={"uid":uid,"version":self.version,"origin":a.uid,"destination":b.uid,
                 "region_path":regions,"chunk_corridor":self._chunk_corridor(a,b,regions),
                 "portals":portals,"crossings":crossings,"route_class":route_class,
                 "cost":int(cost),"danger":int(danger)}
        plan=RegionalRoutePlan(**payload,fingerprint=canonical_hash(payload))
        self._cache[uid]=plan;self._ensure_infrastructure(plan);return plan

    def _candidate_edges(self,settlements):
        rows=sorted(settlements,key=lambda s:s.uid)
        if self.version<3:
            candidates={}
            for a in rows:
                nearby=sorted((b for b in rows if b.uid!=a.uid),
                              key=lambda b:(abs(a.region_x-b.region_x)+abs(a.region_y-b.region_y),
                                            (a.region_x-b.region_x)**2+(a.region_y-b.region_y)**2,b.uid))[:3]
                for b in nearby:
                    lo,hi=sorted((a.uid,b.uid))
                    if (lo,hi) in candidates:continue
                    pa=self.region_planner.plan(a.region_x,a.region_y,persist=True)
                    pb=self.region_planner.plan(b.region_x,b.region_y,persist=True)
                    distance=abs(a.region_x-b.region_x)+abs(a.region_y-b.region_y)
                    utility=int(getattr(pa,"route_value",0))+int(getattr(pb,"route_value",0))
                    utility+=min(60,a.population+b.population)//2
                    candidates[(lo,hi)]=(distance*100-utility,lo,hi,a,b)
            return sorted(candidates.values(),key=lambda row:(row[0],row[1],row[2]))

        by_region={}
        for row in rows:by_region.setdefault((int(row.region_x),int(row.region_y)),[]).append(row)
        out={}
        for a in rows:
            nearby=[]
            for dy in range(-12,13):
                for dx in range(-12,13):
                    for b in by_region.get((int(a.region_x)+dx,int(a.region_y)+dy),()):
                        if b.uid==a.uid:continue
                        rough=abs(dx)+abs(dy)
                        if rough<=12:nearby.append((rough,b.uid,b))
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
        if self.version<3:
            minutes=max(180,int(plan.cost)*5)
            capacity=160 if plan.route_class=="maintained_road" else 100 if plan.route_class=="road" else 55
            for origin,destination,path,chunks,suffix in (
                (a,b,plan.region_path,plan.chunk_corridor,"a"),
                (b,a,list(reversed(plan.region_path)),list(reversed(plan.chunk_corridor)),"b")):
                uid=f"{plan.uid}:{suffix}";old=self.state.trade_routes.get(uid)
                self.state.trade_routes[uid]=TradeRouteState(
                    uid,origin.uid,destination.uid,max(1,len(path)-1),int(plan.danger),capacity,
                    int(old.last_used_minute) if old else 0,int(old.traffic) if old else 0,
                    [f"{rx},{ry}" for rx,ry in path],minutes,[f"{cx},{cy}" for cx,cy in chunks])
            return

        infra=self._ensure_infrastructure(plan)
        by_uid={s.uid:s for s in self.state.settlements.values()}
        canonical_a=by_uid.get(plan.origin,a);canonical_b=by_uid.get(plan.destination,b)
        if self.version==3:
            path=list(plan.region_path);chunks=list(plan.chunk_corridor)
            condition=max(10,int(infra.condition));minutes=max(180,int(plan.cost)*5)*100//condition
            class_capacity=160 if plan.route_class=="maintained_road" else 100 if plan.route_class=="road" else 55
            capacity=0 if infra.blocked else max(1,class_capacity*condition//100)
            danger=min(100,int(plan.danger)+(100-condition)//3+(35 if infra.blocked else 0))
            toll=0;patrol=0;contested=False
        else:
            path=self._effective_regions(plan);chunks=self._chunk_corridor(canonical_a,canonical_b,path)
            condition=max(10,self._effective_condition(infra))
            base_cost=sum(self._region_cost(*r) for r in path[1:]) or int(plan.cost)
            minutes=max(180,base_cost*5)*100//condition
            class_capacity=160 if plan.route_class=="maintained_road" else 100 if plan.route_class=="road" else 55
            capacity=0 if infra.blocked else max(1,class_capacity*condition//100)
            patrol=max(0,min(100,int(infra.patrol_strength)))
            contested=bool(infra.contested)
            danger=min(100,max(0,int(plan.danger)+(100-condition)//3+int(infra.hazard_level)//4+
                               (35 if infra.blocked else 0)+(20 if contested else 0)-patrol//5))
            toll=max(0,int(infra.toll_copper))
        for origin,destination,rpath,rchunks,suffix in (
            (canonical_a,canonical_b,path,chunks,"a"),
            (canonical_b,canonical_a,list(reversed(path)),list(reversed(chunks)),"b")):
            uid=f"{plan.uid}:{suffix}";old=self.state.trade_routes.get(uid)
            self.state.trade_routes[uid]=TradeRouteState(
                uid,origin.uid,destination.uid,max(1,len(rpath)-1),danger,capacity,
                int(old.last_used_minute) if old else 0,int(old.traffic) if old else 0,
                [f"{rx},{ry}" for rx,ry in rpath],minutes,[f"{cx},{cy}" for cx,cy in rchunks],
                plan.uid,toll,patrol,contested)

    def refresh_trade_route(self,plan_or_uid)->None:
        plan=plan_or_uid if isinstance(plan_or_uid,RegionalRoutePlan) else self.plan_by_uid(str(plan_or_uid))
        if plan is None:return
        a=self.state.settlements.get(plan.origin);b=self.state.settlements.get(plan.destination)
        if a is not None and b is not None:self._mirror_trade_route(plan,a,b)

    def _persist(self,plans:Iterable[RegionalRoutePlan],persist:bool)->None:
        if not persist:return
        storer=getattr(self.cache_source,"store_generated_route_plan",None)
        if callable(storer):
            for plan in plans:storer(plan.uid,self.version,plan.to_dict())
        commit=getattr(self.cache_source,"commit_generated",None)
        if callable(commit):commit()

    def _sync_rows(self,rows,*,persist:bool,cleanup:bool)->tuple[RegionalRoutePlan,...]:
        rows=sorted(rows,key=lambda s:s.uid)
        if self.version<4:
            plans=[];settlement_by_uid={s.uid:s for s in rows}
            for _,_,_,a,b in self._select_sparse_edges(rows):
                plan=self._build_plan(a,b);plans.append(plan);self._mirror_trade_route(plan,a,b)
            self._persist(plans,persist)
            if cleanup:
                valid={p.uid for p in plans}
                for uid,route in list(self.state.trade_routes.items()):
                    if route.physical_route_id and route.physical_route_id not in valid:self.state.trade_routes.pop(uid,None)
            self._active_plans={p.uid:p for p in plans}
            self._update_centrality_and_hinterlands(settlement_by_uid,plans)
            return tuple(sorted(plans,key=lambda p:p.uid))

        plans=[self._build_plan(a,b) for _,_,_,a,b in self._select_sparse_edges(rows)]
        self._active_plans={p.uid:p for p in plans}
        settlement_by_uid={s.uid:s for s in rows}
        for plan in plans:
            self._maybe_restore_base(plan,int(getattr(self.state,"clock_minute",0)))
        self._update_centrality_and_hinterlands(settlement_by_uid,plans)
        self._update_border_posts(plans,int(getattr(self.state,"clock_minute",0)))
        for plan in plans:
            a=settlement_by_uid.get(plan.origin);b=settlement_by_uid.get(plan.destination)
            if a is not None and b is not None:self._mirror_trade_route(plan,a,b)
        self._persist(plans,persist)
        if cleanup:
            valid={p.uid for p in plans}
            for uid,route in list(self.state.trade_routes.items()):
                if route.physical_route_id and route.physical_route_id not in valid:self.state.trade_routes.pop(uid,None)
            for post in self.state.border_posts.values():
                if post.route_id not in valid:post.active=False
        return tuple(sorted(plans,key=lambda p:p.uid))

    def sync(self,settlements,center_region:tuple[int,int],radius:int=2,*,persist:bool=True)->tuple[RegionalRoutePlan,...]:
        if self.version<2:return ()
        rx,ry=map(int,center_region)
        selected=sorted((s for s in settlements if abs(int(s.region_x)-rx)<=radius and abs(int(s.region_y)-ry)<=radius),key=lambda s:s.uid)[:32]
        return self._sync_rows(selected,persist=persist,cleanup=False)

    def sync_network(self,settlements,*,persist:bool=True)->tuple[RegionalRoutePlan,...]:
        if self.version<3:return ()
        return self._sync_rows(sorted(settlements,key=lambda s:s.uid),persist=persist,cleanup=True)

    def _blocked_edges(self,plan:RegionalRoutePlan,minute:int)->set[tuple[tuple[int,int],tuple[int,int]]]:
        infra=self._ensure_infrastructure(plan);blocked_ids=self._hard_blocked_crossings(infra,minute)
        out=set()
        for crossing in self._effective_crossings(plan)+list(plan.crossings):
            if str(crossing.get("uid","")) not in blocked_ids:continue
            try:
                a=tuple(map(int,crossing["from_region"]));b=tuple(map(int,crossing["to_region"]))
                out.add(self._transition(a,b))
            except (KeyError,TypeError,ValueError):continue
        return out

    def _reroute_route(self,plan:RegionalRoutePlan,minute:int,reason:str)->bool:
        if self.version<4:return False
        infra=self._ensure_infrastructure(plan)
        start,goal=plan.region_path[0],plan.region_path[-1]
        blocked_edges=self._blocked_edges(plan,minute)
        hazard_regions=set()
        for token in getattr(infra,"hazard_regions",[]):
            try:hazard_regions.add(self._parse_region(token))
            except (TypeError,ValueError):pass
        if infra.condition<=10 and not hazard_regions and len(plan.region_path)>2:
            hazard_regions.add(plan.region_path[len(plan.region_path)//2])
        candidate=self._region_path_dynamic(start,goal,blocked_edges,hazard_regions,pad=5,fallback=False)
        if not candidate or candidate==plan.region_path:
            infra.detour_regions=[];infra.detour_portals=[];infra.detour_crossings=[]
            self._refresh_blocked(plan,infra,minute);return False
        portals,crossings=self._portals_and_crossings(plan.uid,candidate)
        infra.detour_regions=[self._region_token(r) for r in candidate]
        infra.detour_portals=[dict(x) for x in portals]
        infra.detour_crossings=[dict(x) for x in crossings]
        for crossing in crossings:
            uid=str(crossing.get("uid",""))
            if uid:infra.crossing_conditions.setdefault(uid,100)
        infra.detour_updated_minute=int(minute);infra.reroute_count+=1
        infra.hazard_reason=str(reason or infra.hazard_reason)
        infra.blocked=False
        self._material_cache.clear()
        return True

    def _maybe_restore_base(self,plan:RegionalRoutePlan,minute:int)->bool:
        if self.version<4:return False
        infra=self._ensure_infrastructure(plan)
        if not infra.detour_regions:return False
        blocked=self._blocked_edges(plan,minute)
        if blocked or infra.condition<=25 or int(infra.closed_until_minute)>minute or int(infra.hazard_level)>=60:
            return False
        infra.detour_regions=[];infra.detour_portals=[];infra.detour_crossings=[]
        infra.hazard_reason="";infra.hazard_level=max(0,infra.hazard_level-20)
        self._refresh_blocked(plan,infra,minute);self._material_cache.clear();return True

    def links_for_settlement(self,settlement_id:str)->tuple[dict,...]:
        settlement_id=str(settlement_id);out=[]
        for plan in sorted(self._active_plans.values(),key=lambda p:p.uid):
            regions=self._effective_regions(plan);portals=self._effective_portals(plan)
            if len(regions)<2 or not portals:continue
            if plan.origin==settlement_id:
                portal=portals[0]
                out.append({"route_id":plan.uid,"direction":str(portal["direction"]),
                            "portal_cell":tuple(map(int,portal["from_cell"])),"road_class":plan.route_class,
                            "crossing_id":str(portal.get("crossing_id",""))})
            elif plan.destination==settlement_id:
                portal=portals[-1];dest=regions[-1];prev=regions[-2]
                out.append({"route_id":plan.uid,"direction":self._direction(dest,prev),
                            "portal_cell":tuple(map(int,portal["to_cell"])),"road_class":plan.route_class,
                            "crossing_id":str(portal.get("crossing_id",""))})
        return tuple(out)

    @staticmethod
    def _gateway_for_route(skeleton,route_id:str,toward:tuple[int,int])->tuple[int,int]:
        routed=[r for r in skeleton.roads if str(getattr(r,"route_id",""))==str(route_id) and r.polyline]
        if routed:return min((tuple(r.polyline[-1]) for r in routed),key=lambda p:abs(p[0]-toward[0])+abs(p[1]-toward[1]))
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

    def _local_path(self,start:tuple[int,int],goal:tuple[int,int],region:tuple[int,int],avoid:set[tuple[int,int]]|None=None)->list[tuple[int,int]]:
        if start==goal:return [start]
        avoid=avoid or set();rx,ry=region;x0,y0=rx*REGION_SIZE,ry*REGION_SIZE;margin=72
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
                nx,ny=x+dx,y+dy;nxt=(nx,ny)
                if not(left<=nx<=right and top<=ny<=bottom) or (nxt in avoid and nxt not in {start,goal}):continue
                nc=cost+self._local_cost(nx,ny)
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

    def _post_for_crossing(self,route_id:str,x:int,y:int):
        posts=[p for p in self.state.border_posts.values() if p.active and p.route_id==route_id]
        return min(posts,key=lambda p:abs(p.x-x)+abs(p.y-y)) if posts else None

    def _physical_crossings(self,route_id:str,region:tuple[int,int],path:list[tuple[int,int]],known:list[dict])->list[CrossingPlan]:
        known_by_cell={(int(c.get("x",0)),int(c.get("y",0))):c for c in known}
        runs=[];start=None
        for index,cell in enumerate(path):
            env=self.world.environment_at(WorldPos(cell[0],cell[1],0))
            if env is not None and env.open_water:
                if start is None:start=index
            elif start is not None:
                runs.append((start,index-1));start=None
        if start is not None:runs.append((start,len(path)-1))
        out=[]
        for seq,(aidx,bidx) in enumerate(runs):
            cells=list(path[aidx:bidx+1]);mid=cells[len(cells)//2]
            nearby=min(known_by_cell,key=lambda p:abs(p[0]-mid[0])+abs(p[1]-mid[1])) if known_by_cell else None
            known_row=known_by_cell.get(nearby) if nearby is not None and abs(nearby[0]-mid[0])+abs(nearby[1]-mid[1])<=3 else None
            if known_row:
                uid=str(known_row["uid"]);kind=str(known_row["kind"]);river_class=int(known_row.get("river_class",1))
            else:
                kind="ford" if len(cells)<=2 else ("bridge" if len(cells)<=5 else "ferry")
                river_class=min(5,max(1,(len(cells)+1)//2))
                uid=stable_plan_uid("crossing",route_id,f"local:{region[0]},{region[1]}:{seq}:{kind}",cells)
            landing_a=path[aidx-1] if aidx>0 else cells[0]
            landing_b=path[bidx+1] if bidx+1<len(path) else cells[-1]
            infra=self.state.route_infrastructure.get(route_id)
            condition=int(infra.crossing_conditions.get(uid,100)) if infra else 100
            blocked=bool(infra and (uid in self._hard_blocked_crossings(infra,int(getattr(self.state,"clock_minute",0))) or condition<=10))
            post=self._post_for_crossing(route_id,mid[0],mid[1])
            out.append(CrossingPlan(
                uid,route_id,mid[0],mid[1],kind,river_class,condition,blocked,
                list(cells),tuple(landing_a),tuple(landing_b),
                post.controlling_faction_id if post else "",
                int(post.toll_copper) if post else 0,
                int(post.patrol_strength) if post else 0,
            ))

        existing={c.uid for c in out}
        for row in known:
            uid=str(row.get("uid",""))
            if not uid or uid in existing:continue
            try:
                x,y=int(row["x"]),int(row["y"])
                if x//REGION_SIZE!=region[0] or y//REGION_SIZE!=region[1]:continue
            except (KeyError,TypeError,ValueError):continue
            portal=next((p for p in self._effective_portals(self.plan_by_uid(route_id)) if str(p.get("crossing_id",""))==uid),None) if self.plan_by_uid(route_id) else None
            if portal is None:continue
            la=tuple(map(int,portal["from_cell"]));lb=tuple(map(int,portal["to_cell"]))
            infra=self.state.route_infrastructure.get(route_id);condition=int(infra.crossing_conditions.get(uid,100)) if infra else 100
            blocked=bool(infra and (uid in self._hard_blocked_crossings(infra,int(getattr(self.state,"clock_minute",0))) or condition<=10))
            post=self._post_for_crossing(route_id,x,y)
            out.append(CrossingPlan(
                uid,route_id,x,y,str(row.get("kind","ford")),int(row.get("river_class",1)),condition,blocked,
                [(x,y)],la,lb,post.controlling_faction_id if post else "",
                int(post.toll_copper) if post else 0,int(post.patrol_strength) if post else 0,
            ))
        return out

    def materialize_region(self,region:tuple[int,int],skeletons:dict[str,object])->tuple[tuple[RoadSegmentPlan,...],tuple[CrossingPlan,...]]:
        if self.version<3:return (),()
        rx,ry=map(int,region);roads=[];crossings=[]
        for plan in sorted(self._active_plans.values(),key=lambda p:p.uid):
            regions=self._effective_regions(plan);portals=self._effective_portals(plan);known=self._effective_crossings(plan)
            try:index=regions.index((rx,ry))
            except ValueError:continue
            if len(regions)<2 or not portals:continue
            if index==0:
                portal=portals[0];skeleton=skeletons.get(plan.origin)
                start=self._gateway_for_route(skeleton,plan.uid,tuple(portal["from_cell"])) if skeleton is not None else tuple(portal["from_cell"])
            else:start=tuple(map(int,portals[index-1]["to_cell"]))
            if index==len(regions)-1:
                portal=portals[-1];skeleton=skeletons.get(plan.destination)
                goal=self._gateway_for_route(skeleton,plan.uid,tuple(portal["to_cell"])) if skeleton is not None else tuple(portal["to_cell"])
            else:goal=tuple(map(int,portals[index]["from_cell"]))
            infra=self._ensure_infrastructure(plan)
            avoid=set()
            if self.version>=4:
                blocked_ids=self._hard_blocked_crossings(infra,int(getattr(self.state,"clock_minute",0)))
                for cid in blocked_ids:
                    loc=infra.crossing_locations.get(cid)
                    if loc and len(loc)>=2 and int(loc[0])//REGION_SIZE==rx and int(loc[1])//REGION_SIZE==ry:
                        cx,cy=int(loc[0]),int(loc[1])
                        avoid.update((cx+dx,cy+dy) for dx,dy in CARDINALS)
                        avoid.add((cx,cy))
            cache_key=(plan.uid,rx,ry,start,goal,int(infra.reroute_count),tuple(sorted(avoid)))
            cached=self._material_cache.get(cache_key)
            if cached is None:
                path=self._local_path(start,goal,(rx,ry),avoid)
                if len(path)<2:continue
                local_crossings=self._physical_crossings(plan.uid,(rx,ry),path,known)
                self._material_cache[cache_key]=(path,local_crossings)
            else:path,local_crossings=cached
            crossing_ids=[c.uid for c in local_crossings]
            for crossing in local_crossings:
                infra.crossing_conditions.setdefault(crossing.uid,100)
                infra.crossing_locations[crossing.uid]=[int(crossing.x),int(crossing.y)]
            self._refresh_blocked(plan,infra,int(getattr(self.state,"clock_minute",0)))
            uid=stable_plan_uid("regional-road-segment",plan.uid,f"{rx},{ry}",path)
            roads.append(RoadSegmentPlan(
                uid=uid,route_id=plan.uid,road_class=plan.route_class,polyline=list(path),
                chunk_corridor=self._chunk_path(path),width=2 if plan.route_class=="maintained_road" else 1,
                surface="stone" if plan.route_class=="maintained_road" else "earth",
                condition=self._effective_condition(infra),traffic=int(infra.traffic),
                crossing_ids=crossing_ids,blocked=bool(infra.blocked),
                last_maintenance_minute=int(infra.last_maintenance_minute)))
            crossings.extend(local_crossings)
        return tuple(roads),tuple(crossings)

    def crossing_condition(self,route_id:str,crossing_id:str)->int:
        infra=self.state.route_infrastructure.get(str(route_id))
        return int(infra.crossing_conditions.get(str(crossing_id),100)) if infra else 100

    def crossing_blocked(self,route_id:str,crossing_id:str,minute:int|None=None)->bool:
        infra=self.state.route_infrastructure.get(str(route_id))
        if infra is None:return False
        minute=int(getattr(self.state,"clock_minute",0) if minute is None else minute)
        return str(crossing_id) in self._hard_blocked_crossings(infra,minute) or self.crossing_condition(route_id,crossing_id)<=10

    def record_usage(self,route_id:str,minute:int,amount:int=1)->None:
        plan=self.plan_by_uid(route_id)
        if plan is None:return
        infra=self._ensure_infrastructure(plan)
        before=int(infra.traffic);infra.traffic=max(0,before+max(1,int(amount)));infra.last_used_minute=int(minute)
        wear=infra.traffic//8-before//8
        if wear>0:infra.condition=max(0,infra.condition-wear)
        self._refresh_blocked(plan,infra,minute)

    def damage_route(self,route_id:str,amount:int,*,crossing_id:str="",minute:int=0,reason:str="damage",region:tuple[int,int]|None=None)->bool:
        plan=self.plan_by_uid(route_id)
        if plan is None:return False
        infra=self._ensure_infrastructure(plan);amount=max(0,int(amount));changed=False
        if region is not None and self.version>=4:
            token=self._region_token(region)
            if not hasattr(infra,"hazard_regions"):setattr(infra,"hazard_regions",[])
            if token not in infra.hazard_regions:infra.hazard_regions.append(token)
        infra.hazard_level=min(100,max(int(infra.hazard_level),amount*4))
        infra.hazard_reason=str(reason)
        if crossing_id:
            crossing_id=str(crossing_id);infra.crossing_conditions.setdefault(crossing_id,100)
            old=infra.crossing_conditions[crossing_id]
            infra.crossing_conditions[crossing_id]=max(0,old-amount);changed=infra.crossing_conditions[crossing_id]!=old
            if infra.crossing_conditions[crossing_id]<=10 and crossing_id not in infra.blocked_crossings:
                infra.blocked_crossings.append(crossing_id);changed=True
        else:
            old=infra.condition;infra.condition=max(0,infra.condition-amount);changed=infra.condition!=old
        if self.version>=4 and changed:
            self._reroute_route(plan,int(minute),reason)
        self._refresh_blocked(plan,infra,int(minute));self._material_cache.clear()
        if changed:self.refresh_trade_route(plan)
        return changed

    def repair_route(self,route_id:str,amount:int,minute:int,*,crossing_id:str="")->None:
        plan=self.plan_by_uid(route_id)
        if plan is None:return
        infra=self._ensure_infrastructure(plan);amount=max(0,int(amount))
        if crossing_id:
            crossing_id=str(crossing_id);infra.crossing_conditions.setdefault(crossing_id,100)
            infra.crossing_conditions[crossing_id]=min(100,infra.crossing_conditions[crossing_id]+amount)
            if infra.crossing_conditions[crossing_id]>10:
                infra.blocked_crossings=[x for x in infra.blocked_crossings if x!=crossing_id]
                infra.temporary_crossing_closures.pop(crossing_id,None)
        else:infra.condition=min(100,infra.condition+amount)
        infra.last_maintenance_minute=int(minute);infra.hazard_level=max(0,infra.hazard_level-amount*2)
        if infra.condition>25 and not infra.blocked_crossings:infra.hazard_reason=""
        self._maybe_restore_base(plan,int(minute));self._refresh_blocked(plan,infra,int(minute));self._material_cache.clear();self.refresh_trade_route(plan)

    def close_crossing_temporarily(self,route_id:str,crossing_id:str,until_minute:int,reason:str)->bool:
        plan=self.plan_by_uid(route_id)
        if plan is None:return False
        infra=self._ensure_infrastructure(plan);cid=str(crossing_id)
        infra.temporary_crossing_closures[cid]=max(int(until_minute),int(infra.temporary_crossing_closures.get(cid,0)))
        infra.hazard_reason=str(reason);infra.hazard_level=max(infra.hazard_level,35)
        changed=self._reroute_route(plan,int(getattr(self.state,"clock_minute",0)),reason)
        self._refresh_blocked(plan,infra,int(getattr(self.state,"clock_minute",0)));self._material_cache.clear()
        return changed

    def apply_region_hazard(self,region:tuple[int,int],kind:str,severity:int,minute:int)->tuple[str,...]:
        if self.version<4:return ()
        affected=[];severity=max(1,min(100,int(severity)))
        for plan in self.active_plans():
            if region not in set(self._effective_regions(plan))|set(plan.region_path):continue
            crossing=next((c for c in self._effective_crossings(plan)
                           if tuple(c.get("from_region",()))==region or tuple(c.get("to_region",()))==region),None)
            if crossing and kind in {"flood","fire","war"}:
                scale=3 if str(crossing.get("kind",""))=="bridge" and kind=="fire" else 2
                self.damage_route(plan.uid,max(2,severity//scale),crossing_id=str(crossing.get("uid","")),
                                  minute=minute,reason=kind,region=region)
            else:
                self.damage_route(plan.uid,max(1,severity//8),minute=minute,reason=kind,region=region)
            affected.append(plan.uid)
        return tuple(sorted(set(affected)))

    def apply_war_damage(self,faction_a:str,faction_b:str,minute:int,severity:int=35)->tuple[str,...]:
        if self.version<4:return ()
        candidates=[]
        for plan in self.active_plans():
            a=self.state.settlements.get(plan.origin);b=self.state.settlements.get(plan.destination)
            endpoint_factions={getattr(a,"faction_id",""),getattr(b,"faction_id","")}
            posts=[p for p in self.state.border_posts.values() if p.active and p.route_id==plan.uid]
            post_factions={p.controlling_faction_id for p in posts}|{p.rival_faction_id for p in posts}
            if {faction_a,faction_b}.issubset(endpoint_factions|post_factions):
                candidates.append(plan)
        if not candidates:return ()
        candidates.sort(key=lambda p:(-int(self.state.route_infrastructure.get(p.uid,RouteInfrastructureState(p.uid)).contested),p.uid))
        plan=candidates[int(hash_u64(self.seed,"war-route-damage",faction_a,faction_b,minute//(30*1440))%len(candidates))]
        crossings=self._effective_crossings(plan)
        if crossings and hash_u64(self.seed,"war-crossing",plan.uid,minute)%100<55:
            crossing=crossings[int(hash_u64(self.seed,"war-crossing-pick",plan.uid,minute)%len(crossings))]
            region=tuple(map(int,crossing.get("from_region",plan.region_path[0])))
            self.damage_route(plan.uid,max(8,int(severity)),crossing_id=str(crossing.get("uid","")),
                              minute=minute,reason="war",region=region)
        else:
            regions=self._effective_regions(plan);region=regions[len(regions)//2]
            self.damage_route(plan.uid,max(4,int(severity)//2),minute=minute,reason="war",region=region)
        return (plan.uid,)

    def hourly_hazard_update(self,minute:int,environment)->tuple[str,...]:
        if self.version<4:return ()
        hour=int(minute)//60;affected=[]
        fire_cells=[(int(f.x),int(f.y),int(f.intensity)) for f in self.state.fires.values() if int(f.z)==0 and int(f.intensity)>0]
        material_by_route={}
        for key,(path,_) in self._material_cache.items():
            if not key:continue
            route_id=str(key[0]);material_by_route.setdefault(route_id,set()).update(path)
        for plan in self.active_plans():
            infra=self._ensure_infrastructure(plan)
            if infra.last_hazard_hour==hour:continue
            infra.last_hazard_hour=hour
            changed=False
            for crossing in self._effective_crossings(plan):
                uid=str(crossing.get("uid",""))
                if not uid:continue
                x,y=int(crossing.get("x",0)),int(crossing.get("y",0))
                weather=environment.weather.at(minute,x,y)
                env=self.world.environment_at(WorldPos(x,y,0))
                rain=int(weather.get("rain",0) or 0);storm=int(weather.get("storm_intensity",0) or 0)
                flood=int(getattr(env,"flood_risk",0) or 0) if env is not None else 0
                kind=str(crossing.get("kind","ford"))
                token=int(hash_u64(self.seed,"route-weather",plan.uid,uid,hour)%100)
                if kind=="ferry" and storm>=55:
                    infra.temporary_crossing_closures[uid]=max(infra.temporary_crossing_closures.get(uid,0),minute+60+storm)
                    infra.hazard_reason="storm";infra.hazard_level=max(infra.hazard_level,storm);changed=True
                elif kind=="ford" and rain>=7 and flood>=35 and token<min(90,flood+rain*4):
                    infra.temporary_crossing_closures[uid]=max(infra.temporary_crossing_closures.get(uid,0),minute+60+rain*12)
                    infra.hazard_reason="flood";infra.hazard_level=max(infra.hazard_level,min(100,flood+rain*3));changed=True
                elif kind=="bridge" and rain>=7 and flood>=45 and token<min(80,flood):
                    self.damage_route(plan.uid,max(1,(rain+flood//10)//3),crossing_id=uid,
                                      minute=minute,reason="flood",region=(x//REGION_SIZE,y//REGION_SIZE));changed=True
                if kind in {"bridge","ferry"}:
                    burning=max((intensity for fx,fy,intensity in fire_cells if abs(fx-x)+abs(fy-y)<=2),default=0)
                    if burning:
                        self.damage_route(plan.uid,max(1,burning//18),crossing_id=uid,
                                          minute=minute,reason="fire",region=(x//REGION_SIZE,y//REGION_SIZE));changed=True
            route_cells=material_by_route.get(plan.uid,set())
            if route_cells and fire_cells:
                burning=max((intensity for fx,fy,intensity in fire_cells if (fx,fy) in route_cells),default=0)
                if burning:
                    region=next(((fx//REGION_SIZE,fy//REGION_SIZE) for fx,fy,intensity in fire_cells if intensity==burning and (fx,fy) in route_cells),None)
                    self.damage_route(plan.uid,max(1,burning//30),minute=minute,reason="fire",region=region);changed=True
            self._hard_blocked_crossings(infra,minute)
            if changed:
                self._reroute_route(plan,minute,infra.hazard_reason or "hazard");affected.append(plan.uid)
            elif infra.detour_regions:self._maybe_restore_base(plan,minute)
            infra.hazard_level=max(0,infra.hazard_level-1)
            self._refresh_blocked(plan,infra,minute)
            if changed:self.refresh_trade_route(plan)
        return tuple(sorted(set(affected)))

    def _region_control(self,region:tuple[int,int])->tuple[str,int,str,int]:
        token=self._region_token(region);rows=[]
        for faction in self.state.factions.values():
            score=int(faction.influence_regions.get(token,0))
            if score>0:rows.append((score,int(getattr(faction,"prominence",0)),faction.uid))
        rows.sort(reverse=True)
        if not rows:return "",0,"",0
        first=rows[0];second=rows[1] if len(rows)>1 else (0,0,"")
        return first[2],first[0],second[2],second[0]

    def _update_border_posts(self,plans:list[RegionalRoutePlan],minute:int)->None:
        if self.version<4:return
        valid=set()
        for plan in plans:
            infra=self._ensure_infrastructure(plan);regions=self._effective_regions(plan);portals=self._effective_portals(plan)
            route_posts=[]
            for index,(a,b) in enumerate(zip(regions,regions[1:])):
                if index>=len(portals):break
                fa,sa,ra,rsa=self._region_control(a);fb,sb,rb,rsb=self._region_control(b)
                if not fa and not fb:continue
                if fa==fb and fa:continue
                if fa and fb:
                    controller,control_score,rival,rival_score=(fa,sa,fb,sb) if sa>=sb else (fb,sb,fa,sa)
                elif fa:controller,control_score,rival,rival_score=fa,sa,"",0
                else:controller,control_score,rival,rival_score=fb,sb,"",0
                faction=self.state.factions.get(controller)
                if faction is None or control_score<35:continue
                war=bool(rival and rival in faction.at_war)
                contested=bool(rival and (war or abs(control_score-rival_score)<=18))
                portal=portals[index]
                cell=tuple(map(int,portal["from_cell"] if controller==fa else portal["to_cell"]))
                pair=self._transition(a,b)
                uid=stable_plan_uid("border-post",plan.uid,f"{pair[0][0]},{pair[0][1]}>{pair[1][0]},{pair[1][1]}",[cell])
                toll=max(1,1+int(getattr(faction,"toll_policy",50))//30+(1 if plan.route_class=="maintained_road" else 0))
                if contested:toll+=1
                patrol=min(100,max(5,int(faction.power)//4+int(faction.prominence)//6+(18 if war else 0)+(10 if contested else 0)))
                post=self.state.border_posts.get(uid)
                if post is None:
                    post=BorderPostState(uid,plan.uid,cell[0],cell[1],cell[0]//REGION_SIZE,cell[1]//REGION_SIZE)
                    self.state.border_posts[uid]=post
                post.route_id=plan.uid;post.x,post.y=cell;post.region_x,post.region_y=cell[0]//REGION_SIZE,cell[1]//REGION_SIZE
                post.controlling_faction_id=controller;post.rival_faction_id=rival;post.toll_copper=toll
                post.patrol_strength=patrol;post.contested=contested;post.active=True;post.last_update_minute=int(minute)
                valid.add(uid);route_posts.append(post)
            infra.toll_copper=sum(p.toll_copper for p in route_posts)
            infra.patrol_strength=max((p.patrol_strength for p in route_posts),default=0)
            infra.contested=any(p.contested for p in route_posts)
            controllers={p.controlling_faction_id for p in route_posts if p.controlling_faction_id}
            infra.control_faction_id=next(iter(controllers)) if len(controllers)==1 else ""
        for uid,post in self.state.border_posts.items():
            if uid not in valid:post.active=False

    def border_posts_for_route(self,route_id:str)->tuple[BorderPostState,...]:
        return tuple(sorted((p for p in self.state.border_posts.values() if p.active and p.route_id==str(route_id)),key=lambda p:p.uid))

    def border_post_at(self,pos:WorldPos)->BorderPostState|None:
        return next((p for p in self.state.border_posts.values() if p.active and p.x==pos.x and p.y==pos.y),None)

    def route_toll(self,route_id:str,payer_faction_id:str="")->int:
        total=0
        for post in self.border_posts_for_route(route_id):
            if payer_faction_id and post.controlling_faction_id==payer_faction_id:continue
            total+=max(0,int(post.toll_copper))
        return total

    def crossing_toll(self,route_id:str,x:int,y:int,payer_faction_id:str="")->int:
        posts=self.border_posts_for_route(route_id)
        if not posts:return 0
        post=min(posts,key=lambda p:abs(int(p.x)-int(x))+abs(int(p.y)-int(y)))
        if payer_faction_id and post.controlling_faction_id==payer_faction_id:return 0
        return max(0,int(post.toll_copper)) if abs(post.x-int(x))+abs(post.y-int(y))<=REGION_SIZE else 0

    def collect_crossing_toll(self,route_id:str,x:int,y:int,amount:int,payer_faction_id:str="")->int:
        posts=self.border_posts_for_route(route_id)
        if not posts:return 0
        post=min(posts,key=lambda p:abs(int(p.x)-int(x))+abs(int(p.y)-int(y)))
        if payer_faction_id and post.controlling_faction_id==payer_faction_id:return 0
        due=min(max(0,int(amount)),max(0,int(post.toll_copper)))
        faction=self.state.factions.get(post.controlling_faction_id)
        if faction is not None:faction.treasury+=due
        post.treasury_collected+=due
        return due

    def collect_toll(self,route_id:str,amount:int,payer_faction_id:str="")->int:
        remaining=max(0,int(amount));collected=0
        for post in self.border_posts_for_route(route_id):
            if remaining<=0:break
            if payer_faction_id and post.controlling_faction_id==payer_faction_id:continue
            due=min(remaining,max(0,int(post.toll_copper)))
            faction=self.state.factions.get(post.controlling_faction_id)
            if faction is not None:faction.treasury+=due
            post.treasury_collected+=due;collected+=due;remaining-=due
        return collected

    def patrol_destination_for_settlement(self,settlement_id:str)->WorldPos|None:
        town=self.state.settlements.get(str(settlement_id))
        if town is None:return None
        rows=[]
        for plan in self.active_plans():
            if settlement_id not in {plan.origin,plan.destination}:continue
            for post in self.border_posts_for_route(plan.uid):
                if post.controlling_faction_id==town.faction_id or post.contested:
                    dist=abs(post.x-town.x)+abs(post.y-town.y)
                    rows.append((-post.patrol_strength,dist,post.uid,post))
        if not rows:return None
        post=min(rows,key=lambda row:(row[1],row[0],row[2]))[-1]
        return WorldPos(int(post.x),int(post.y),0)

    def monthly_update(self,minute:int)->None:
        month=int(minute)//(30*1440)
        for plan in sorted(self._active_plans.values(),key=lambda p:p.uid):
            infra=self._ensure_infrastructure(plan)
            if int(infra.last_update_month)==month:continue
            infra.last_update_month=month
            if infra.condition>0:infra.condition=max(0,infra.condition-1)
            infra.hazard_level=max(0,infra.hazard_level-8)
            a=self.state.settlements.get(plan.origin);b=self.state.settlements.get(plan.destination)
            if self.version<4:
                same_faction=bool(a and b and a.faction_id and a.faction_id==b.faction_id)
                faction=self.state.factions.get(a.faction_id) if same_faction and a else None
                if faction is not None and infra.condition<82 and faction.treasury>20:
                    repair=min(10,100-infra.condition);cost=max(2,repair*2)
                    if faction.treasury>=cost:faction.treasury-=cost;self.repair_route(plan.uid,repair,minute)
                self._refresh_blocked(plan,infra,minute)
                if a is not None and b is not None:self._mirror_trade_route(plan,a,b)
                continue

            controller=self.state.factions.get(infra.control_faction_id)
            if controller is None and a is not None and b is not None and a.faction_id==b.faction_id:
                controller=self.state.factions.get(a.faction_id)
            if controller is not None:
                investment=max(0,min(100,int(getattr(controller,"road_investment",50))))
                target=68+investment//5+(6 if plan.route_class=="maintained_road" else 0)
                if infra.condition<target and controller.treasury>12:
                    repair=min(4+investment//20,100-infra.condition);cost=max(2,repair*2)
                    if controller.treasury>=cost:
                        controller.treasury-=cost;self.repair_route(plan.uid,repair,minute)
                broken=sorted((cid for cid in infra.blocked_crossings if infra.crossing_conditions.get(cid,100)<=10),
                              key=lambda cid:(infra.crossing_conditions.get(cid,100),cid))
                if broken and controller.treasury>=24:
                    cid=broken[0];repair=min(25,100-infra.crossing_conditions.get(cid,0));cost=max(8,repair*2)
                    if controller.treasury>=cost:
                        controller.treasury-=cost;self.repair_route(plan.uid,repair,minute,crossing_id=cid)
            self._hard_blocked_crossings(infra,minute)
            self._maybe_restore_base(plan,minute);self._refresh_blocked(plan,infra,minute)
            if a is not None and b is not None:self._mirror_trade_route(plan,a,b)
        if self.version>=4:self._update_border_posts(list(self._active_plans.values()),minute)

    def _update_centrality_and_hinterlands(self,settlements:dict[str,object],plans:list[RegionalRoutePlan])->None:
        degree={uid:0 for uid in settlements};candidate_regions=set();route_edges={}
        for s in settlements.values():candidate_regions.add((int(s.region_x),int(s.region_y)))
        for plan in plans:
            regions=self._effective_regions(plan) if self.version>=4 else list(plan.region_path)
            infra=self.state.route_infrastructure.get(plan.uid)
            degree[plan.origin]=degree.get(plan.origin,0)+1;degree[plan.destination]=degree.get(plan.destination,0)+1
            candidate_regions.update(regions)
            for a,b in zip(regions,regions[1:]):
                condition=self._effective_condition(infra) if infra is not None else 100
                route_edges[self._transition(a,b)]=(condition,bool(infra and infra.contested),bool(infra and infra.blocked))
        for region in list(candidate_regions):
            for dx,dy in CARDINALS:candidate_regions.add((region[0]+dx,region[1]+dy))
        for uid,s in settlements.items():
            through=sum(1 for p in plans if (int(s.region_x),int(s.region_y)) in self._effective_regions(p)[1:-1])
            s.route_centrality=min(100,degree.get(uid,0)*24+through*12)

        factions={s.faction_id for s in settlements.values() if s.faction_id in self.state.factions}
        for faction in self.state.factions.values():
            faction.influence_regions={};faction.hinterland_regions=[]
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
                    edge=self._transition(cur,nxt)
                    if edge in route_edges:
                        condition,contested,blocked=route_edges[edge]
                        step=8+(100-condition)//12+(8 if contested else 0)+(20 if blocked else 0)
                    else:step=30
                    nc=cost+step
                    if nc>=best.get(nxt,1<<60):continue
                    best[nxt]=nc;heapq.heappush(heap,(nc,nxt))
            faction.influence_regions={f"{r[0]},{r[1]}":max(0,100-c) for r,c in sorted(best.items()) if c<100}

        winners={}
        ranking={}
        for region in candidate_regions:
            token=self._region_token(region);rows=[]
            for faction_id in factions:
                faction=self.state.factions[faction_id];score=int(faction.influence_regions.get(token,0))
                if score>0:rows.append((score,int(getattr(faction,"prominence",0)),faction_id))
            rows.sort(reverse=True);ranking[token]=rows
            if rows:winners[token]=rows[0]
        for faction_id in factions:
            faction=self.state.factions[faction_id]
            faction.hinterland_regions=sorted(region for region,row in winners.items() if row[2]==faction_id and row[0]>=35)

        if self.version>=4:
            for s in settlements.values():
                token=self._region_token((int(s.region_x),int(s.region_y)));rows=ranking.get(token,[])
                own=int(self.state.factions.get(s.faction_id).influence_regions.get(token,0)) if s.faction_id in self.state.factions else 0
                rivals=[row for row in rows if row[2]!=s.faction_id]
                rival_score=rivals[0][0] if rivals else 0;rival_id=rivals[0][2] if rivals else ""
                own_faction=self.state.factions.get(s.faction_id)
                war=bool(own_faction and rival_id in own_faction.at_war)
                if rival_score>=35 and (war or abs(own-rival_score)<=18):
                    s.frontier_status="contested"
                elif own<65 or rival_score>=25:
                    s.frontier_status="frontier"
                else:s.frontier_status="core"
                s.border_pressure=max(0,min(100,rival_score+(20 if war else 0)))
                s.patrol_pressure=max(0,min(100,(own_faction.power//3 if own_faction else 0)+(25 if s.frontier_status=="contested" else 8 if s.frontier_status=="frontier" else 0)))
