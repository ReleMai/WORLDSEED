from __future__ import annotations

from worldseed.systems.state import HouseholdState

FOODS=("core:wheat","core:turnip","core:meat","core:dried_meat","core:beans","core:berries")

class HouseholdEconomySystem:
    """Daily material needs for represented households using physical storage."""
    def __init__(self,state,seed:bytes):self.state=state;self.seed=seed

    def sync(self,settlement_id:str|None=None):
        groups={}
        for npc in self.state.npcs.values():
            if not npc.alive or not npc.family_uid or (settlement_id and npc.settlement_id!=settlement_id):continue
            groups.setdefault(npc.family_uid,[]).append(npc)
        for uid,members in groups.items():
            members.sort(key=lambda n:n.uid);town=members[0].settlement_id
            h=self.state.households.get(uid)
            if h is None:h=HouseholdState(uid,town);self.state.households[uid]=h
            h.settlement_id=town;h.member_uids=[n.uid for n in members]
            homes=[n.home_id for n in members if n.home_id];h.home_id=sorted(homes)[0] if homes else h.home_id
            h.storage_uids=sorted(c.uid for c in self.state.containers.values() if c.kind=="property" and c.property_id==h.home_id)
        return tuple(self.state.households[k] for k in sorted(groups))

    def _containers(self,h):
        by_uid={c.uid:c for c in self.state.containers.values()}
        return [by_uid[uid] for uid in h.storage_uids if uid in by_uid]

    def daily_update(self,minute:int)->None:
        for h in self.sync():
            if h.last_consumed_minute==int(minute):continue
            members=[self.state.npcs[uid] for uid in h.member_uids if uid in self.state.npcs and self.state.npcs[uid].alive]
            need=max(1,(len(members)+2)//3);remaining=need
            for container in self._containers(h):
                for iid in FOODS:
                    have=max(0,int(container.items.get(iid,0)));take=min(remaining,have)
                    if take:
                        left=have-take
                        if left:container.items[iid]=left
                        else:container.items.pop(iid,None)
                        remaining-=take
                    if remaining<=0:break
                if remaining<=0:break
            h.food_shortage=remaining;h.days_short=(h.days_short+1 if remaining else 0);h.last_consumed_minute=int(minute)
            hunger_delta=12+remaining*8 if remaining else -10
            for npc in members:npc.hunger=max(0,min(100,npc.hunger+hunger_delta))
