import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from worldseed.content.item_catalog import canonical_item_catalog
DATA=ROOT/'worldseed'/'data'

def load(name): return json.loads((DATA/name).read_text())
def save(name,data):
    if name=='items.json':data=canonical_item_catalog(data)
    (DATA/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding='utf-8')

def upsert(rows,row):
    for i,x in enumerate(rows):
        if x['id']==row['id']:
            y=dict(x); y.update(row)
            # Preserve modern canonical authoring fields when this legacy
            # enrichment tool is rerun.
            for field in ('name','category','subcategory','asset'):
                if field in x: y[field]=x[field]
            rows[i]=y; return
    rows.append(row)

def item(i,n,mat='core:organic',mass=100,vol=100,tags=(),desc='',flavor='',cat='misc',roles=(),**kw):
    r={'id':i,'name':n,'asset':i.split(':',1)[-1],'material':mat,'mass_g':mass,'volume_ml':vol,'tags':list(tags),'description':desc or f'{n} is a practical material of the living world.','flavor':flavor or f'"Every scrap of {n.lower()} has a use to someone patient enough to find it."','category':cat,'utility_roles':list(roles)}
    r.update(kw); return r

items=load('items.json')
# Enrich old items with readable descriptions/flavor and role hints.
old_roles={
'core:wood':['fuel','construction','craft_input'],'core:stone':['construction','primitive_craft','masonry'],'core:brush':['fuel','cordage_input','bedding'],
'core:fiber':['cordage','craft_input'],'core:berries':['raw_food','cooking'],'core:meat':['raw_food','cooking'],'core:cooked_meat':['food'],
'core:hide':['legacy_leather_input'],'core:bone':['craft_input','fertilizer','broth'],'core:iron_ore':['smelting'],'core:coal':['fuel','smelting'],
'core:iron_bloom':['metalworking'],'core:steel_billet':['metalworking'],'core:copper_coin':['currency'],'core:book':['knowledge'],
'core:parchment':['writing'],'core:bone_meal':['fertilizer'],'core:medicinal_herb':['medicine','cooking'],'core:soap':['sanitation'],
'core:clean_water':['drink','cooking'],'core:waterskin':['drink'],'core:wheat':['food','cooking'],'core:turnip':['food','cooking'],
}
for r in items:
    r.setdefault('description',f"{r['name']} has a clear practical place in survival, craft, trade, or daily life.")
    r.setdefault('flavor',f'"{r["name"]}: ordinary in isolation, important when the right need appears."')
    r.setdefault('category','equipment' if any(t in r.get('tags',[]) for t in ('tool','weapon','armor')) else 'material')
    r.setdefault('utility_roles',old_roles.get(r['id'],list(r.get('tags',[]))))
    if r.get('nutrition',0)>0:
        r.setdefault('calories',r['nutrition']*12); r.setdefault('food_groups',['protein'] if 'meat' in r['id'] else ['grain'] if 'wheat' in r['id'] else ['vegetable'] if 'turnip' in r['id'] else ['fruit'])
        r.setdefault('protein',12 if 'meat' in r['id'] else 2);r.setdefault('carbs',18 if any(x in r['id'] for x in ('wheat','turnip','berries')) else 0);r.setdefault('fat',5 if 'meat' in r['id'] else 0);r.setdefault('fiber',4 if any(x in r['id'] for x in ('berries','turnip','wheat')) else 0)
    # bridge old tools into qualities
    tq=dict(r.get('tool_qualities',{}))
    if 'axe' in r.get('tags',[]): tq.setdefault('chop',r.get('tool_power',1))
    if 'pick' in r.get('tags',[]): tq.setdefault('mine',r.get('tool_power',1))
    if r.get('damage_type')=='cut': tq.setdefault('cut',max(1,r.get('weapon_damage',4)//4))
    if tq:r['tool_qualities']=tq

new=[
item('core:stout_branch','Stout Branch','core:wood',700,900,['raw','wood','branch','fuel'],'A straight fallen branch thick enough to become a haft, spear shaft, firewood, or frame member.','"A useful branch is already half a tool."','natural',['primitive_craft','fuel','construction']),
item('core:bark','Tannin-Rich Bark','core:wood',250,450,['raw','bark','tannin','fuel'],'Strips of bark rich in tannins, useful for cordage, fire-starting, and preserving hides.','"The tree gives more than timber."','natural',['cordage_input','tanning','fuel']),
item('core:reed_bundle','Reed Bundle','core:fiber',300,1200,['raw','fiber','reed','fuel'],'Long wetland reeds suitable for mats, baskets, thatching, cordage, and kindling.','"Where the ground is too wet for grass, reeds do the building."','natural',['weaving','construction','fuel']),
item('core:clay_lump','Clay Lump','core:clay',1000,700,['raw','clay'],'Plastic clay dug from damp ground, ready to be shaped and fired.','"Mud remembers the hands that shaped it."','natural',['pottery','construction']),
item('core:stone_flake','Sharp Stone Flake','core:stone',180,80,['tool','primitive','sharp'],'A deliberately struck stone flake with a keen but fragile edge.','"The first blade needed no forge."','tool',['cutting','primitive_craft'],tool_qualities={'cut':1,'skin':1,'scrape':1},weapon_damage=2,damage_type='cut'),
item('core:plant_cordage','Plant Cordage','core:fiber',120,180,['craft','cordage'],'Twisted plant fibers strong enough for bindings, snares, lashings, and primitive tools.','"Strength made from many weak fibers."','material',['binding','construction','toolmaking']),
item('core:sinew','Sinew','core:organic',90,100,['animal','fiber','sinew'],'Cleaned tendon fibers valued for compact, very strong bindings and bow work.','"Pulled from bone, stronger than it looks."','animal_product',['binding','bowmaking','sewing']),
item('core:sinew_cord','Sinew Cord','core:organic',80,90,['craft','cordage','sinew'],'Tightly twisted sinew cord with excellent tensile strength.','"It dries hard and holds harder."','material',['binding','bowmaking']),
item('core:animal_fat','Rendered Animal Fat','core:organic',250,260,['food','fat','animal'],'Dense animal fat useful for cooking, soap, sealing, and calorie-rich meals.','"Winter stores itself under the hide."','food',['cooking','soap','preservation'],nutrition=12,calories=280,protein=0,carbs=0,fat=28,fiber=0,food_groups=['fats']),
item('core:offal','Fresh Offal','core:organic',350,330,['food','raw_meat','offal','animal'],'Nutrient-dense organs that spoil quickly but enrich broths and survival meals.','"Waste to the careless; strength to the hungry."','food',['cooking'],nutrition=14,calories=190,protein=20,carbs=2,fat=10,food_groups=['protein']),
item('core:fresh_hide','Fresh Hide','core:leather',1200,2100,['animal','hide','fresh'],'Unprocessed hide, heavy with moisture and vulnerable to rot until scraped and preserved.','"A skin is not leather until work makes it so."','animal_product',['hide_processing']),
item('core:scraped_hide','Scraped Hide','core:leather',1000,1800,['animal','hide','scraped'],'A cleaned hide with flesh and membrane removed, ready for drying or tanning.','"The blade work shows in every clean patch."','animal_product',['drying','tanning']),
item('core:rawhide','Rawhide Sheet','core:leather',850,1400,['craft','rawhide'],'A stiff dried hide useful for shields, lashings, containers, and hard-wearing camp gear.','"Hard as old bark when dry, pliable when soaked."','material',['armor','binding','containers']),
item('core:leather','Tanned Leather','core:leather',750,1250,['craft','leather'],'Flexible preserved hide suitable for clothing, armor, containers, straps, and fine work.','"Time, bark, water, and patience make skin endure."','material',['armor','clothing','containers','craft_input']),
item('core:feather','Flight Feather','core:organic',10,35,['animal','feather'],'A stiff flight feather suitable for arrow fletching, bedding, and decorative work.','"A small piece of the sky left behind."','animal_product',['fletching','bedding']),
item('core:stone_knife','Stone Knife','core:stone',420,300,['tool','knife','weapon','primitive'],'A flaked stone blade lashed to a short handle. Essential for carcass work and hide preparation.','"Ugly edges still cut cleanly."','tool',['hunting','butchery','hide_processing'],tool_qualities={'cut':2,'skin':2,'butcher':2,'scrape':2},weapon_damage=4,damage_type='cut'),
item('core:stone_pick','Stone Pick','core:stone',1800,1400,['tool','pick','weapon','primitive'],'A heavy stone head bound to a stout branch for breaking softer rock and opening shallow workings.','"The mountain yields first to persistence, then to metal."','tool',['mining'],tool_qualities={'mine':2,'hammer':1},tool_power=2,weapon_damage=5,damage_type='blunt'),
item('core:stone_hammer','Stone Hammer','core:stone',1500,1050,['tool','hammer','weapon','primitive'],'A rounded stone hammer for construction, crushing bone, and rough craft.','"Simple weight, carefully directed."','tool',['construction','processing'],tool_qualities={'hammer':2,'crush':2},weapon_damage=5,damage_type='blunt'),
item('core:digging_stick','Digging Stick','core:wood',900,950,['tool','dig','primitive'],'A fire-hardened stick used to loosen soil, pry roots, and begin primitive farming.','"The first plow was a branch and stubborn hands."','tool',['farming','foraging'],tool_qualities={'dig':1,'till':1}),
item('core:crude_hoe','Crude Stone Hoe','core:stone',1350,1200,['tool','hoe','primitive'],'A broad stone edge lashed to a handle for turning soil more efficiently than a digging stick.','"A field begins one broken clod at a time."','tool',['farming'],tool_qualities={'till':2,'dig':1}),
item('core:wooden_spear','Fire-Hardened Spear','core:wood',1300,1800,['weapon','spear','primitive'],'A straight branch with a hardened point. Crude, reachy, and far safer than empty hands against game.','"Keep the teeth at the far end of the shaft."','weapon',['hunting','combat'],weapon_damage=7,damage_type='pierce',range=2),
item('core:club','Heavy Club','core:wood',1500,1400,['weapon','primitive'],'A dense branch trimmed into a brutal close-quarters weapon and pounding tool.','"No edge to dull, only weight to swing."','weapon',['combat'],weapon_damage=6,damage_type='blunt'),
item('core:sling','Fiber Sling','core:fiber',140,120,['weapon','ranged','primitive'],'A braided sling that turns smooth stones into useful small-game ammunition.','"A stone travels farther when the cord lends it speed."','weapon',['hunting','ranged_combat'],weapon_damage=5,damage_type='blunt',range=6,ammo_item='core:sling_stone'),
item('core:sling_stone','Sling Stone','core:stone',80,35,['ammo','stone'],'A smooth palm-sized stone selected for consistent sling flight.','"The best ammunition is often underfoot."','ammo',['ranged_ammo']),
item('core:short_bow','Short Hunting Bow','core:wood',900,1300,['weapon','ranged','bow'],'A compact sinew-backed hunting bow suited to woods and close stalking.','"A bent stave stores patience as force."','weapon',['hunting','ranged_combat'],weapon_damage=8,damage_type='pierce',range=9,ammo_item='core:wood_arrow'),
item('core:wood_arrow','Stone-Tipped Arrow','core:wood',45,35,['ammo','arrow'],'A light shaft with stone point and feather fletching.','"Straight wood, sharp stone, steady breath."','ammo',['ranged_ammo']),
item('core:bone_awl','Bone Awl','core:bone',90,40,['tool','awl'],'A polished bone point for piercing leather, bark, and woven material.','"A little point opens the way for thread."','tool',['leatherwork','basketry'],tool_qualities={'sew':1,'pierce':2}),
item('core:bone_needle','Bone Needle','core:bone',25,10,['tool','needle'],'A fine drilled bone needle for stitched leather, cloth, and careful repairs.','"Small enough to lose, important enough to mourn."','tool',['sewing'],tool_qualities={'sew':2}),
item('core:rawhide_buckler','Rawhide Buckler','core:leather',1800,1500,['armor','shield','rawhide'],'A light wooden-and-rawhide hand shield that turns glancing blows aside.','"Not a wall, just enough between you and the teeth."','armor',['combat'],base_value=18,equip_slot='offhand',armor=5,coverage=['left_arm']),
item('core:clay_pot','Fired Clay Cooking Pot','core:clay',1700,1700,['cookware','pot'],'A fire-safe clay pot for stews, broths, porridges, boiling water, and rendering fat.','"A pot turns scattered ingredients into a meal."','tool',['cooking']),
item('core:wooden_bowl','Wooden Bowl','core:wood',250,450,['container','bowl'],'A carved bowl for eating meals, collecting ingredients, and simple camp use.','"The shape of hunger answered in wood."','tool',['cooking','serving']),
item('core:raw_small_game','Small-Game Meat','core:organic',350,320,['food','raw_meat','protein'],'Lean meat from rabbit, hare, or similar small game. Best cooked before eating.','"Small prey feeds a careful hunter."','food',['cooking','drying'],nutrition=14,calories=170,protein=28,carbs=0,fat=5,fiber=0,food_groups=['protein']),
item('core:raw_game_meat','Red Game Meat','core:organic',500,450,['food','raw_meat','protein'],'Dense red meat from deer, elk, boar, or other large game.','"A day of tracking condensed into a heavy cut of meat."','food',['cooking','drying'],nutrition=18,calories=260,protein=32,carbs=0,fat=13,fiber=0,food_groups=['protein']),
item('core:raw_poultry','Raw Poultry','core:organic',400,360,['food','raw_meat','poultry','protein'],'Light meat from wild birds, tender but quick to spoil.','"Feathers on the ground, supper in the pot."','food',['cooking','drying'],nutrition=16,calories=210,protein=30,carbs=0,fat=8,fiber=0,food_groups=['protein']),
item('core:dried_meat','Dried Meat','core:organic',220,210,['food','preserved','protein'],'Thin strips of meat dried until light, chewy, and resistant to spoilage.','"Hard travel food that asks only strong teeth."','food',['food','travel'],nutrition=24,calories=280,protein=40,carbs=0,fat=9,fiber=0,food_groups=['protein'],spoilage_hours=720),
item('core:blueberries','Blueberries','core:organic',120,140,['food','fruit','forage'],'Dark wild berries with tart sweetness and useful moisture.','"A handful stains the fingers and brightens a lean meal."','food',['raw_food','cooking'],nutrition=10,hydration=5,calories=65,protein=1,carbs=15,fat=0,fiber=4,food_groups=['fruit']),
item('core:raspberries','Raspberries','core:organic',120,150,['food','fruit','forage'],'Soft red berries that bruise easily and reward careful gathering.','"Sweet enough that birds always arrive first."','food',['raw_food','cooking'],nutrition=10,hydration=5,calories=70,protein=1,carbs=16,fat=0,fiber=5,food_groups=['fruit']),
item('core:wild_strawberries','Wild Strawberries','core:organic',100,120,['food','fruit','forage'],'Small fragrant berries growing close to sunny ground.','"Tiny fruit with a summer larger than itself."','food',['raw_food','cooking'],nutrition=9,hydration=5,calories=55,protein=1,carbs=13,fat=0,fiber=3,food_groups=['fruit']),
item('core:dandelion_greens','Dandelion Greens','core:organic',100,160,['food','vegetable','forage','herb'],'Bitter young greens that add fiber and vitamins to soups and stews.','"The weed survives because it knows the world better than gardeners do."','food',['raw_food','cooking'],nutrition=8,hydration=4,calories=35,protein=2,carbs=7,fat=0,fiber=4,food_groups=['vegetable']),
item('core:nettles','Nettle Leaves','core:organic',100,200,['food','vegetable','forage','fiber_plant'],'Stinging leaves that become edible when cooked and useful as coarse fiber when processed.','"Handle badly and it bites; handle well and it feeds."','food',['cooking','fiber'],nutrition=9,calories=45,protein=4,carbs=7,fat=0,fiber=5,food_groups=['vegetable']),
item('core:wild_onion','Wild Onion','core:organic',130,140,['food','vegetable','forage','root'],'Sharp wild bulbs that flavor meals and can yield seed for cultivation.','"A small bulb with enough scent to announce dinner."','food',['raw_food','cooking','seed_source'],nutrition=10,hydration=3,calories=60,protein=2,carbs=14,fat=0,fiber=3,food_groups=['vegetable']),
item('core:wild_carrot','Wild Carrot Root','core:organic',150,160,['food','vegetable','forage','root'],'A pale tough root, less sweet than cultivated carrot but dependable.','"Pulled from stubborn ground, still worth the dirt under the nails."','food',['raw_food','cooking','seed_source'],nutrition=11,hydration=4,calories=70,protein=1,carbs=16,fat=0,fiber=4,food_groups=['vegetable']),
item('core:yarrow','Yarrow','core:organic',50,90,['herb','medical','forage'],'A pungent flowering herb traditionally valued in field dressings and bitter infusions.','"White flowers above, old fieldcraft below."','herb',['medicine','cooking']),
item('core:plantain_leaf','Broadleaf Plantain','core:organic',70,120,['herb','medical','forage'],'Broad resilient leaves useful in simple poultices and herb mixtures.','"It grows where boots pass and survives because of it."','herb',['medicine','cooking']),
item('core:morel','Morel Mushroom','core:organic',90,110,['food','vegetable','mushroom','forage'],'A honeycombed woodland mushroom, valuable cooked and risky to waste.','"The forest hides good food in shapes that look improbable."','food',['cooking'],nutrition=8,calories=45,protein=3,carbs=7,fat=1,fiber=3,food_groups=['vegetable']),
item('core:bolete','Bolete Mushroom','core:organic',120,140,['food','vegetable','mushroom','forage'],'A firm woodland mushroom well suited to broths and stews.','"A quiet cap beneath old trees."','food',['cooking'],nutrition=9,calories=55,protein=4,carbs=8,fat=1,fiber=3,food_groups=['vegetable']),
item('core:wild_grain','Wild Grain Heads','core:organic',120,150,['food','grain','forage'],'Loose heads of wild cereal grain, sparse but enough to seed the first field.','"Civilization begins when someone saves a handful instead of eating it."','food',['cooking','seed_source'],nutrition=11,calories=130,protein=4,carbs=27,fat=1,fiber=4,food_groups=['grain']),
item('core:cattail_root','Cattail Root','core:organic',220,260,['food','vegetable','wetland','forage'],'A starchy wetland rhizome that becomes much more pleasant after cooking.','"The marsh keeps its starch underground."','food',['cooking'],nutrition=13,hydration=3,calories=120,protein=2,carbs=28,fat=0,fiber=5,food_groups=['vegetable']),
]
# Crop items + seeds
for key,name,group,cal,p,c,fib in [
('barley','Barley','grain',140,4,28,5),('beans','Field Beans','protein',150,9,24,7),('cabbage','Cabbage','vegetable',45,2,9,4),('carrot','Carrot','vegetable',65,1,15,4),('onion','Onion','vegetable',55,1,13,3),('flax','Flax Seed','grain',160,6,20,6)]:
    seed_id='core:'+('flax_seed' if key=='flax' else f'{key}_seed')
    food_id='core:'+key
    new.append(item(seed_id,name+' Seed','core:organic',20,15,['seed'],f'Seed saved for planting {name.lower()}.',f'"A future field carried in the palm."','seed',['planting']))
    new.append(item(food_id,name,'core:organic',100,120,['food','crop',group],f'Harvested {name.lower()} suitable for cooking, storage, and seed-saving.',f'"A field turns weather and soil into something you can carry."','food',['cooking'],nutrition=12,calories=cal,protein=p,carbs=c,fat=2 if key in ('beans','flax') else 0,fiber=fib,food_groups=[group]))
for r in new: upsert(items,r)
save('items.json',items)

# Recipes
recipes=load('recipes.json')
# Make legacy recipe descriptions/category useful.
for r in recipes:
    r.setdefault('description',f"Use available materials and time to produce {r['name'].lower()}.")
    r.setdefault('category','advanced' if r.get('station')=='core:forge' else 'general')
    r.setdefault('skill','crafting');r.setdefault('difficulty',1 if not r.get('station') else 3);r.setdefault('tool_qualities',{})
# Primitive chain
primitive=[
('core:stone_flake','Strike Stone Flake',{'core:stone':1},{'core:stone_flake':2},8,None,'primitive','Knock a sharp flake from a suitable stone. The edge is fragile, but it can cut fiber, skin small game, and start better tools.',{}),
('core:plant_cordage','Twist Plant Cordage',{'core:brush':2},{'core:plant_cordage':1},12,None,'primitive','Twist dry fibers and bark strands into binding cord.',{}),
('core:bark_cordage','Twist Bark Cordage',{'core:bark':2},{'core:plant_cordage':1},18,None,'primitive','Pound and twist inner bark fibers into rough cord.',{}),
('core:stone_knife','Make Stone Knife',{'core:stone_flake':1,'core:stout_branch':1,'core:plant_cordage':1},{'core:stone_knife':1},25,None,'primitive_tools','Lash a sharp flake to a short haft for the first serious cutting tool.',{}),
('core:stone_axe_rc7','Make Stone Axe',{'core:stone_flake':2,'core:stout_branch':1,'core:plant_cordage':1},{'core:stone_axe':1},35,None,'primitive_tools','Bind a heavy cutting edge to a branch so mature timber can be felled.',{'hammer':0}),
('core:stone_pick','Make Stone Pick',{'core:stone':2,'core:stout_branch':1,'core:plant_cordage':1},{'core:stone_pick':1},45,None,'primitive_tools','Build a crude pick capable of breaking cave rock and surface boulders.',{}),
('core:stone_hammer','Make Stone Hammer',{'core:stone':1,'core:stout_branch':1,'core:plant_cordage':1},{'core:stone_hammer':1},30,None,'primitive_tools','Lash a rounded hammerstone to a branch for building and processing.',{}),
('core:digging_stick','Fire-Harden Digging Stick',{'core:stout_branch':1},{'core:digging_stick':1},15,'core:campfire','primitive_tools','Harden and shape a branch into a basic soil-working tool.',{}),
('core:crude_hoe','Make Crude Hoe',{'core:stone_flake':1,'core:stout_branch':1,'core:plant_cordage':1},{'core:crude_hoe':1},30,None,'primitive_tools','Bind a broad stone edge for more efficient cultivation.',{}),
('core:wooden_spear','Make Fire-Hardened Spear',{'core:stout_branch':1},{'core:wooden_spear':1},20,'core:campfire','hunting','Sharpen and harden a long branch for defense and hunting.',{}),
('core:club','Shape Heavy Club',{'core:stout_branch':1},{'core:club':1},12,None,'weapons','Trim a dense branch into a simple striking weapon.',{}),
('core:sling','Braid Sling',{'core:plant_cordage':2},{'core:sling':1},20,None,'hunting','Braid a compact sling for small-game hunting at range.',{}),
('core:sling_stone','Select Sling Stones',{'core:stone':1},{'core:sling_stone':8},5,None,'hunting','Sort and shape small smooth stones for consistent sling flight.',{}),
('core:short_bow','Make Short Hunting Bow',{'core:wood':1,'core:sinew_cord':2},{'core:short_bow':1},90,'core:workbench','hunting','Shape a short stave and back it with sinew for a compact hunting bow.',{'cut':2}),
('core:wood_arrow','Make Stone-Tipped Arrows',{'core:stout_branch':1,'core:stone_flake':1,'core:feather':2,'core:plant_cordage':1},{'core:wood_arrow':4},35,None,'hunting','Straighten short shafts, bind stone points, and fletch them with feathers.',{'cut':1}),
('core:bone_awl','Shape Bone Awl',{'core:bone':1},{'core:bone_awl':1},25,'core:workbench','bonecraft','Polish bone into a strong piercing awl.',{'scrape':1}),
('core:bone_needle','Carve Bone Needle',{'core:bone':1},{'core:bone_needle':2},40,'core:workbench','bonecraft','Shape and drill fine bone needles for stitching.',{'cut':2}),
('core:sinew_cord','Twist Sinew Cord',{'core:sinew':2},{'core:sinew_cord':1},20,None,'leatherwork','Twist cleaned sinew into a compact strong cord.',{}),
('core:rawhide_buckler','Build Rawhide Buckler',{'core:rawhide':1,'core:wood':1,'core:plant_cordage':1},{'core:rawhide_buckler':1},60,'core:workbench','leatherwork','Stretch stiff rawhide across a light wooden frame.',{'cut':1}),
('core:clay_pot','Shape and Fire Clay Pot',{'core:clay_lump':2},{'core:clay_pot':1},120,'core:campfire','pottery','Shape a thick cooking pot and fire it slowly beside the coals.',{}),
('core:wooden_bowl','Carve Wooden Bowl',{'core:wood':1},{'core:wooden_bowl':1},45,'core:workbench','woodcraft','Hollow a small bowl from seasoned wood.',{'cut':2}),
('core:scrape_hide','Scrape Fresh Hide',{'core:fresh_hide':1},{'core:scraped_hide':1},35,None,'hide_processing','Remove membrane and clinging tissue before drying or tanning.',{'scrape':2}),
('core:sinew_from_offcuts','Clean Sinew',{'core:sinew':1},{'core:sinew':1},10,None,'hide_processing','Clean and separate tendon fibers for cordage.',{'cut':1}),
('core:soap_fat','Make Fat-and-Ash Soap',{'core:animal_fat':1,'core:wood':1},{'core:soap':2},75,'core:campfire','household','Render fat with alkaline wood ash into rough cleansing soap.',{}),
]
for rid,name,inputs,outputs,mins,station,cat,desc,tools in primitive:
    upsert(recipes,{'id':rid,'name':name,'inputs':inputs,'outputs':outputs,'minutes':mins,'station':station,'knowledge':None,'description':desc,'category':cat,'skill':'crafting','difficulty':1 if cat in ('primitive','primitive_tools') else 2,'tool_qualities':tools})
# Seed saving recipes (wild + crops)
seed_recipes=[('wild_onion','onion'),('wild_carrot','carrot'),('wild_grain','wheat')]
for wild,crop in seed_recipes:
    upsert(recipes,{'id':f'core:save_seed_{wild}','name':f'Save {crop.title()} Seed','inputs':{f'core:{wild}':1},'outputs':{f'core:{crop}_seed':2},'minutes':8,'description':'Select and dry viable seed instead of eating the entire find.','category':'farming','skill':'survival','difficulty':1,'tool_qualities':{}})
save('recipes.json',recipes)

# Structures
structures=load('structures.json')
for s in structures:
    s.setdefault('description',f"{s['name']} has a specific practical role in shelter, storage, work, or defense.")
    s.setdefault('uses',list(s.get('tags',[])));s.setdefault('comfort',0);s.setdefault('work_bonus',0);s.setdefault('warmth',0);s.setdefault('shelter',0)
    if s['id']=='core:campfire':
        s['cost']={'core:stone':2,'core:stout_branch':2,'core:brush':1};s['description']='A ring of stones around a controlled fire for warmth, roasting, boiling, hardening wood, and light.';s['uses']=['cooking','warmth','fire_hardening','light'];s['warmth']=12
    elif s['id']=='core:workbench':s['uses']=['crafting','toolmaking'];s['work_bonus']=15
    elif s['id']=='core:bed':s['uses']=['sleep','recovery'];s['comfort']=30
new_structs=[
{'id':'core:brush_lean_to','name':'Brush Lean-To','glyph':'/','passable':True,'blocks_sight':False,'cost':{'core:stout_branch':4,'core:brush':5,'core:plant_cordage':2},'tags':['shelter','flammable'],'description':'A sloped frame packed with brush that cuts wind and sheds light rain.','uses':['shelter','rest'],'comfort':8,'shelter':18},
{'id':'core:sleeping_mat','name':'Reed Sleeping Mat','glyph':'_','passable':True,'blocks_sight':False,'cost':{'core:reed_bundle':2,'core:plant_cordage':1},'tags':['furniture','bed','flammable'],'description':'A woven mat that keeps the body off cold damp ground.','uses':['sleep','recovery'],'comfort':12},
{'id':'core:storage_basket','name':'Woven Storage Basket','glyph':'u','passable':False,'blocks_sight':False,'cost':{'core:reed_bundle':2,'core:plant_cordage':1},'tags':['container','furniture','flammable'],'description':'A large woven basket for keeping food, tools, fibers, and camp clutter together.','uses':['storage'],'capacity_mass_g':35000,'capacity_volume_ml':70000},
{'id':'core:crude_work_surface','name':'Crude Work Surface','glyph':'w','passable':False,'blocks_sight':False,'cost':{'core:stout_branch':3,'core:plant_cordage':2},'tags':['station','furniture','flammable'],'description':'A lashed frame that raises cutting and assembly work off the ground.','uses':['crafting','toolmaking'],'work_bonus':8},
{'id':'core:butcher_table','name':'Butcher Table','glyph':'B','passable':False,'blocks_sight':False,'cost':{'core:wood':2,'core:stout_branch':2,'core:plant_cordage':1},'tags':['station','furniture','flammable'],'description':'A washable work surface for cleaner, more efficient carcass processing.','uses':['butchery','skinning','deboning'],'work_bonus':18},
{'id':'core:drying_rack','name':'Drying Rack','glyph':'H','passable':True,'blocks_sight':False,'cost':{'core:stout_branch':4,'core:plant_cordage':2},'tags':['station','flammable'],'description':'An elevated rack that lets air move around meat, herbs, and scraped hides.','uses':['drying','preservation'],'work_bonus':10},
{'id':'core:tanning_frame','name':'Tanning Frame','glyph':'A','passable':False,'blocks_sight':False,'cost':{'core:stout_branch':4,'core:plant_cordage':3},'tags':['station','flammable'],'description':'A stretched frame for working tannin solution through a prepared hide.','uses':['tanning','leatherwork'],'work_bonus':12},
{'id':'core:stone_hearth','name':'Stone Hearth','glyph':'*','passable':True,'blocks_sight':False,'cost':{'core:stone':6,'core:clay_lump':2},'tags':['station','fire'],'description':'A durable hearth that holds heat more evenly than an open campfire.','uses':['cooking','warmth','preservation'],'warmth':18,'work_bonus':8},
{'id':'core:reed_screen','name':'Reed Windbreak','glyph':':','passable':False,'blocks_sight':False,'cost':{'core:reed_bundle':3,'core:plant_cordage':2},'tags':['wall','flammable','shelter'],'description':'A woven panel that blocks wind without becoming a permanent wall.','uses':['windbreak','shelter'],'shelter':8,'support_strength':12},
]
for s in new_structs: upsert(structures,s)
save('structures.json',structures)

# Crops
crops=load('crops.json')
for c in crops:
    c.setdefault('nitrogen',4 if c['id']=='core:wheat' else 2);c.setdefault('phosphorus',2);c.setdefault('potassium',2);c.setdefault('disease_family','cereal' if c['id']=='core:wheat' else 'root');c.setdefault('description',f"A cultivated {c['name'].lower()} crop with its own soil and season demands.")
new_crops=[
('barley','Barley','core:barley_seed','core:barley',88,14,78,3,3,7,['spring','summer'],4,2,2,'cereal','A hardy cereal that matures quickly and tolerates cooler weather.'),
('beans','Field Beans','core:beans_seed','core:beans',82,18,82,4,3,6,['spring','summer'],1,3,3,'legume','A protein-rich legume that draws modest nitrogen and helps diversify rotations.'),
('cabbage','Cabbage','core:cabbage_seed','core:cabbage',90,12,72,5,2,5,['spring','autumn'],3,2,4,'brassica','A leafy vegetable that likes steady water and potassium-rich soil.'),
('carrot','Carrot','core:carrot_seed','core:carrot',76,12,78,3,3,6,['spring','summer','autumn'],2,3,4,'root','A root crop that rewards loose soil and steady moisture.'),
('onion','Onion','core:onion_seed','core:onion',80,14,82,3,3,6,['spring','summer'],2,3,3,'allium','A compact bulb crop useful raw, cooked, and as a reliable flavor base.'),
('flax','Flax','core:flax_seed','core:flax',92,16,80,4,3,6,['spring','summer'],3,2,3,'fiber','A dual-purpose seed and fiber crop valuable beyond food alone.'),
]
for key,name,seed,harv,grow,mn,mx,water,ymin,ymax,seasons,n,p,k,fam,desc in new_crops:
    upsert(crops,{'id':f'core:{key}','name':name,'seed_item':seed,'harvest_item':harv,'growth_hours':grow,'min_temp':mn,'max_temp':mx,'water_use':water,'yield_min':ymin,'yield_max':ymax,'seasons':seasons,'nitrogen':n,'phosphorus':p,'potassium':k,'disease_family':fam,'description':desc})
save('crops.json',crops)

# Natural resources
resources=load('resources.json')
# Replace authored layer with richer definitions while retaining old IDs.
def res(i,n,glyph,color,tags,yields,terrains,density,desc,flavor,tool=None,power=0,mins=10,regrow=30,moist=(0,65535),temp=(0,65535),seasons=(),patch=1,block=False,sight=False):
    return {'id':i,'name':n,'glyph':glyph,'ascii_glyph':glyph,'ansi_color':color,'tags':list(tags),'required_tool_tag':tool,'required_tool_power':power,'minutes':mins,'regrow_days':regrow,'yields':yields,'blocks_movement':block,'blocks_sight':sight,'description':desc,'flavor':flavor,'terrains':list(terrains),'min_temp':moist[0] if False else temp[0],'max_temp':temp[1],'min_moisture':moist[0],'max_moisture':moist[1],'seasons':list(seasons),'density':density,'patch_scale':patch}
rich=[
res('core:oak_tree','Mature Oak','T',92,['tree','wood','living'],{'core:wood':[4,7],'core:bark':[1,2]},['core:forest','core:grass'],420,'A mature broadleaf tree providing heavy timber and tannin-rich bark.','"Old wood keeps a long memory of weather."','axe',1,35,240,moist=(25000,65535),temp=(18000,56000),block=True,sight=True,patch=6),
res('core:pine_tree','Mature Pine','Y',32,['tree','wood','living','conifer'],{'core:wood':[3,6],'core:bark':[1,2]},['core:forest','core:tundra'],380,'A straight conifer yielding useful timber and fibrous bark.','"Needles whisper even when the forest is still."','axe',1,30,210,moist=(18000,60000),temp=(5000,36000),block=True,sight=True,patch=5),
res('core:birch_tree','Mature Birch','T',97,['tree','wood','living'],{'core:wood':[2,5],'core:bark':[2,3]},['core:forest','core:grass'],180,'A pale-barked tree whose wood is light and bark readily worked.','"White bark marks the edge of younger woods."','axe',1,28,180,moist=(25000,60000),temp=(14000,48000),block=True,sight=True,patch=4),
res('core:willow_tree','Mature Willow','T',92,['tree','wood','living','wetland'],{'core:wood':[2,4],'core:bark':[2,4],'core:stout_branch':[1,2]},['core:grass','core:forest'],120,'A water-loving tree with flexible branches and useful bark.','"Willow follows water where stone will not."','axe',1,26,170,moist=(43000,65535),temp=(18000,54000),block=True,sight=True,patch=4),
res('core:blueberry_bush','Blueberry Bush','%',35,['bush','food','fruit','living'],{'core:blueberries':[2,5]},['core:forest','core:grass'],120,'A low shrub bearing dark edible berries in warm seasons.','"Blue stains on the fingers are proof enough."',mins=8,regrow=18,moist=(30000,60000),temp=(16000,52000),seasons=['summer','autumn'],patch=4),
res('core:raspberry_cane','Raspberry Cane','%',31,['bush','food','fruit','living'],{'core:raspberries':[2,4]},['core:forest','core:grass'],90,'Thorny canes carrying soft red berries.','"The thorns collect their share before you do."',mins=8,regrow=16,moist=(28000,60000),temp=(18000,54000),seasons=['summer'],patch=4),
res('core:strawberry_patch','Wild Strawberry Patch','*',91,['food','fruit','living'],{'core:wild_strawberries':[1,4]},['core:grass','core:forest'],70,'Low plants bearing small fragrant berries near sunny clearings.','"Small enough to miss, sweet enough to remember."',mins=7,regrow=14,moist=(24000,52000),temp=(20000,56000),seasons=['spring','summer'],patch=3),
res('core:dandelion_patch','Dandelion Patch',';',93,['food','vegetable','herb','living'],{'core:dandelion_greens':[1,3]},['core:grass','core:scrub'],110,'Common hardy greens useful raw or cooked.','"The common plant survives because nobody can truly own the ground."',mins=6,regrow=20,temp=(16000,58000),seasons=['spring','summer','autumn'],patch=3),
res('core:nettle_patch','Nettle Patch','!',92,['food','vegetable','fiber','living'],{'core:nettles':[1,3],'core:brush':[1,2]},['core:grass','core:forest'],80,'Stinging plants offering food after cooking and coarse fiber after processing.','"It punishes bare hands but rewards preparation."',mins=8,regrow=24,moist=(30000,62000),temp=(16000,54000),seasons=['spring','summer'],patch=3),
res('core:wild_onion_patch','Wild Onion','i',97,['food','vegetable','root','living'],{'core:wild_onion':[1,3]},['core:grass','core:scrub'],65,'Sharp-smelling wild bulbs hidden among grasses.','"Smell finds it before sight does."',mins=8,regrow=45,temp=(18000,56000),seasons=['spring','summer','autumn'],patch=2),
res('core:wild_carrot_patch','Wild Carrot','i',37,['food','vegetable','root','living'],{'core:wild_carrot':[1,2]},['core:grass','core:scrub'],55,'A tough wild root that hints at the potential of cultivation.','"A pale root under ordinary leaves."',mins=9,regrow=50,temp=(16000,54000),seasons=['summer','autumn'],patch=2),
res('core:yarrow_patch','Yarrow','+',97,['herb','medical','living'],{'core:yarrow':[1,3]},['core:grass','core:scrub'],50,'A hardy flowering herb useful in simple medicine and bitter infusions.','"Fieldcraft remembers plants long before books do."',mins=7,regrow=35,temp=(12000,56000),seasons=['summer','autumn'],patch=2),
res('core:plantain_patch','Broadleaf Plantain','+',32,['herb','medical','living'],{'core:plantain_leaf':[1,3]},['core:grass'],55,'Low broad leaves common on disturbed ground.','"It grows where people walk, as if following them."',mins=6,regrow=28,moist=(18000,56000),temp=(16000,56000),seasons=['spring','summer','autumn'],patch=2),
res('core:morel_patch','Morel Cluster','m',33,['food','mushroom','vegetable','living'],{'core:morel':[1,3]},['core:forest'],35,'A seasonal cluster of edible woodland mushrooms.','"Honeycombed caps after wet weather."',mins=6,regrow=60,moist=(36000,65535),temp=(14000,42000),seasons=['spring'],patch=3),
res('core:bolete_patch','Bolete Cluster','m',33,['food','mushroom','vegetable','living'],{'core:bolete':[1,3]},['core:forest'],45,'Firm mushrooms appearing beneath mature forest cover.','"A stout cap pushing through old leaves."',mins=6,regrow=50,moist=(32000,62000),temp=(18000,50000),seasons=['summer','autumn'],patch=3),
res('core:reed_bed','Reed Bed','|',92,['fiber','wetland','living'],{'core:reed_bundle':[1,3]},['core:grass'],120,'Tall reeds rooted in saturated soil near water.','"Wet ground grows its own building material."',mins=10,regrow=30,moist=(50000,65535),temp=(16000,56000),patch=4),
res('core:wild_grain_patch','Wild Grain','"',93,['food','grain','living'],{'core:wild_grain':[1,3]},['core:grass','core:scrub'],80,'Sparse stands of wild cereal grass with collectable seed heads.','"The first field begins as something nobody planted."',mins=10,regrow=90,moist=(16000,48000),temp=(20000,58000),seasons=['summer','autumn'],patch=4),
res('core:cattail_bed','Cattails','|',32,['food','wetland','living'],{'core:cattail_root':[1,2],'core:reed_bundle':[1,2]},['core:grass'],70,'Wetland plants with edible roots and useful fibrous leaves.','"Food and fiber standing ankle-deep in water."',mins=12,regrow=50,moist=(54000,65535),temp=(18000,56000),patch=4),
res('core:clay_bank','Clay Bank','~',33,['clay','soil'],{'core:clay_lump':[1,3]},['core:grass','core:sand'],60,'Exposed sticky clay in damp low ground.','"Earth that keeps the shape of your hand."',mins=12,regrow=0,moist=(44000,65535),temp=(10000,60000),patch=3),
res('core:fallen_branches','Fallen Branches','/',33,['wood','branch','fuel'],{'core:stout_branch':[1,2],'core:brush':[1,2]},['core:forest','core:grass','core:scrub'],170,'Deadfall branches that can be gathered without an axe.','"Storms do some cutting for free."',mins=7,regrow=25,patch=3),
res('core:loose_stone','Loose Stone','#',37,['rock','stone'],{'core:stone':[1,2]},['core:grass','core:scrub','core:rock','core:tundra'],160,'Loose fist-sized stone available without mining tools.','"The first tool is often simply the right rock."',mins=5,regrow=0,patch=2),
res('core:surface_boulder','Surface Boulder','o',37,['rock','stone'],{'core:stone':[2,5]},['core:rock','core:grass'],140,'A large exposed boulder requiring a pick to break efficiently.','"Too large to carry, useful once broken."','pick',1,25,0,patch=3,block=True),
]
resources=[]
for r in rich: resources.append(r)
save('resources.json',resources)

# Species
species=[]
def sp(i,n,g,diet,mass,hp,dmg,agg,speed,repro,mort,k,hab,desc,flavor,attacks,carcass,temp=(0,65535),moist=(0,65535),group=(1,3)):
    return {'id':i,'name':n,'glyph':g,'diet':diet,'mass_kg':mass,'max_hp':hp,'damage':dmg,'aggression':agg,'speed':speed,'reproduction':repro,'mortality':mort,'carrying_capacity':k,'habitats':hab,'drops':{},'body':{'torso':58,'head':16,'legs':26},'description':desc,'flavor':flavor,'min_temp':temp[0],'max_temp':temp[1],'min_moisture':moist[0],'max_moisture':moist[1],'group_min':group[0],'group_max':group[1],'attacks':attacks,'carcass':carcass}
A=lambda name,damage,dtype='bite',bleed=1,fract=0:{'name':name,'damage':damage,'type':dtype,'bleeding':bleed,'fracture':fract}
species=[
sp('core:rabbit','Cottontail Rabbit','r','herbivore',2,10,1,0,3,48,13,380,['grass','forest','scrub'],'A small fast herbivore that relies on cover, speed, and prolific breeding.','"A flash of white tail, then grass moving where nothing seems to be."',[A('panicked kick',1,'blunt',0)],{'core:raw_small_game':1,'core:fresh_hide':1,'core:bone':1},temp=(12000,56000),group=(1,3)),
sp('core:snowshoe_hare','Snowshoe Hare','h','herbivore',3,12,2,0,3,40,12,220,['forest','tundra'],'A cold-country hare whose large feet carry it over soft ground.','"Long legs, pale fur, and a habit of vanishing uphill."',[A('desperate kick',2,'blunt',0)],{'core:raw_small_game':1,'core:fresh_hide':1,'core:bone':1},temp=(0,32000),group=(1,2)),
sp('core:deer','White-Tailed Deer','d','herbivore',85,38,4,3,3,18,8,100,['grass','forest'],'A wary browser moving between woodland cover and open feeding ground.','"It watches the wind before it watches you."',[A('defensive kick',5,'blunt',0,10),A('antler jab',4,'pierce',2)],{'core:raw_game_meat':6,'core:fresh_hide':2,'core:bone':3,'core:animal_fat':1,'core:sinew':2},temp=(8000,56000),group=(1,5)),
sp('core:elk','Elk','E','herbivore',280,70,8,8,3,12,7,65,['grass','forest'],'A massive grazing deer moving in loose herds near meadow and forest edge.','"A herd sounds like weather when it decides to run."',[A('goring rush',9,'pierce',3,8),A('heavy kick',8,'blunt',0,18)],{'core:raw_game_meat':14,'core:fresh_hide':4,'core:bone':6,'core:animal_fat':3,'core:sinew':4},temp=(5000,48000),group=(2,8)),
sp('core:moose','Moose','M','herbivore',430,90,11,15,2,8,6,35,['forest','grass'],'A huge solitary browser, usually calm until crowded or threatened.','"Too large to mistake for harmless once it turns toward you."',[A('antler sweep',12,'blunt',2,15),A('trampling charge',14,'blunt',1,25)],{'core:raw_game_meat':20,'core:fresh_hide':5,'core:bone':8,'core:animal_fat':4,'core:sinew':5},temp=(0,40000),moist=(25000,65535),group=(1,2)),
sp('core:boar','Wild Boar','b','omnivore',95,50,8,35,3,22,9,80,['forest','scrub','grass'],'A tough rooting omnivore with poor manners and dangerous tusks.','"Brush shakes first. Then the tusks arrive."',[A('tusk slash',9,'cut',4),A('body charge',7,'blunt',0,12)],{'core:raw_game_meat':7,'core:fresh_hide':2,'core:bone':3,'core:animal_fat':2,'core:sinew':1},temp=(12000,58000),group=(1,5)),
sp('core:turkey','Wild Turkey','t','omnivore',7,18,3,5,3,30,12,160,['forest','grass'],'A large ground bird that feeds in flocks and bursts noisily into flight.','"A sudden thunder of wings from brush that looked empty."',[A('spur rake',3,'cut',1)],{'core:raw_poultry':2,'core:feather':4,'core:bone':1},temp=(14000,58000),group=(2,8)),
sp('core:grouse','Grouse','g','omnivore',1,8,1,0,3,38,14,220,['forest','scrub'],'A compact ground bird relying on camouflage and explosive escape.','"You notice it exactly one heartbeat before it leaves."',[A('wing buffet',1,'blunt',0)],{'core:raw_poultry':1,'core:feather':2},temp=(5000,50000),group=(1,5)),
sp('core:mountain_goat','Mountain Goat','G','herbivore',75,42,6,12,3,16,8,50,['rock','tundra'],'A sure-footed grazer of rocky high country, defensive when cornered.','"Cliffs are roads to it."',[A('horn jab',7,'pierce',2),A('shove',5,'blunt',0,12)],{'core:raw_game_meat':5,'core:fresh_hide':2,'core:bone':2,'core:sinew':2},temp=(0,35000),group=(2,6)),
sp('core:red_fox','Red Fox','f','carnivore',7,16,4,12,3,28,12,55,['forest','grass','scrub'],'A small adaptable predator hunting rodents, birds, and carrion.','"A bright tail passing through dusk grass."',[A('snapping bite',4,'bite',2)],{'core:raw_small_game':1,'core:fresh_hide':1,'core:bone':1},temp=(8000,56000),group=(1,2)),
sp('core:wolf','Grey Wolf','w','carnivore',45,32,7,62,3,13,10,28,['forest','grass','tundra'],'A social endurance predator that becomes far more dangerous in a pack.','"One wolf watches. The others use the watching."',[A('raking bite',8,'bite',4),A('hamstring bite',6,'bite',5)],{'core:raw_game_meat':3,'core:fresh_hide':2,'core:bone':2,'core:sinew':1},temp=(0,52000),group=(2,7)),
sp('core:brown_bear','Brown Bear','B','omnivore',320,105,14,55,2,7,5,16,['forest','grass'],'A huge omnivore with enormous strength and little need to bluff.','"The forest becomes smaller when a bear stands up."',[A('clawing rush',15,'cut',6),A('crushing bite',14,'bite',5,18)],{'core:raw_game_meat':15,'core:fresh_hide':5,'core:bone':7,'core:animal_fat':5,'core:sinew':3},temp=(2000,46000),group=(1,1)),
sp('core:badger','Badger','q','omnivore',12,24,6,45,2,20,11,45,['grass','forest','scrub'],'A low powerful digger that reacts to close threats with disproportionate confidence.','"Small enough to underestimate exactly once."',[A('mauling bite',7,'bite',4),A('claw rake',5,'cut',3)],{'core:raw_small_game':2,'core:fresh_hide':1,'core:bone':1,'core:animal_fat':1},temp=(8000,54000),group=(1,2)),
sp('core:cave_crawler','Cave Crawler','c','omnivore',18,24,6,55,2,20,12,45,['underground'],'A pale many-limbed cave scavenger drawn to carrion and vibration.','"Its feet click before its body clears the dark."',[A('hooking bite',6,'bite',3),A('limb rake',5,'cut',2)],{'core:raw_small_game':2,'core:bone':1},group=(1,4)),
sp('core:cave_grazer','Cave Grazer','v','herbivore',55,34,4,2,2,18,9,70,['underground'],'A blind subterranean grazer feeding on cave growths and mineral films.','"It noses stone as if stone were grass."',[A('defensive shove',4,'blunt',0,8)],{'core:raw_game_meat':4,'core:fresh_hide':1,'core:bone':2},group=(2,5)),
sp('core:cave_stalker','Cave Stalker','s','carnivore',38,36,9,75,3,10,11,22,['underground'],'A vibration-hunting cave predator that waits near narrow passages.','"Silence in a cave can be something holding still."',[A('ambush bite',10,'bite',5),A('rending claw',8,'cut',4)],{'core:raw_game_meat':2,'core:fresh_hide':2,'core:bone':2,'core:sinew':1},group=(1,2)),
sp('core:marsh_boar','Marsh Boar','j','omnivore',110,55,9,42,2,18,9,45,['grass','scrub'],'A heavy wetland-adapted boar feeding among reeds and muddy banks.','"Mud hides the feet, not the tusks."',[A('tusk hook',10,'cut',4),A('muddy charge',8,'blunt',0,15)],{'core:raw_game_meat':8,'core:fresh_hide':2,'core:bone':3,'core:animal_fat':3},temp=(16000,58000),moist=(43000,65535),group=(1,4)),
]
save('species.json',species)

# Cooking methods
methods=[
{'id':'core:roast','name':'Roast','station':'core:campfire','cookware':None,'min_ingredients':1,'max_ingredients':2,'allowed_tags':['raw_meat','vegetable','mushroom','root'],'minutes':25,'satiety_percent':115,'hydration_bonus':0,'description':'Cook one or two solid ingredients directly over controlled heat.','effect':'warming'},
{'id':'core:stew','name':'Stew','station':'core:campfire','cookware':'core:clay_pot','min_ingredients':2,'max_ingredients':4,'allowed_tags':['raw_meat','vegetable','mushroom','root','grain','fat','herb'],'minutes':50,'satiety_percent':135,'hydration_bonus':12,'description':'Simmer mixed ingredients in water for a filling balanced meal.','effect':'recovery'},
{'id':'core:porridge','name':'Porridge','station':'core:campfire','cookware':'core:clay_pot','min_ingredients':2,'max_ingredients':4,'allowed_tags':['grain','fruit','fat'],'minutes':40,'satiety_percent':130,'hydration_bonus':8,'description':'Boil grain with water and optional fruit or fat into durable energy food.','effect':'stamina'},
{'id':'core:broth','name':'Broth','station':'core:campfire','cookware':'core:clay_pot','min_ingredients':1,'max_ingredients':4,'allowed_tags':['offal','bone','herb','vegetable','mushroom'],'minutes':60,'satiety_percent':105,'hydration_bonus':20,'description':'Slowly simmer bones, organs, herbs, or vegetables into a hydrating broth.','effect':'recovery'},
]
save('cooking_methods.json',methods)
print('items',len(items),'recipes',len(recipes),'structures',len(structures),'crops',len(crops),'resources',len(resources),'species',len(species),'cooking',len(methods))
