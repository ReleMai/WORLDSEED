from __future__ import annotations

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import HouseholdDeliveryState, HouseholdState

FOODS=("core:bread","core:cooked_meat","core:smoked_fish","core:wheat","core:turnip","core:meat","core:dried_meat","core:beans","core:berries")
DAILY_WAGE={"farmer":6,"herder":6,"miner":9,"carpenter":8,"hunter":7,"smith":10,"merchant":8,"guard":7,"healer":9,"scholar":8,"priest":6}
ESSENTIALS=("core:wood","core:soap","core:herbal_tonic")

class HouseholdEconomySystem:
    """Material household economy over physical homes, cash, markets and hauling.

    Named residents are exact actors. Goods bought by their household leave the
    settlement market immediately, exist as persistent cargo while hauled, and
    only become household stock when delivered into real home storage.
    """
    def __init__(self,state,seed:bytes,registry=None,economy=None):
        self.state=state;self.seed=seed;self.registry=registry;self.economy=economy;self.physicalization=None
        self.storage_access=None;self.commerce=None;self.active_carrier=None

    def attach_physicalization(self,physicalization)->None:self.physicalization=physicalization

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
            h.logistics_mode="exact" if h.storage_uids else "aggregate"
        return tuple(self.state.households[k] for k in sorted(groups))

    def _members(self,h):return [self.state.npcs[u] for u in h.member_uids if u in self.state.npcs and self.state.npcs[u].alive]
    def _containers(self,h):
        by_uid={c.uid:c for c in self.state.containers.values()};return [by_uid[u] for u in h.storage_uids if u in by_uid]
    def household_wealth(self,h)->int:return sum(max(0,int(n.wealth)) for n in self._members(h))

    def _ledger(self,h,minute:int,kind:str,**data)->None:
        h.ledger.append({"minute":int(minute),"kind":str(kind),**data});h.ledger=h.ledger[-80:]

    def _debit(self,h,amount:int)->bool:
        amount=max(0,int(amount))
        if self.household_wealth(h)<amount:return False
        left=amount
        payers=sorted(self._members(h),key=lambda n:(n.age<16,-n.wealth,n.uid))
        for n in payers:
            take=min(left,max(0,int(n.wealth)));n.wealth-=take;left-=take
            if left<=0:return True
        return left<=0

    def _credit(self,h,amount:int,preferred_uid:str="")->None:
        amount=max(0,int(amount));members=self._members(h)
        if not members or amount<=0:return
        target=next((n for n in members if n.uid==preferred_uid),None) or sorted(members,key=lambda n:(n.age<16,n.uid))[0]
        target.wealth+=amount

    def _inventory(self,h)->dict[str,int]:
        out={}
        for c in self._containers(h):
            for iid,qty in c.items.items():out[iid]=out.get(iid,0)+max(0,int(qty))
        return out

    def _inbound(self,h)->dict[str,int]:
        out={}
        for d in self.state.household_deliveries.values():
            if d.household_uid==h.uid and d.status in {"assigned","carried"}:out[d.item_id]=out.get(d.item_id,0)+d.quantity
        return out

    def _container_load(self,c)->tuple[int,int]:
        mass=volume=0
        if self.registry is None:return 0,0
        for iid,qty in c.items.items():
            item=self.registry.items.get(iid)
            if item:mass+=item.mass_g*qty;volume+=item.volume_ml*qty
        return mass,volume

    def _fit(self,c,item_id:str)->int:
        if self.registry is None or item_id not in self.registry.items:return 999999
        item=self.registry.items[item_id];mass,volume=self._container_load(c)
        mfit=999999 if item.mass_g<=0 else max(0,(c.capacity_mass_g-mass)//item.mass_g)
        vfit=999999 if item.volume_ml<=0 else max(0,(c.capacity_volume_ml-volume)//item.volume_ml)
        return max(0,min(mfit,vfit))

    def _daily_food_need(self,h)->int:return max(1,(len(self._members(h))+2)//3)

    def _reserve_policy(self,h)->int:
        cash=self.household_wealth(h)
        days=2 if cash<20 else (3 if cash<80 else 5)
        if h.days_short>=2:days=min(6,days+1)
        return days

    def _set_targets(self,h)->None:
        members=self._members(h);h.reserve_days=self._reserve_policy(h)
        food=self._daily_food_need(h)*h.reserve_days
        fuel=max(1,(len(members)+3)//4)*h.reserve_days
        soap=max(1,(len(members)+3)//4)
        medicine=1 if any(n.hp<70 or n.infections for n in members) else 0
        h.target_stock={"food":food,"core:wood":fuel,"core:soap":soap,"core:herbal_tonic":medicine}

    def _food_group(self,item_id:str)->str:
        item=self.registry.items.get(item_id) if self.registry is not None else None
        groups=tuple(getattr(item,"food_groups",()) or ()) if item is not None else ()
        if groups:return str(groups[0])
        if item_id in {"core:meat","core:dried_meat","core:beans"}:return "protein"
        if item_id=="core:wheat":return "grain"
        return "produce"

    def _consume_food(self,h,minute:int)->None:
        members=self._members(h);need=self._daily_food_need(h);remaining=need;mix={}
        containers=self._containers(h)
        available={iid:sum(max(0,int(c.items.get(iid,0))) for c in containers) for iid in FOODS}
        # Prefer a varied basket before consuming duplicates. Scarcity still wins:
        # if only one food exists the household eats it rather than starving.
        ordered=sorted((iid for iid in FOODS if available[iid]>0),key=lambda iid:(h.diet_mix.get(self._food_group(iid),0),-available[iid],iid))
        while remaining>0 and ordered:
            progressed=False
            for iid in ordered:
                if remaining<=0:break
                c=next((row for row in containers if row.items.get(iid,0)>0),None)
                if c is None:continue
                c.items[iid]-=1
                if c.items[iid]<=0:c.items.pop(iid,None)
                group=self._food_group(iid);mix[group]=mix.get(group,0)+1;remaining-=1;progressed=True
            if not progressed:break
        h.diet_mix=mix
        variety=len([v for v in mix.values() if v>0]);h.nutrition_quality=max(10,min(100,35+variety*20-(remaining*20)))
        h.food_shortage=remaining;h.days_short=(h.days_short+1 if remaining else 0);h.last_consumed_minute=int(minute)
        hunger_delta=(12+remaining*8) if remaining else (-12 if h.nutrition_quality>=75 else -8)
        for npc in members:
            npc.hunger=max(0,min(100,npc.hunger+hunger_delta))
            if h.nutrition_quality<45:npc.needs["health"]=min(100,npc.needs.get("health",0)+3)
            elif h.nutrition_quality>=75:npc.needs["health"]=max(0,npc.needs.get("health",0)-2)
        self._ledger(h,minute,"daily_food",needed=need,shortage=remaining,diet=dict(mix),quality=h.nutrition_quality)

    @staticmethod
    def _take_item(containers,item_id:str,quantity:int)->int:
        remaining=max(0,int(quantity));taken=0
        for c in containers:
            have=max(0,int(c.items.get(item_id,0)));use=min(remaining,have)
            if use:
                left=have-use
                if left:c.items[item_id]=left
                else:c.items.pop(item_id,None)
                taken+=use;remaining-=use
            if remaining<=0:break
        return taken

    def _consume_essentials(self,h,minute:int)->None:
        members=self._members(h);containers=self._containers(h);day=int(minute)//1440
        fuel_need=max(1,(len(members)+3)//4) if day%2==0 else 0
        hygiene_need=max(1,(len(members)+3)//4) if day%7==0 else 0
        sick=sum(1 for n in members if n.hp<70 or n.infections);medicine_need=1 if sick else 0
        h.fuel_shortage=max(0,fuel_need-self._take_item(containers,"core:wood",fuel_need))
        h.hygiene_shortage=max(0,hygiene_need-self._take_item(containers,"core:soap",hygiene_need))
        h.medical_shortage=max(0,medicine_need-self._take_item(containers,"core:herbal_tonic",medicine_need))
        hardship=min(100,h.food_shortage*30+h.fuel_shortage*15+h.hygiene_shortage*8+h.medical_shortage*25+max(0,55-h.nutrition_quality)//3)
        h.hardship_score=hardship;h.stable_days=(h.stable_days+1 if hardship==0 else 0)
        for npc in members:
            if h.fuel_shortage:npc.needs["safety"]=min(100,npc.needs.get("safety",0)+4)
            if h.hygiene_shortage:npc.needs["health"]=min(100,npc.needs.get("health",0)+3)
            if h.medical_shortage and (npc.hp<70 or npc.infections):npc.needs["health"]=min(100,npc.needs.get("health",0)+8)
            if hardship==0:npc.needs["safety"]=max(0,npc.needs.get("safety",0)-2)
        self._ledger(h,minute,"daily_essentials",fuel_shortage=h.fuel_shortage,hygiene_shortage=h.hygiene_shortage,medical_shortage=h.medical_shortage,hardship=hardship)

    def _pay_prior_work(self,h,minute:int)->None:
        if h.last_income_minute==int(minute) or self.economy is None:return
        day=int(minute)//1440;town=self.state.settlements.get(h.settlement_id)
        if town is None:return
        earned=0
        for n in self._members(h):
            if n.age<16 or n.work_assignment_day!=day-1 or n.work_hours_today<=0:continue
            daily=DAILY_WAGE.get(n.occupation,6);gross=max(1,daily*min(12,n.work_hours_today)//8);paid=min(max(0,int(town.wealth)),gross)
            if paid<=0:continue
            town.wealth-=paid;n.wealth+=paid;earned+=paid
            self.economy.record_transaction(town.uid,"household_wage",town.uid,n.uid,copper_value=paid,minute=minute)
        h.last_income_minute=int(minute);h.total_income+=earned
        if earned:self._ledger(h,minute,"wages",amount=earned)

    def _market_pos(self,h)->WorldPos:
        town=self.state.settlements[h.settlement_id]
        if self.physicalization is not None:
            p=self.physicalization.destination_for_function(town.uid,("market",))
            if p is not None:return p
        return WorldPos(int(town.x),int(town.y),0)

    def _carrier(self,h):
        members=self._members(h);adults=[n for n in members if n.age>=16] or members
        return min(adults,key=lambda n:(len(n.tasks),n.hunger,n.uid)) if adults else None

    def _destination(self,h,item_id:str):
        options=[(self._fit(c,item_id),c) for c in self._containers(h)];options=[row for row in options if row[0]>0]
        if not options:return None,0
        fit,c=max(options,key=lambda row:(row[0],-row[1].y,-row[1].x,row[1].uid));return c,fit

    def _queue_purchase(self,h,item_id:str,requested:int,minute:int)->int:
        if self.economy is None or requested<=0:return 0
        town=self.state.settlements.get(h.settlement_id);carrier=self._carrier(h);dest,fit=self._destination(h,item_id)
        if town is None or carrier is None or dest is None:return 0
        available=max(0,int(town.stocks.get(item_id,0)));unit=self.economy.trade_price(town.uid,item_id,buy=True);afford=self.household_wealth(h)//max(1,unit)
        qty=min(int(requested),available,afford,fit)
        physical=bool(self.storage_access is not None and self.active_carrier is not None and self.active_carrier(carrier))
        if physical:
            qty=min(qty,self.storage_access.goods.carry_fit(carrier,item_id))
            if not self.storage_access.transfer_tasks(carrier,dest,'household_dropoff',{item_id:qty}):return 0
        if qty<=0:return 0
        cost=qty*unit
        if not self._debit(h,cost):return 0
        town.stocks[item_id]=available-qty;town.wealth+=cost
        uid=self.state.uid("household-delivery");market=self._market_pos(h);distance=abs(market.x-dest.x)+abs(market.y-dest.y)
        delivery=HouseholdDeliveryState(uid,h.uid,town.uid,carrier.uid,item_id,qty,dest.uid,cost,int(minute),coarse_due_minute=int(minute)+max(180,min(720,120+distance*4)))
        self.state.household_deliveries[uid]=delivery
        if physical:
            delivery.physical_cargo=True
            market=self.commerce.market_position(town)
            carrier.tasks.extend([
                dict(kind='move',x=market.x,y=market.y,z=market.z,physical_path=True,commerce_task=True,delivery_uid=uid),
                dict(kind='perform',action='household_pickup',commerce_task=True,delivery_uid=uid),
            ])
            carrier.tasks.extend(self.storage_access.transfer_tasks(carrier,dest,'household_dropoff',
                                {item_id:qty},delivery_uid=uid,commerce_task=True))
        else:
            carrier.tasks.extend([
                {"kind":"move","x":market.x,"y":market.y,"delivery_uid":uid},{"kind":"perform","action":"household_pickup","delivery_uid":uid},
                {"kind":"move","x":dest.x,"y":dest.y,"delivery_uid":uid},{"kind":"perform","action":"household_dropoff","delivery_uid":uid},
            ])
        h.total_spent+=cost;h.last_procurement_minute=int(minute)
        self.economy.record_transaction(town.uid,"household_purchase",h.uid,town.uid,copper_value=cost,minute=minute,requested={item_id:qty})
        self._ledger(h,minute,"purchase_reserved",item=item_id,quantity=qty,cost=cost,delivery_uid=uid)
        return qty

    def plan_procurement(self,h,minute:int)->None:
        self._set_targets(h);stock=self._inventory(h);inbound=self._inbound(h);unmet={}
        food_have=sum(stock.get(i,0)+inbound.get(i,0) for i in FOODS);food_need=max(0,h.target_stock["food"]-food_have)
        if food_need:
            town=self.state.settlements.get(h.settlement_id)
            choices=[] if town is None else [i for i in FOODS if town.stocks.get(i,0)>0]
            choices.sort(key=lambda i:(self.economy.trade_price(town.uid,i,buy=True) if self.economy else 9999,int(hash_u64(self.seed,"food-preference",h.uid,i)%17),i))
            left=food_need
            for iid in choices:
                if left<=0:break
                bought=self._queue_purchase(h,iid,left,minute);left-=bought
            if left:unmet["food"]=left
        for iid in ESSENTIALS:
            target=h.target_stock.get(iid,0);need=max(0,target-stock.get(iid,0)-inbound.get(iid,0))
            if need:
                bought=self._queue_purchase(h,iid,need,minute)
                if bought<need:unmet[iid]=need-bought
        h.unmet_needs=unmet

    def pickup_delivery(self,delivery_uid:str,carrier_uid:str,minute:int)->bool:
        d=self.state.household_deliveries.get(str(delivery_uid))
        if d is None or d.carrier_uid!=str(carrier_uid) or d.status!="assigned":return False
        if d.physical_cargo:
            carrier=self.state.npcs.get(d.carrier_uid);town=self.state.settlements.get(d.settlement_id)
            if carrier is None or town is None or self.commerce is None:return False
            market=self.commerce.market_position(town)
            if carrier.uid in self.state.interior_actors or carrier.z!=market.z or abs(carrier.x-market.x)+abs(carrier.y-market.y)>1:return False
            if self.storage_access.goods.carry_fit(carrier,d.item_id)<d.quantity:return False
            carrier.inventory[d.item_id]=carrier.inventory.get(d.item_id,0)+d.quantity
            # Assigned quantity owns reserved market goods; once carried, this
            # record describes the obligation and NPC.inventory owns the cargo.
        d.status="carried";d.picked_minute=int(minute);return True

    def _finish_delivery(self,d,minute:int)->bool:
        h=self.state.households.get(d.household_uid);dest=next((c for c in self.state.containers.values() if c.uid==d.destination_uid),None)
        if h is None or dest is None:return False
        fit=self._fit(dest,d.item_id);placed=min(d.quantity,fit)
        if d.physical_cargo and d.status=='carried':
            carrier=self.state.npcs.get(d.carrier_uid)
            if carrier is None or carrier.inventory.get(d.item_id,0)<d.quantity:return False
            if fit<d.quantity:return False
            carrier.inventory[d.item_id]-=d.quantity
            if not carrier.inventory[d.item_id]:carrier.inventory.pop(d.item_id)
        if placed:dest.items[d.item_id]=dest.items.get(d.item_id,0)+placed
        remainder=d.quantity-placed
        if remainder:
            town=self.state.settlements.get(d.settlement_id);unit=d.copper_value//max(1,d.quantity);refund=unit*remainder
            if town is not None:town.stocks[d.item_id]=town.stocks.get(d.item_id,0)+remainder;town.wealth=max(0,town.wealth-refund)
            self._credit(h,refund,d.carrier_uid);h.total_spent=max(0,h.total_spent-refund);self._ledger(h,minute,"delivery_refund",item=d.item_id,quantity=remainder,amount=refund)
        d.status="delivered";d.delivered_minute=int(minute);self._ledger(h,minute,"delivery_complete",item=d.item_id,quantity=placed,delivery_uid=d.uid)
        carrier=self.state.npcs.get(d.carrier_uid)
        if carrier is not None:carrier.tasks=[t for t in carrier.tasks if t.get("delivery_uid")!=d.uid]
        return True

    def dropoff_delivery(self,delivery_uid:str,carrier_uid:str,minute:int)->bool:
        d=self.state.household_deliveries.get(str(delivery_uid))
        if d is None or d.carrier_uid!=str(carrier_uid) or d.status not in {"assigned","carried"}:return False
        if d.physical_cargo:
            carrier=self.state.npcs.get(d.carrier_uid)
            dest=next((c for c in self.state.containers.values() if c.uid==d.destination_uid),None)
            if d.status!='carried' or carrier is None or dest is None or self.storage_access is None:return False
            if not self.storage_access.in_reach(carrier,dest):return False
        return self._finish_delivery(d,minute)

    def process_overdue(self,minute:int)->int:
        done=0
        for d in list(self.state.household_deliveries.values()):
            if d.status in {"assigned","carried"} and d.coarse_due_minute>=0 and int(minute)>=d.coarse_due_minute:
                carrier=self.state.npcs.get(d.carrier_uid)
                if d.physical_cargo and carrier is not None and self.active_carrier is not None and self.active_carrier(carrier):continue
                if self._finish_delivery(d,minute):done+=1
        return done

    def hourly_update(self,minute:int)->None:self.process_overdue(minute)

    def daily_update(self,minute:int)->None:
        self.process_overdue(minute)
        for h in self.sync():
            if h.last_consumed_minute==int(minute):continue
            self._pay_prior_work(h,minute)
            if h.logistics_mode!="exact":
                h.unmet_needs={"physical_storage":1}
                continue
            self._consume_food(h,minute);self._consume_essentials(h,minute);self.plan_procurement(h,minute)
