from __future__ import annotations
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import LivingWorldState, NPCState
from worldseed.systems.history import HistorySystem
from worldseed.systems.pathfinding import local_path

class NPCSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem,world=None,building=None,lod=None):self.state=state;self.seed=seed;self.history=history;self.world=world;self.building=building;self.lod=lod
    def hourly_update(self,minute:int,player_pos:WorldPos)->None:
        for npc in self.state.npcs.values():
            if not npc.alive:continue
            if self.lod is not None:
                tier=self.lod.npc_tier(player_pos,npc)
                if not self.lod.should_update(tier,minute,"ai"):continue
            elif abs(npc.x-player_pos.x)+abs(npc.y-player_pos.y)>1200:continue
            town=self.state.settlements.get(npc.settlement_id)
            if not town:continue
            npc.hunger=min(100,npc.hunger+3);npc.thirst=min(100,npc.thirst+5);npc.rest=min(100,npc.rest+2)
            if not npc.home_id:self._assign_property(npc,town)
            if not npc.tasks:self._choose_goal_and_plan(npc,town,minute)
            self._execute_task(npc,town,minute,player_pos)
    def _choose_goal_and_plan(self,npc:NPCState,town,minute:int)->None:
        war=bool(self.state.factions.get(npc.faction_id).at_war) if npc.faction_id in self.state.factions else False
        scores={"eat":npc.hunger*3,"drink":npc.thirst*4,"rest":npc.rest*2,"work":80+(30 if "ambitious" in npc.traits else 0)-npc.hunger,"socialize":35+(25 if "kind" in npc.traits else 0),"guard":(85 if npc.occupation=="guard" else 25)+(35 if war else 0)}
        best=max(scores,key=scores.get);best_score=scores[best]
        if npc.goal_score*110//100>=best_score:best=npc.goal;best_score=npc.goal_score
        npc.goal=best;npc.goal_score=best_score
        center={"kind":"move","x":town.x,"y":town.y}
        if best in ("eat","drink","work","guard"):npc.tasks=[center,{"kind":"perform","action":best}]
        elif best=="rest":npc.tasks=[{"kind":"move","x":town.x+(hash_u64(self.seed,'home-x',npc.uid)%9)-4,"y":town.y+(hash_u64(self.seed,'home-y',npc.uid)%9)-4},{"kind":"perform","action":"rest"}]
        elif best=="socialize":
            peers=[p for p in self.state.npcs.values() if p.alive and p.settlement_id==npc.settlement_id and p.uid!=npc.uid]
            if peers:
                other=peers[hash_u64(self.seed,"social-target",npc.uid,minute//60)%len(peers)];npc.tasks=[{"kind":"move","x":other.x,"y":other.y},{"kind":"social","target":other.uid}]
    def _execute_task(self,npc:NPCState,town,minute:int,player_pos:WorldPos)->None:
        if not npc.tasks:return
        task=npc.tasks[0]
        if task['kind']=='move':
            goal=WorldPos(int(task['x']),int(task['y']),npc.z);start=WorldPos(npc.x,npc.y,npc.z)
            if abs(npc.x-goal.x)+abs(npc.y-goal.y)<=1:npc.tasks.pop(0);return
            if self.world and abs(npc.x-player_pos.x)<80 and abs(npc.y-player_pos.y)<60:
                def passable(p):return self.world.is_passable(p) and (self.building.passable(p,self.world.is_passable(p)) if self.building else True)
                path=local_path(start,goal,passable,800)
                if len(path)>1:
                    step=path[min(3,len(path)-1)];npc.x,npc.y=step.x,step.y
                    if step==goal:npc.tasks.pop(0)
                    return
            # aggregate/remote travel is straight-line at coarse fidelity
            npc.x += 0 if npc.x==goal.x else (1 if goal.x>npc.x else -1);npc.y += 0 if npc.y==goal.y else (1 if goal.y>npc.y else -1)
        elif task['kind']=='perform':
            action=task['action'];npc.tasks.pop(0)
            if action=='eat' and town.stocks.get('core:wheat',0)>0:town.stocks['core:wheat']-=1;npc.hunger=max(0,npc.hunger-45)
            elif action=='drink':npc.thirst=max(0,npc.thirst-55)
            elif action=='rest':npc.rest=max(0,npc.rest-55)
            elif action=='work':self._work(npc,town)
            elif action=='guard':npc.rest=min(100,npc.rest+5)
        elif task['kind']=='social':
            npc.tasks.pop(0);other=self.state.npcs.get(task['target'])
            if other:self._socialize(npc,other,minute)
    def _assign_property(self,npc:NPCState,town)->None:
        idx=sum(1 for n in self.state.npcs.values() if n.settlement_id==town.uid and n.uid<npc.uid);home=f'{town.uid}:house:{idx//4}';work=f'{town.uid}:{npc.occupation}:{idx}'
        town.property_owners.setdefault(home,npc.uid);town.property_owners.setdefault(work,npc.uid);npc.home_id=home;npc.workplace_id=work
    def _work(self,npc:NPCState,town)->None:
        mapping={"farmer":("core:wheat",2),"hunter":("core:meat",1),"miner":("core:iron_ore",1),"carpenter":("core:wood",2),"herder":("core:turnip",1),"merchant":("core:wood",1)};item,amount=mapping.get(npc.occupation,(None,0))
        if npc.occupation=='smith' and 'tech:smelting' in town.knowledge and town.stocks.get('core:iron_ore',0)>=2 and town.stocks.get('core:coal',0)>=1:town.stocks['core:iron_ore']-=2;town.stocks['core:coal']-=1;town.stocks['core:iron_bloom']=town.stocks.get('core:iron_bloom',0)+1
        elif item:town.stocks[item]=town.stocks.get(item,0)+amount
    def _socialize(self,npc:NPCState,other:NPCState,minute:int)->None:
        rel=npc.relationships.setdefault(other.uid,{"affection":0,"trust":0,"fear":0,"respect":0,"obligation":0,"familiarity":0});rel['familiarity']=min(100,rel['familiarity']+2);rel['trust']=min(100,rel['trust']+1);rel['affection']=min(100,rel['affection']+1)
        npc.memories.append({"minute":minute,"type":"social","subject":other.uid,"salience":5,"valence":5});npc.memories=npc.memories[-40:]
