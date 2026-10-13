from __future__ import annotations
from functools import lru_cache
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.systems.state import LivingWorldState, FireCell, FluidCell, DiseaseState, pos_key
from worldseed.systems.history import HistorySystem
from worldseed.world.lighting import LightingSystem

Q=65535

class WeatherSystem:
    """Legacy-compatible weather plus v8 climate-driven moving fronts."""

    def __init__(self,seed:bytes,generator=None):
        self.seed=seed;self.generator=generator

    def _legacy_at(self,minute:int,x:int,y:int)->dict:
        day=minute//1440;cellx=x//128;celly=y//128;rng=PCG32(derive_seed(self.seed,"weather",day,cellx,celly))
        kinds=["clear","clear","cloudy","rain","rain","wind","storm","fog"]
        kind=rng.choice(kinds);temp_delta={"clear":5,"cloudy":0,"rain":-4,"wind":-2,"storm":-6,"fog":-3}[kind]
        wind=rng.randbelow(5);rain=0 if kind not in ("rain","storm") else 3+rng.randbelow(7)
        return {"kind":kind,"temp_delta":temp_delta,"wind":wind,"rain":rain,"visibility":4 if kind=="fog" else 6 if kind=="storm" else 8,
                "cloud_cover":65 if kind=="cloudy" else 85 if kind in ("rain","storm") else 45 if kind=="fog" else 15,
                "storm_intensity":80 if kind=="storm" else 0,"humidity":75 if kind in ("rain","storm","fog") else 45,
                "wetness":min(100,rain*10),"fog":75 if kind=="fog" else 0,"wind_dx":0,"wind_dy":0,"wind_speed":wind*20}

    def _v8_slot(self,slot:int,x:int,y:int,climate)->dict:
        """Deterministic slow-moving weather fronts with long dry intervals.

        Six two-hour slots share one synoptic front instead of rolling rain
        independently every two hours. A front arrives along prevailing winds,
        peaks, then moves out. Precipitation potential and humidity affect
        incidence, while wind/orography control severity. Rendering remains
        observational; no persistent weather state or save migration is needed.
        """
        slot=max(0,int(slot))
        front_id=slot//6
        phase=slot%6
        drift=front_id*6+phase
        advx=int(x)-(int(climate.prevailing_wind_dx)*drift)//24
        advy=int(y)-(int(climate.prevailing_wind_dy)*drift)//24
        cellx=advx//256;celly=advy//256
        token=hash_u64(self.seed,"weather-v8-front3",front_id,cellx,celly)
        precip=max(0,min(100,int(climate.precipitation_potential)*100//Q))
        humidity=max(0,min(100,int(climate.humidity)*100//Q))
        wind_strength=max(0,min(100,int(climate.wind_strength)*100//Q))
        chance=max(2,min(36,(precip*36+humidity*10)//100-14))
        wet_front=(token%100)<chance
        # Cloudy periods occur between rain systems, without guaranteeing rain.
        clouds=max(6,min(95,(humidity*2+precip)//4+int((token>>13)%37)-18))
        if wet_front:clouds=max(clouds,72+(int((token>>23)%19)))
        rain=0
        if wet_front:
            # Beginning/end of a weather front are lighter than its center.
            envelope=(1,2,3,3,2,1)[phase]
            severity=1+(precip//23)+int((token>>29)%3)
            rain=min(10,max(1,severity*envelope//3))
        # Thunderstorms are uncommon even within rainy fronts.
        storm=0
        if wet_front and rain>=5 and int((token>>35)%100)<10+precip//15:
            storm=min(95,max(24,(rain-4)*16+int((token>>42)%20)))
        wind_speed=max(5,min(100,wind_strength+int((token>>48)%21)-10+(12 if storm else 0)))
        fog=0
        if not wet_front and humidity>=76 and wind_speed<42 and (token>>8)%100<humidity-55:
            fog=max(15,min(85,humidity-8))
        if storm:kind="storm"
        elif rain:kind="rain"
        elif fog:kind="fog"
        elif clouds>=58:kind="cloudy"
        elif wind_speed>=62:kind="wind"
        else:kind="clear"
        temp_delta=3 if kind=="clear" else 0 if kind=="cloudy" else -3 if kind=="rain" else -6 if kind=="storm" else -2
        visibility=4 if fog>=55 else 5 if storm>=55 else 6 if rain>=6 else 8
        return {"kind":kind,"temp_delta":temp_delta,"wind":wind_speed//20,"rain":rain,
                "visibility":visibility,"cloud_cover":cloud,"storm_intensity":storm,
                "humidity":humidity,"fog":fog,
                "wind_dx":int(climate.prevailing_wind_dx),
                "wind_dy":int(climate.prevailing_wind_dy),"wind_speed":wind_speed}

    @lru_cache(maxsize=512)
    def at(self,minute:int,x:int,y:int)->dict:
        generator=self.generator
        climate_getter=getattr(generator,"climate_at",None) if generator is not None else None
        if generator is None or int(getattr(generator,"version",0))<8 or not callable(climate_getter):
            return self._legacy_at(minute,x,y)
        climate=climate_getter(WorldPos(int(x),int(y),0))
        if climate is None:return self._legacy_at(minute,x,y)
        slot=max(0,int(minute))//120
        current=self._v8_slot(slot,x,y,climate)
        recent=[current["rain"]]
        for age in range(1,4):
            recent.append(self._v8_slot(max(0,slot-age),x,y,climate)["rain"])
        wetness=min(100,recent[0]*10+recent[1]*7+recent[2]*4+recent[3]*2+current["humidity"]//10)
        current["wetness"]=wetness
        return current

class EnvironmentSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,seed:bytes,history:HistorySystem,world=None):
        self.state=state;self.registry=registry;self.seed=seed;self.history=history;self.world=world
        self.weather=WeatherSystem(seed,getattr(world,"generator",None));self.lighting=LightingSystem()

    def visual_conditions(self,minute:int,pos:WorldPos):
        weather=self.weather.at(minute,pos.x,pos.y)
        lighting=self.lighting.at(minute,weather.get("cloud_cover",0),weather.get("storm_intensity",0))
        return weather,lighting
    def hourly_update(self,minute:int)->None:
        # crop simulation
        for key,c in list(self.state.crops.items()):
            crop=self.registry.crops.get(c.crop_id)
            if not crop:continue
            w=self.weather.at(minute,c.x,c.y);c.moisture=min(100,c.moisture+w["rain"]*3);c.moisture=max(0,c.moisture-crop.water_use)
            day=minute//1440;season=("spring","summer","autumn","winter")[(day//30)%4]
            if self.world is not None and int(getattr(self.world.generator,"version",0))>=8:
                fields=self.world.generator.sample_fields(WorldPos(c.x,c.y,0))
                climate=-18+(int(fields.temperature)*63)//Q+int(w["temp_delta"])
            else:
                climate=(hash_u64(self.seed,"temp",c.x//64,c.y//64)%60)+15+w["temp_delta"]
            good_temp=crop.min_temp<=climate<=crop.max_temp
            if c.moisture<15 or not good_temp:c.health=max(0,c.health-4)
            elif c.moisture>90:c.health=max(0,c.health-1)
            else:c.health=min(100,c.health+1)
            soil=self.state.soils.get(key)
            if soil and minute%360==0:
                # Different crops stress nutrients differently; rotation and fertility matter.
                n_use,p_use,k_use=(crop.nitrogen,crop.phosphorus,crop.potassium)
                soil.nitrogen=max(0,soil.nitrogen-n_use);soil.phosphorus=max(0,soil.phosphorus-p_use);soil.potassium=max(0,soil.potassium-k_use)
                nutrient=min(soil.nitrogen,soil.phosphorus,soil.potassium)
                c.disease=min(100,max(c.disease,soil.disease_pressure)+(1 if c.moisture>88 else 0))
                if nutrient<20:c.health=max(0,c.health-4)
                elif nutrient<40:c.health=max(0,c.health-2)
                if c.disease>35:c.health=max(0,c.health-max(1,c.disease//25))
                if c.health<=0:soil.disease_pressure=min(100,soil.disease_pressure+8)
            if c.health>0 and season in crop.seasons:
                nutrient_bonus=0 if not soil else min(3,min(soil.nitrogen,soil.phosphorus,soil.potassium)//25)
                c.growth+=max(1,c.health//25+nutrient_bonus)
            if c.growth>=crop.growth_hours*4:c.mature=True
        self._spread_fire(minute);self._flow_fluids()

    def coarse_advance(self,start_minute:int,end_minute:int)->None:
        """Advance local environmental state in bounded blocks for offline simulation.

        This intentionally approximates repeated hourly stepping without replaying
        every missed hour. Persistent crops, fire, fluids and contamination still
        change, but the cost is proportional to realized state rather than elapsed
        wall-clock seconds.
        """
        hours=max(0,(end_minute-start_minute)//60)
        if hours<=0:return
        minute=end_minute
        for key,c in list(self.state.crops.items()):
            crop=self.registry.crops.get(c.crop_id)
            if not crop:continue
            w=self.weather.at(minute,c.x,c.y)
            rain_hours=min(hours,24)
            c.moisture=max(0,min(100,c.moisture+w["rain"]*rain_hours-crop.water_use*hours))
            day=minute//1440;season=("spring","summer","autumn","winter")[(day//30)%4]
            if self.world is not None and int(getattr(self.world.generator,"version",0))>=8:
                fields=self.world.generator.sample_fields(WorldPos(c.x,c.y,0))
                climate=-18+(int(fields.temperature)*63)//Q+int(w["temp_delta"])
            else:
                climate=(hash_u64(self.seed,"temp",c.x//64,c.y//64)%60)+15+w["temp_delta"]
            soil=self.state.soils.get(key)
            stress=0
            if not (crop.min_temp<=climate<=crop.max_temp):stress+=hours//2
            if c.moisture<15 or c.moisture>92:stress+=hours//3
            cycles=max(0,hours//6)
            if soil and cycles:
                n_use,p_use,k_use=(crop.nitrogen,crop.phosphorus,crop.potassium)
                soil.nitrogen=max(0,soil.nitrogen-n_use*cycles);soil.phosphorus=max(0,soil.phosphorus-p_use*cycles);soil.potassium=max(0,soil.potassium-k_use*cycles)
                nutrient=min(soil.nitrogen,soil.phosphorus,soil.potassium)
                c.disease=min(100,max(c.disease,soil.disease_pressure)+(cycles if c.moisture>88 else 0))
                if nutrient<20:stress+=cycles*3
                elif nutrient<40:stress+=cycles
            if stress:c.health=max(0,c.health-stress)
            else:c.health=min(100,c.health+max(1,hours//4))
            if c.health>0 and season in crop.seasons:
                nutrient_bonus=0 if not soil else min(3,min(soil.nitrogen,soil.phosphorus,soil.potassium)//25)
                c.growth+=hours*max(1,c.health//25+nutrient_bonus)
            if c.growth>=crop.growth_hours*4:c.mature=True
        # Coarse fire burns down rather than branching through hundreds of missed
        # hourly spread rolls. One deterministic spread/flow step per block keeps
        # persistent hazards alive without pathological catch-up work.
        for f in list(self.state.fires.values()):
            f.fuel=max(0,f.fuel-max(1,hours*2));f.intensity=max(0,f.intensity-max(1,hours//2))
        self._spread_fire(minute)
        for _ in range(min(4,max(1,hours//6))):self._flow_fluids()
        for k in [k for k,v in self.state.fires.items() if v.fuel<=0 or v.intensity<=0]:self.state.fires.pop(k,None)

    def daily_update(self,minute:int)->None:
        # Human/animal epidemiology is owned by EpidemiologySystem.  Keeping the
        # environment cadence separate prevents weather/crop code from mutating
        # settlement disease state merely because a renderer or tool touches it.
        return

    def _spread_fire(self,minute:int)->None:
        additions={};removals=[]
        for key,f in list(self.state.fires.items()):
            weather=self.weather.at(minute,f.x,f.y)
            rain=int(weather.get("rain",0) or 0)
            if rain:
                f.intensity=max(0,f.intensity-rain*2)
                f.fuel=max(0,f.fuel-rain)
            f.fuel-=max(1,f.intensity//10);f.intensity=max(0,f.intensity-2)
            struct=self.state.structures.get(key)
            if struct and "flammable" in self.registry.structures[struct.structure_id].tags:
                struct.condition-=max(1,f.intensity//8)
                if struct.condition<=0:
                    name=self.registry.structures[struct.structure_id].name;self.state.structures.pop(key,None);self.state.containers.pop(key,None);self.history.record("structure_fire",f"{name} burned down.",minute,f.x//512,f.y//512,salience=15)
            roof=self.state.roofs.get(key)
            if roof and "flammable" in self.registry.structures[roof.structure_id].tags:
                roof.condition-=max(1,f.intensity//10)
                if roof.condition<=0:
                    name=self.registry.structures[roof.structure_id].name;self.state.roofs.pop(key,None);self.history.record("roof_fire",f"{name} burned away.",minute,f.x//512,f.y//512,salience=10)
            if f.fuel<=0 or f.intensity<=0:removals.append(key);continue
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                if hash_u64(self.seed,"fire-spread",minute//60,f.x,f.y,dx,dy)%100<min(40,f.intensity//3):
                    nk=pos_key(f.x+dx,f.y+dy,f.z)
                    if nk not in self.state.fires:additions[nk]=FireCell(f.x+dx,f.y+dy,f.z,max(10,f.intensity//2),40)
        for k in removals:self.state.fires.pop(k,None)
        self.state.fires.update(additions)
    def _flow_fluids(self)->None:
        # intentionally cellular and bounded: only realized fluid cells move
        changes=[]
        for key,f in list(self.state.fluids.items()):
            if f.amount<8:continue
            below=pos_key(f.x,f.y,f.z-1)
            if below in self.state.fluids:
                dst=self.state.fluids[below];m=min(20,f.amount//4);f.amount-=m;dst.amount=min(255,dst.amount+m)
            else:
                # horizontal equalization to a deterministic neighbor
                dx=1 if (f.x+f.y)%2==0 else -1; nk=pos_key(f.x+dx,f.y,f.z);changes.append((nk,f,8))
        for nk,src,m in changes:
            if src.amount<m:continue
            src.amount-=m
            if nk in self.state.fluids:self.state.fluids[nk].amount=min(255,self.state.fluids[nk].amount+m)
            else:
                x,y,z=(int(v) for v in nk.split(','));self.state.fluids[nk]=FluidCell(x,y,z,src.fluid,m,src.contamination)
        for k in [k for k,v in self.state.fluids.items() if v.amount<=0]:self.state.fluids.pop(k,None)
    def _update_disease(self,minute:int)->None:
        for d in self.state.diseases.values():
            s=None
            for town in self.state.settlements.values():
                if (town.region_x,town.region_y)==(d.region_x,d.region_y):s=town;break
            if not s:continue
            susceptible=max(0,s.population-d.infected);new=min(susceptible,(d.infected*d.contagiousness)//1000);recover=max(1,d.infected//20)
            d.infected=max(0,d.infected+new-recover)
            if d.infected and minute%(7*1440)==0 and d.severity>60 and s.population>5:s.population-=1

    def fluid_at(self,pos:WorldPos):
        return self.state.fluids.get(pos_key(pos.x,pos.y,pos.z))
    def fluid_passable(self,pos:WorldPos)->bool:
        f=self.fluid_at(pos);return f is None or f.amount<220

    def ignite(self,pos:WorldPos,intensity:int=70)->None:self.state.fires[pos_key(pos.x,pos.y,pos.z)]=FireCell(pos.x,pos.y,pos.z,intensity,80)
    def add_water(self,pos:WorldPos,amount:int=120)->None:self.state.fluids[pos_key(pos.x,pos.y,pos.z)]=FluidCell(pos.x,pos.y,pos.z,"water",min(255,amount),0)
