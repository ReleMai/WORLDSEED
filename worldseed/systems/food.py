from __future__ import annotations
from collections import Counter
from worldseed.content.registry import ContentRegistry, CookingMethodDef
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.state import LivingWorldState, PreparedMealState

FOOD_GROUPS=("protein","vegetable","grain","fruit","fats")

class NutritionSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry):self.state=state;self.registry=registry

    def _record(self,minute:int,name:str,calories:int,protein:int,carbs:int,fat:int,fiber:int,groups:dict[str,int]):
        self.state.player_diet_history.append({"minute":int(minute),"name":name,"calories":int(calories),"protein":int(protein),"carbs":int(carbs),"fat":int(fat),"fiber":int(fiber),"groups":dict(groups)})
        cutoff=minute-7*1440
        self.state.player_diet_history=[r for r in self.state.player_diet_history[-300:] if int(r.get("minute",0))>=cutoff]

    def _apply_groups(self,groups:dict[str,int]):
        for g,amount in groups.items():
            if g in FOOD_GROUPS:self.state.player_nutrition[g]=min(100,int(self.state.player_nutrition.get(g,0))+max(1,int(amount)))

    def consume_item(self,item_id:str,v:Vitals,minute:int)->str:
        item=self.registry.items[item_id]
        v.hunger=max(0,v.hunger-item.nutrition);v.thirst=max(0,v.thirst-item.hydration)
        groups={g:max(2,item.nutrition//2) for g in item.food_groups}
        self._apply_groups(groups);self._record(minute,item.name,item.calories,item.protein,item.carbs,item.fat,item.fiber,groups)
        self._derive_effects(minute)
        return f"You eat {item.name.lower()}."

    def consume_meal(self,meal:PreparedMealState,v:Vitals,minute:int)->str:
        v.hunger=max(0,v.hunger-meal.satiety);v.thirst=max(0,v.thirst-meal.hydration)
        self._apply_groups(meal.food_groups);self._record(minute,meal.name,meal.calories,meal.protein,meal.carbs,meal.fat,meal.fiber,meal.food_groups)
        for effect,duration in meal.effects.items():self.state.player_food_effects[effect]=max(self.state.player_food_effects.get(effect,0),minute+duration)
        self._derive_effects(minute)
        return f"You eat a portion of {meal.name.lower()}."

    def daily_update(self,minute:int)->None:
        for g in FOOD_GROUPS:self.state.player_nutrition[g]=max(0,int(self.state.player_nutrition.get(g,0))-4)
        self.state.player_food_effects={k:v for k,v in self.state.player_food_effects.items() if int(v)>minute}
        cutoff=minute-7*1440;self.state.player_diet_history=[r for r in self.state.player_diet_history[-300:] if int(r.get('minute',0))>=cutoff]

    def _derive_effects(self,minute:int)->None:
        vals=[int(self.state.player_nutrition.get(g,0)) for g in FOOD_GROUPS]
        if sum(v>=45 for v in vals)>=4:self.state.player_food_effects['well_fed']=max(self.state.player_food_effects.get('well_fed',0),minute+8*60)
        recent=[r for r in self.state.player_diet_history if int(r.get('minute',0))>=minute-2*1440]
        protein=sum(int(r.get('protein',0)) for r in recent);carbs=sum(int(r.get('carbs',0)) for r in recent);fat=sum(int(r.get('fat',0)) for r in recent)
        if protein>=90:self.state.player_food_effects['recovery']=max(self.state.player_food_effects.get('recovery',0),minute+6*60)
        if carbs>=120:self.state.player_food_effects['stamina']=max(self.state.player_food_effects.get('stamina',0),minute+6*60)
        if fat>=70:self.state.player_food_effects['cold_resist']=max(self.state.player_food_effects.get('cold_resist',0),minute+4*60)

    def seven_day_totals(self,minute:int)->dict:
        cutoff=minute-7*1440;rows=[r for r in self.state.player_diet_history if int(r.get('minute',0))>=cutoff]
        return {k:sum(int(r.get(k,0)) for r in rows) for k in ('calories','protein','carbs','fat','fiber')} | {"meals":len(rows)}

class CookingSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,nutrition:NutritionSystem):self.state=state;self.registry=registry;self.nutrition=nutrition

    def can_cook(self,method_id:str,ingredients:list[str],inv:Inventory,stations:set[str],water_available:bool)->tuple[bool,str]:
        method=self.registry.cooking_methods.get(method_id)
        if not method:return False,"Unknown cooking method."
        if method.station not in stations:return False,f"Requires {self.registry.structures[method.station].name}."
        if method.cookware and inv.count(method.cookware)<=0:return False,f"Requires {self.registry.items[method.cookware].name}."
        if method.requires_water and not water_available:return False,"You need clean or accessible water."
        if not (method.min_ingredients<=len(ingredients)<=method.max_ingredients):return False,f"Choose {method.min_ingredients}-{method.max_ingredients} ingredients."
        counts=Counter(ingredients)
        for iid,n in counts.items():
            item=self.registry.items.get(iid)
            if not item or inv.count(iid)<n:return False,"You do not have those ingredients."
            if not set(item.tags).intersection(method.allowed_tags):return False,f"{item.name} does not suit this cooking method."
        # Broth specifically needs at least one body/herb/vegetable contribution; porridge requires grain.
        if method_id=='core:porridge' and not any('grain' in self.registry.items[i].tags for i in ingredients):return False,"Porridge needs grain."
        if method_id=='core:broth' and not any(set(self.registry.items[i].tags)&{'bone','offal','herb','vegetable','mushroom'} for i in ingredients):return False,"Broth needs bones, organs, herbs, or vegetables."
        return True,""

    def preview(self,method_id:str,ingredients:list[str])->dict:
        method=self.registry.cooking_methods[method_id];items=[self.registry.items[i] for i in ingredients]
        sat=sum(max(1,i.nutrition) for i in items)*method.satiety_percent//100
        hyd=sum(i.hydration for i in items)+method.hydration_bonus
        calories=sum(i.calories for i in items)*method.satiety_percent//100
        protein=sum(i.protein for i in items);carbs=sum(i.carbs for i in items);fat=sum(i.fat for i in items);fiber=sum(i.fiber for i in items)
        groups={}
        for i in items:
            for g in i.food_groups:groups[g]=groups.get(g,0)+max(2,i.nutrition//2)
        return {'satiety':sat,'hydration':hyd,'calories':calories,'protein':protein,'carbs':carbs,'fat':fat,'fiber':fiber,'groups':groups}

    def meal_name(self,method_id:str,ingredients:list[str])->str:
        method=self.registry.cooking_methods[method_id];names=[]
        for iid in ingredients:
            n=self.registry.items[iid].name.replace('Raw ','').replace('Wild ','')
            if n not in names:names.append(n)
        if method_id=='core:porridge':
            base=next((self.registry.items[i].name for i in ingredients if 'grain' in self.registry.items[i].tags),'Grain')
            extras=[self.registry.items[i].name for i in ingredients if 'grain' not in self.registry.items[i].tags]
            return f"{base} Porridge"+(f" with {extras[0]}" if extras else '')
        lead=' & '.join(names[:2]) if names else 'Camp'
        return f"{lead} {method.name}"

    def cook(self,method_id:str,ingredients:list[str],inv:Inventory,stations:set[str],water_available:bool,minute:int)->tuple[bool,str,int,str|None]:
        ok,why=self.can_cook(method_id,ingredients,inv,stations,water_available)
        if not ok:return False,why,0,None
        for iid,n in Counter(ingredients).items():inv.remove(iid,n)
        method=self.registry.cooking_methods[method_id];stats=self.preview(method_id,ingredients);uid=self.state.uid('meal');name=self.meal_name(method_id,ingredients)
        effects={}
        if method.effect=='warming':effects['cold_resist']=180
        elif method.effect=='recovery':effects['recovery']=300
        elif method.effect=='stamina':effects['stamina']=300
        # Prepared food is deliberately more perishable than preserved food.
        # The shelf life depends on method rather than being a universal cooked-food timer.
        shelf_hours={'core:roast':24,'core:stew':36,'core:porridge':30,'core:broth':20}.get(method_id,24)
        spoil_minute=minute+shelf_hours*60
        self.state.prepared_meals[uid]=PreparedMealState(uid,name,method_id,'player',minute,list(ingredients),2 if len(ingredients)>=3 else 1,stats['satiety'],stats['hydration'],stats['calories'],stats['protein'],stats['carbs'],stats['fat'],stats['fiber'],stats['groups'],effects,spoil_minute)
        return True,f"You prepare {name.lower()} ({self.state.prepared_meals[uid].portions} portion(s)).",method.minutes,uid
