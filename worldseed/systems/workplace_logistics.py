from __future__ import annotations

from worldseed.core.coords import WorldPos
from worldseed.systems.state import WorkplaceLogisticsState, WorkplaceShipmentState


class WorkplaceLogisticsSystem:
    """Bridge aggregate settlement production into bounded exact workplace stock.

    Labor reservations remain authoritative. This system materializes only the
    share represented by named workers with a real generated workplace/storage,
    then falls back to the aggregate ledger for every remaining batch.
    """

    def __init__(self,state,registry,seed:bytes,physicalization=None):
        self.state=state;self.registry=registry;self.seed=seed;self.physicalization=physicalization
        self.storage_access=None
        self.physical_labor_authorities=[]

    def attach_physicalization(self,physicalization)->None:self.physicalization=physicalization

    def _storage_for_property(self,property_id:str):
        rows=sorted(
            (c for c in self.state.containers.values() if c.kind=="property" and c.property_id==str(property_id)),
            key=lambda c:(c.uid!='property-storage:'+str(property_id),c.uid),
        )
        return rows[0] if rows else None

    def _reservation(self,town_uid:str,process_id:str,day:int):
        row=self.state.labor_reservations.get(f"labor:{town_uid}:{process_id}")
        if row is None or not row.active or row.assigned_day!=int(day):return None
        return row

    def _bindings(self,town,proc,day:int):
        reservation=self._reservation(town.uid,proc.id,day)
        if reservation is None:return []
        out=[];seen=set()
        for uid in sorted(reservation.representative_uids):
            npc=self.state.npcs.get(uid)
            if npc is None or not npc.alive or not npc.workplace_id:continue
            # Exact activity workers already replaced their anonymous batch in
            # EconomySystem. Remaining anonymous labor must not materialize a
            # second batch through that same named representative's store.
            if npc.assigned_process_id==proc.id and any(
                callable(getattr(authority,"supports_physical_work",None))
                and authority.supports_physical_work(npc,town)
                for authority in self.physical_labor_authorities
            ):continue
            storage=self._storage_for_property(npc.workplace_id)
            if storage is None or storage.uid in seen:continue
            seen.add(storage.uid);out.append((npc,storage))
        return out

    def _row(self,town,proc,npc,storage)->WorkplaceLogisticsState:
        uid=f"workplace:{storage.property_id}:{proc.id}"
        row=self.state.workplace_logistics.get(uid)
        if row is None:
            row=WorkplaceLogisticsState(uid,town.uid,storage.property_id,storage.uid,proc.id)
            self.state.workplace_logistics[uid]=row
        row.settlement_id=town.uid;row.property_id=storage.property_id;row.storage_uid=storage.uid;row.process_id=proc.id
        if npc.uid not in row.representative_uids:row.representative_uids=sorted(set(row.representative_uids+[npc.uid]))
        return row

    @staticmethod
    def _ledger(row,minute:int,kind:str,**data)->None:
        row.ledger.append({"minute":int(minute),"kind":str(kind),**data});row.ledger=row.ledger[-80:]

    def _load(self,container)->tuple[int,int]:
        mass=volume=0
        for iid,qty in container.items.items():
            item=self.registry.items.get(iid)
            if item:mass+=item.mass_g*max(0,int(qty));volume+=item.volume_ml*max(0,int(qty))
        return mass,volume

    def _fit(self,container,item_id:str)->int:
        item=self.registry.items.get(item_id)
        if item is None:return 999999
        mass,volume=self._load(container)
        mfit=999999 if item.mass_g<=0 else max(0,(container.capacity_mass_g-mass)//item.mass_g)
        vfit=999999 if item.volume_ml<=0 else max(0,(container.capacity_volume_ml-volume)//item.volume_ml)
        return max(0,min(mfit,vfit))

    @staticmethod
    def _has_batch_inputs(container,proc)->bool:
        return all(container.items.get(iid,0)>=qty for iid,qty in proc.inputs.items())

    @staticmethod
    def _consume_batch_inputs(container,proc)->None:
        for iid,qty in proc.inputs.items():
            left=container.items.get(iid,0)-qty
            if left>0:container.items[iid]=left
            else:container.items.pop(iid,None)

    @staticmethod
    def _aggregate_capacity(town,proc,batches:int)->int:
        batches=max(0,int(batches))
        for iid,qty in proc.inputs.items():batches=min(batches,town.stocks.get(iid,0)//max(1,qty))
        return max(0,batches)

    @staticmethod
    def _consume_aggregate_inputs(town,proc,batches:int)->None:
        for iid,qty in proc.inputs.items():town.stocks[iid]=town.stocks.get(iid,0)-qty*int(batches)

    @staticmethod
    def _output_total(proc,batches:int,bonus:int)->dict[str,int]:
        if batches<=0:return {}
        return {iid:max(1,qty*batches*int(bonus)//100) for iid,qty in proc.outputs.items()}

    def _replenish_inputs(self,town,proc,npc,storage,row,minute:int)->None:
        moved={}
        for iid,qty in proc.inputs.items():
            have=max(0,int(storage.items.get(iid,0)));missing=max(0,int(qty)-have)
            if missing<=0:continue
            transfer=min(missing,max(0,int(town.stocks.get(iid,0))),self._fit(storage,iid))
            if transfer<=0:continue
            town.stocks[iid]=town.stocks.get(iid,0)-transfer;storage.items[iid]=have+transfer
            row.staged_inputs_total[iid]=row.staged_inputs_total.get(iid,0)+transfer;moved[iid]=transfer
        if moved:self._ledger(row,minute,"input_buffer",items=moved)

    def _market_pos(self,town)->WorldPos:
        if self.physicalization is not None:
            pos=self.physicalization.destination_for_function(town.uid,("market",))
            if pos is not None:return pos
        return WorldPos(int(town.x),int(town.y),0)

    def _carrier(self,row):
        members=[self.state.npcs[u] for u in row.representative_uids if u in self.state.npcs and self.state.npcs[u].alive]
        return min(members,key=lambda n:(len(n.tasks),n.hunger,n.uid)) if members else None

    def _queue_market_shipment(self,town,proc,row,storage,item_id:str,qty:int,minute:int)->int:
        qty=min(max(0,int(qty)),max(0,int(storage.items.get(item_id,0))))
        carrier=self._carrier(row)
        if qty<=0 or carrier is None:return 0
        pickup=None
        if storage.interior_space_id:
            if self.storage_access is None:return 0
            pickup=self.storage_access.transfer_tasks(carrier,storage,'workplace_pickup',{})
            if not pickup:return 0
        left=storage.items.get(item_id,0)-qty
        if left>0:storage.items[item_id]=left
        else:storage.items.pop(item_id,None)
        uid=self.state.uid("workplace-shipment");market=self._market_pos(town)
        distance=abs(storage.x-market.x)+abs(storage.y-market.y)
        shipment=WorkplaceShipmentState(
            uid,row.uid,town.uid,carrier.uid,item_id,qty,storage.uid,int(minute),
            coarse_due_minute=int(minute)+max(180,min(720,120+distance*4)),
        )
        self.state.workplace_shipments[uid]=shipment
        if pickup is None:
            pickup=[{"kind":"move","x":storage.x,"y":storage.y},
                    {"kind":"perform","action":"workplace_pickup"}]
        for task in pickup:task['shipment_uid']=uid
        carrier.tasks.extend(pickup+[
            {"kind":"move","x":market.x,"y":market.y,"shipment_uid":uid},
            {"kind":"perform","action":"workplace_dropoff","shipment_uid":uid},
        ])
        self._ledger(row,minute,"market_shipment_reserved",item=item_id,quantity=qty,shipment_uid=uid)
        return qty

    def _plan_market_shipments(self,town,proc,row,storage,minute:int)->None:
        for iid,batch_qty in proc.outputs.items():
            reserve=max(1,int(batch_qty))
            excess=max(0,int(storage.items.get(iid,0))-reserve)
            if excess<=0:continue
            # Keep shipments bounded so one representative does not accumulate
            # an arbitrarily long task/cargo chain in a single daily tick.
            self._queue_market_shipment(town,proc,row,storage,iid,min(excess,max(1,batch_qty*4)),minute)

    def run_process(self,town,proc,workers:int,day:int,minute:int,bonus:int)->int:
        labor_batches=max(0,int(workers)//max(1,int(proc.workers)))
        if labor_batches<=0:return 0
        bindings=self._bindings(town,proc,day)
        if not bindings:
            batches=self._aggregate_capacity(town,proc,labor_batches)
            if batches<=0:return 0
            self._consume_aggregate_inputs(town,proc,batches)
            for iid,amount in self._output_total(proc,batches,bonus).items():town.stocks[iid]=town.stocks.get(iid,0)+amount
            return batches

        physical=[]
        for npc,storage in bindings[:labor_batches]:
            row=self._row(town,proc,npc,storage);row.last_run_minute=int(minute)
            if self._has_batch_inputs(storage,proc):
                self._consume_batch_inputs(storage,proc);row.physical_batches_total+=1;row.blocked_reason=""
                physical.append((npc,storage,row))
            else:
                row.blocked_reason="input buffer empty" if proc.inputs else ""

        remaining=labor_batches-len(physical)
        aggregate=self._aggregate_capacity(town,proc,remaining)
        self._consume_aggregate_inputs(town,proc,aggregate)
        total=len(physical)+aggregate

        if total>0:
            outputs=self._output_total(proc,total,bonus)
            for iid,total_amount in outputs.items():
                physical_amount=(total_amount*len(physical))//total if physical else 0
                if physical and physical_amount<=0:physical_amount=1
                physical_amount=min(total_amount,physical_amount)
                aggregate_amount=total_amount-physical_amount
                overflow=0
                if physical_amount:
                    base=physical_amount//len(physical);extra=physical_amount%len(physical)
                    for index,(npc,storage,row) in enumerate(physical):
                        share=base+(1 if index<extra else 0);placed=min(share,self._fit(storage,iid))
                        if placed:
                            storage.items[iid]=storage.items.get(iid,0)+placed
                            row.retained_outputs_total[iid]=row.retained_outputs_total.get(iid,0)+placed
                        spill=share-placed
                        if spill:
                            overflow+=spill;row.overflow_outputs_total[iid]=row.overflow_outputs_total.get(iid,0)+spill
                town.stocks[iid]=town.stocks.get(iid,0)+aggregate_amount+overflow

            for npc,storage,row in physical:
                self._ledger(row,minute,"physical_production",process=proc.id,batches=1,outputs=dict(proc.outputs))
            for npc,storage in bindings:
                row=self._row(town,proc,npc,storage)
                self._plan_market_shipments(town,proc,row,storage,minute)

        # Inputs staged after production are a real next-cycle buffer, not an
        # extra current-cycle input source. This avoids duplicating aggregate
        # production while making future physical production depend on stock.
        for npc,storage in bindings:
            row=self._row(town,proc,npc,storage);self._replenish_inputs(town,proc,npc,storage,row,minute)
            if total<=0 and proc.inputs and not self._has_batch_inputs(storage,proc):row.blocked_reason="input shortage"
        return total

    def pickup_shipment(self,shipment_uid:str,carrier_uid:str,minute:int)->bool:
        s=self.state.workplace_shipments.get(str(shipment_uid))
        if s is None or s.carrier_uid!=str(carrier_uid) or s.status!="assigned":return False
        container=next((c for c in self.state.containers.values() if c.uid==s.source_uid),None)
        if container is not None and container.interior_space_id:
            npc=self.state.npcs.get(str(carrier_uid))
            if self.storage_access is None or npc is None or not self.storage_access.in_reach(npc,container):return False
        s.status="carried";s.picked_minute=int(minute);return True

    def _finish_shipment(self,s,minute:int)->bool:
        town=self.state.settlements.get(s.settlement_id)
        if town is None:return False
        town.stocks[s.item_id]=town.stocks.get(s.item_id,0)+s.quantity
        s.status="delivered";s.delivered_minute=int(minute)
        row=self.state.workplace_logistics.get(s.workplace_uid)
        if row is not None:
            row.market_outputs_total[s.item_id]=row.market_outputs_total.get(s.item_id,0)+s.quantity
            self._ledger(row,minute,"market_shipment_delivered",item=s.item_id,quantity=s.quantity,shipment_uid=s.uid)
        carrier=self.state.npcs.get(s.carrier_uid)
        if carrier is not None:carrier.tasks=[t for t in carrier.tasks if t.get("shipment_uid")!=s.uid]
        return True

    def dropoff_shipment(self,shipment_uid:str,carrier_uid:str,minute:int)->bool:
        s=self.state.workplace_shipments.get(str(shipment_uid))
        if s is None or s.carrier_uid!=str(carrier_uid) or s.status not in {"assigned","carried"}:return False
        return self._finish_shipment(s,minute)

    def process_overdue(self,minute:int)->int:
        done=0
        for s in list(self.state.workplace_shipments.values()):
            if s.status in {"assigned","carried"} and s.coarse_due_minute>=0 and int(minute)>=s.coarse_due_minute:
                if self._finish_shipment(s,minute):done+=1
        return done

    def hourly_update(self,minute:int)->None:self.process_overdue(minute)
