#!/usr/bin/env python3
"""Rebuild the authored recovery-and-crafting catalog (no random content).

Lists below describe individual physical objects and distinct craft processes;
helpers only apply consistent IDs, progression, discovery, nutrition and art
metadata. Existing core definitions remain intact on repeated runs.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'worldseed' / 'data'

def slug(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

def iid(name):
    return name if name.startswith('core:') else 'core:' + slug(name)

COMPONENTS = [
    ('Wood Pieces', 'wood', 120, 180, 1),
    ('Metal Scraps', 'iron', 80, 40, 2),
    ('Nuts and Bolts', 'iron', 30, 25, 4),
    ('Tool Handles', 'wood', 180, 250, 4),
    ('Plant Scraps', 'organic', 30, 75, 1),
    ('Cloth Scraps', 'fiber', 10, 35, 2),
    ('Leather Scraps', 'leather', 40, 65, 3),
    ('Bone Chips', 'bone', 5, 5, 2),
    ('Ceramic Shards', 'clay', 70, 35, 1),
    ('Glass Shards', 'stone', 35, 20, 2),
    ('Copper Wire', 'copper', 20, 15, 5),
    ('Resin Lumps', 'organic', 35, 30, 3),
    ('Mineral Grit', 'stone', 100, 45, 1),
]
RARE_COMPONENTS = [
    ('Tempered Spring', 'steel', 15, 15, 15),
    ('Fine Gear', 'iron', 20, 15, 18),
    ('Clear Crystal', 'stone', 30, 18, 18),
    ('Aromatic Oil', 'organic', 10, 12, 12),
    ('Tough Fiber', 'fiber', 10, 30, 12),
    ('Silver Filament', 'copper', 5, 8, 24),
]

# Each family contains eighteen different village props. These are recovery
# inputs, never inert collectible filler and never nutritious spoiled food.
VILLAGE_FAMILIES = [
    ('metal', ['workshop','workyard','armory','dungeon'], 'unfasten',
     {'Metal Scraps':[2,3], 'Nuts and Bolts':[1,2]}, 'Tempered Spring', [
      'Bent Door Hinge','Rusted Padlock','Broken Buckle','Cracked Sickle Head',
      'Worn Horseshoe','Discarded Spur','Bent Wagon Bracket','Split Iron Ring',
      'Dented Candle Snuffer','Seized Hand Drill','Snapped Shears','Broken Chain Link',
      'Rusted Stove Grate','Loose Gate Latch','Bent Fire Poker','Cracked Pan Handle',
      'Discarded Harness Bell','Jammed Clockwork Catch']),
    ('wood', ['household','workshop','workyard','inn'], 'carve',
     {'Wood Pieces':[2,4], 'Tool Handles':[1,1]}, 'Tough Fiber', [
      'Split Wagon Spoke','Broken Chair Rung','Cracked Barrel Stave','Worn Rolling Pin',
      'Splintered Rake','Broken Loom Shuttle','Discarded Paddle','Warped Cupboard Door',
      'Split Crate Lid','Cracked Spinning Distaff','Snapped Broom Shaft','Broken Ladder Step',
      'Worn Tent Peg','Chipped Wooden Ladle','Discarded Yoke','Broken Cart Axle',
      'Loose Window Shutter','Split Tool Rack']),
    ('cloth', ['household','wardrobe','inn','medicine'], 'strip',
     {'Cloth Scraps':[3,5], 'Plant Scraps':[1,2]}, 'Tough Fiber', [
      'Torn Apron','Threadbare Curtain','Frayed Bedroll','Split Grain Sack',
      'Worn Sail Patch','Tangled Embroidery','Discarded Cap Lining','Torn Banner',
      'Ragged Quilt','Unraveled Scarf','Stained Table Runner','Broken Felt Slipper',
      'Frayed Fishing Smock','Old Saddle Blanket','Split Pillowcase','Discarded Bandolier Lining',
      'Worn Laundry Strap','Torn Mosquito Veil']),
    ('leather', ['wardrobe','armory','workshop','workyard'], 'strip',
     {'Leather Scraps':[2,4], 'Nuts and Bolts':[1,1]}, 'Tough Fiber', [
      'Split Harness Strap','Worn Boot Sole','Broken Scabbard','Cracked Saddle Flap',
      'Torn Leather Pouch','Discarded Bridle','Old Bellows Skin','Broken Glove',
      'Split Quiver Seam','Cracked Belt','Worn Knee Guard','Loose Shield Grip',
      'Discarded Muzzle','Broken Satchel Flap','Torn Hunting Gaiter','Worn Drum Head',
      'Cracked Sling Strap','Split Water Bag']),
    ('ceramic', ['household','pantry','inn','medicine'], 'crush',
     {'Ceramic Shards':[2,4], 'Mineral Grit':[1,1]}, 'Clear Crystal', [
      'Chipped Crock','Broken Roof Tile','Cracked Jug','Split Butter Dish',
      'Shattered Inkpot','Broken Oil Lamp','Chipped Chamber Pot','Cracked Honey Jar',
      'Broken Kiln Spacer','Split Tea Bowl','Cracked Fermentation Weight','Broken Drain Pipe',
      'Chipped Mortar Bowl','Cracked Soap Dish','Broken Flower Pot','Split Baking Stone',
      'Chipped Salt Cellar','Discarded Crucible']),
    ('glass', ['archive','medicine','pantry','inn'], 'sort',
     {'Glass Shards':[2,4], 'Copper Wire':[1,1]}, 'Clear Crystal', [
      'Clouded Window Pane','Cracked Bottle Neck','Broken Spectacle Lens','Chipped Glass Bead',
      'Shattered Perfume Vial','Split Lamp Chimney','Broken Hourglass Bulb','Cracked Mirror Edge',
      'Chipped Glass Stopper','Broken Lantern Globe','Clouded Prism','Cracked Apothecary Jar',
      'Split Glass Funnel','Broken Seal Stamp','Chipped Drinking Glass','Cracked Fishing Float',
      'Broken Glass Pendant','Shattered Measuring Tube']),
    ('paper', ['archive','household','inn','dungeon'], 'strip',
     {'Plant Scraps':[2,4], 'Cloth Scraps':[1,2]}, 'Silver Filament', [
      'Waterlogged Ledger','Torn Map Case','Loose Book Binding','Discarded Letter Bundle',
      'Molded Scroll Tube','Broken Writing Board','Faded Market Notice','Split Wax Tablet',
      'Frayed Document Roll','Discarded Account Slip','Torn Song Folio','Broken Seal Envelope',
      'Ruined Recipe Leaf','Old Tax Register','Tattered Charter Copy','Discarded Shipping Label',
      'Split Notebook Cover','Waterstained Almanac']),
    ('stone', ['workshop','workyard','dungeon','household'], 'crush',
     {'Mineral Grit':[2,3], 'Ceramic Shards':[1,2]}, 'Clear Crystal', [
      'Worn Whetstone','Chipped Mill Fragment','Cracked Hearth Brick','Broken Grindstone Rim',
      'Split Stone Weight','Chipped Plumb Bob','Cracked Slate Shingle','Broken Mosaic Piece',
      'Chipped Stone Pestle','Fractured Mortar Block','Split Quarry Wedge','Worn Grinding Pebble',
      'Broken Soapstone Cup','Chipped Sandstone Disc','Cracked Door Sill','Loose Gravel Paver',
      'Broken Stone Spindle','Split Chalk Marker']),
    ('mixed', ['workshop','armory','archive','dungeon'], 'unfasten',
     {'Metal Scraps':[1,2], 'Wood Pieces':[1,2], 'Copper Wire':[1,1]}, 'Fine Gear', [
      'Broken Hand Lantern','Jammed Ratchet Wheel','Damaged Survey Compass','Broken Spinning Reel',
      'Cracked Balance Scale','Seized Music Box','Damaged Spring Trap','Broken Bellows Valve',
      'Jammed Door Closer','Bent Loom Ratchet','Broken Crossbow Trigger','Cracked Orrery Arm',
      'Split Pump Piston','Damaged Grinding Crank','Broken Wagon Brake','Seized Clock Pendulum',
      'Damaged Sighting Tube','Broken Winding Key']),
    ('provisions', ['pantry','grain','workyard','natural_stump'], 'sort',
     {'Plant Scraps':[3,5], 'Resin Lumps':[1,1]}, 'Aromatic Oil', [
      'Empty Seed Husk Bundle','Spoiled Herb Sachet','Dried Onion Skins','Mildewed Grain Chaff',
      'Cracked Nut Shells','Old Apple Pressings','Discarded Tea Stems','Molded Hop Sack',
      'Spent Malt Heap','Broken Beeswax Comb','Dried Gourd Rind','Old Spice Sweepings',
      'Split Pine Pitch Pot','Spoiled Flax Bundle','Crumbled Herb Wreath','Dried Citrus Peel',
      'Spent Dye Leaves','Discarded Reed Mat Offcuts']),
]

# Four habitats, twelve botanically different recoverable plants in each.
# Rare plants are still physical resources, not random generic ground rewards.
WILD_PLANTS = [
    (['forest','scrub'], [
      'Resinous Pine Cone','Birch Catkin Cluster','Oak Gall Cluster','Juniper Bough',
      'Hazel Catkin Spray','Spruce Pitch Knot','Willow Bark Curl','Beech Nut Cup',
      'Dogwood Stem Bundle','Silverleaf Sprig','Ghost Orchid Stem','Amberroot Crown']),
    (['grass','floodplain'], [
      'Dried Teasel Head','Burdock Burr Cluster','Milkweed Pod','Flax Seed Capsule',
      'Chicory Root Crown','Mullein Flower Spike','Goldenrod Spray','Sweet Clover Tops',
      'Rose Hip Branch','Moonmint Sprig','Saffron Crocus Tuft','Sunspice Rhizome']),
    (['wetland','riverbank','salt_marsh'], [
      'Cattail Seed Head','Alder Cone Cluster','Rush Pith Bundle','Bog Myrtle Branch',
      'Sedge Root Mat','Marsh Mallow Stems','Water Iris Rhizome','Sweet Flag Root',
      'Peat Moss Clump','Blue Lotus Stalk','Marsh Amber Bulb','Star Reed Tuft']),
    (['tundra','rock','coastal_cliff','rocky_shore'], [
      'Reindeer Lichen Mat','Rock Samphire Stems','Sea Lavender Spray','Dwarf Willow Twigs',
      'Mountain Avens Seedhead','Crowberry Stem Mat','Alpine Sorrel Root','Cotton Grass Tuft',
      'Bladderwrack Holdfast','Frost Sage Branch','Crimson Stonecrop Crown','Pearl Kelp Knot']),
]

ANIMAL_PARTS = [
    ('Rabbit Foot Tuft','cloth',['rabbit','snowshoe_hare'],'Cloth Scraps','Tough Fiber'),
    ('Deer Antler Tip','bone',['deer','elk'],'Bone Chips','Tough Fiber'),
    ('Elk Tooth Row','bone',['elk'],'Bone Chips','Tough Fiber'),
    ('Moose Hoof Plate','bone',['moose'],'Bone Chips','Tough Fiber'),
    ('Boar Bristle Patch','cloth',['boar','marsh_boar','pig'],'Cloth Scraps','Tough Fiber'),
    ('Turkey Quill Fan','cloth',['turkey'],'Cloth Scraps','Tough Fiber'),
    ('Grouse Down Tuft','cloth',['grouse'],'Cloth Scraps','Tough Fiber'),
    ('Goat Horn Sheath','bone',['mountain_goat'],'Bone Chips','Tough Fiber'),
    ('Fox Tail Tuft','cloth',['red_fox'],'Cloth Scraps','Tough Fiber'),
    ('Wolf Fang Pair','bone',['wolf'],'Bone Chips','Tough Fiber'),
    ('Bear Claw Sheath','bone',['brown_bear'],'Bone Chips','Tough Fiber'),
    ('Badger Guard Hairs','cloth',['badger'],'Cloth Scraps','Tough Fiber'),
    ('Crawler Carapace Plate','bone',['cave_crawler'],'Bone Chips','Tough Fiber'),
    ('Grazer Horn Chip','bone',['cave_grazer'],'Bone Chips','Tough Fiber'),
    ('Stalker Tendon Knot','leather',['cave_stalker'],'Leather Scraps','Tough Fiber'),
    ('Muskrat Fur Clump','cloth',['muskrat'],'Cloth Scraps','Tough Fiber'),
    ('Beaver Incisor Pair','bone',['beaver'],'Bone Chips','Tough Fiber'),
    ('Otter Whisker Bundle','cloth',['river_otter'],'Cloth Scraps','Tough Fiber'),
    ('Heron Pinion Quills','cloth',['great_blue_heron'],'Cloth Scraps','Tough Fiber'),
    ('Gull Wing Down','cloth',['herring_gull'],'Cloth Scraps','Tough Fiber'),
    ('Seal Whisker Pad','leather',['harbor_seal'],'Leather Scraps','Tough Fiber'),
    ('Cow Horn Ring','bone',['cow'],'Bone Chips','Tough Fiber'),
    ('Chicken Quill Bundle','cloth',['chicken'],'Cloth Scraps','Tough Fiber'),
    ('Sheep Wool Locks','cloth',['sheep'],'Cloth Scraps','Tough Fiber'),
]

new_items = []
new_recipes = []
salvage = []
manifest = {'version':1, 'components':[iid(x[0]) for x in COMPONENTS],
            'rare_components':[iid(x[0]) for x in RARE_COMPONENTS],
            'misc':[], 'recipes':[]}

for name,mat,mass,volume,value in COMPONENTS + RARE_COMPONENTS:
    asset='component_'+slug(name)
    new_items.append(dict(id=iid(name),name=name,asset=asset,sprite_tag=asset,
         category='material',material=iid(mat),mass_g=mass,volume_ml=volume,base_value=value,
         tags=['craft_component','recovered']+(['rare_component'] if (name,mat,mass,volume,value) in RARE_COMPONENTS else []),
         description=f'{name} sorted and cleaned for reuse in specialist crafting. Recovery avoids wasting sound material.',
         flavor=f'"A patient craftsperson saves the useful {name.lower()}."'))
component_masses={x['id']:x['mass_g'] for x in new_items}


def misc(name,family,contexts,yields,rare,method,source='village',habitats=(),species=(),rarity='common',index=0):
    item_id=iid(name)
    y={iid(k):list(v) for k,v in yields.items()}
    rare_id=iid(rare)
    # Maximum recoverable mass, including the bonus, is below source mass.
    mass=sum(component_masses[k]*v[1] for k,v in y.items())+component_masses[rare_id]+40
    asset='salvage_'+slug(name)
    mat={'metal':'iron','wood':'wood','cloth':'fiber','leather':'leather','ceramic':'clay',
         'glass':'stone','paper':'fiber','stone':'stone','mixed':'iron','provisions':'organic',
         'plant':'organic','bone':'bone'}[family]
    parts=', '.join(k.split(':')[1].replace('_',' ') for k in y)
    new_items.append(dict(id=item_id,name=name,asset=asset,sprite_tag=asset,
      category='plant' if source=='wild' else 'material',
      **({'subcategory':'wild'} if source=='wild' else {}),
      material=iid(mat),mass_g=mass,volume_ml=max(35,mass*2),base_value=max(1,mass//180),
      tags=['misc','salvageable',family]+(['forage'] if source=='wild' else ['animal_part'] if source=='animal' else ['village_salvage']),
      description=f'{name}. Careful '+{'unfasten':'unfastening','carve':'carving','strip':'stripping',
          'crush':'crushing','sort':'sorting','clean':'cleaning'}[method]+f' recovers {parts}; an intact {rare.lower()} may survive inside.',
      flavor=f'"Look at the material before deciding that {name.lower()} is worthless."'))
    salvage.append(dict(id='core:salvage_'+slug(name),item_id=item_id,
       minutes=6+(index%4)*2+(4 if family in {'metal','mixed'} else 0),
       difficulty=3 if rarity=='rare' else 2 if family in {'metal','mixed','glass'} else 1,
       method=method,tool_qualities={},yields=y,
       rare_yields=[dict(item_id=rare_id,min=1,max=1,chance_percent=12 if rarity=='rare' else 4 if rarity=='uncommon' else 2)],
       description=f'Recover reusable {parts} from the {name.lower()} while protecting its delicate parts.'))
    row=dict(item_id=item_id,art_family=family,loot_contexts=list(contexts),
             habitats=[iid(h) for h in habitats],rarity=rarity,source=source)
    if species:row['species']=[iid(s) for s in species]
    manifest['misc'].append(row)

for family,contexts,method,y,rare,names in VILLAGE_FAMILIES:
    for index,name in enumerate(names):
        misc(name,family,contexts,y,rare,method,index=index,rarity='uncommon' if index>=14 else 'common')
for habitats,names in WILD_PLANTS:
    for index,name in enumerate(names):
        rare=index>=9
        misc(name,'plant',['wild_ground','natural_log','natural_stump'],
             {'Plant Scraps':[2,4], 'Resin Lumps':[1,1]},
             'Aromatic Oil' if index%2 else 'Tough Fiber','strip',source='wild',habitats=habitats,
             rarity='rare' if rare else 'uncommon' if index>=6 else 'common',index=index)
for index,(name,family,species,part,rare) in enumerate(ANIMAL_PARTS):
    misc(name,family,[],{part:[2,4]},rare,'clean',source='animal',species=species,index=index)

# Exact habitat legality is shared with the authored ecological features.
HABITAT_OVERRIDES = {
    **{slug(n):['wetland','riverbank'] for n in ['Water Iris Rhizome','Blue Lotus Stalk','Star Reed Tuft']},
    **{slug(n):['tundra','rock','coastal_cliff'] for n in ['Reindeer Lichen Mat','Dwarf Willow Twigs','Mountain Avens Seedhead','Crowberry Stem Mat','Alpine Sorrel Root','Cotton Grass Tuft','Frost Sage Branch','Crimson Stonecrop Crown']},
    **{slug(n):['rocky_shore','coastal_cliff'] for n in ['Rock Samphire Stems','Bladderwrack Holdfast','Pearl Kelp Knot']},
    'sea_lavender_spray':['rocky_shore','salt_marsh'],
}
for row in manifest['misc']:
    if row['item_id'].split(':')[1] in HABITAT_OVERRIDES:
        row['habitats']=[iid(t) for t in HABITAT_OVERRIDES[row['item_id'].split(':')[1]]]

# Rare returns represent retained physical parts. Ordinary pottery and simple
# metal offcuts do not contain springs, jewels or clockwork just by being junk.
for row in salvage:
    item=next(x for x in new_items if x['id']==row['item_id'])
    if 'ceramic' in item['tags'] or ('animal_part' in item['tags'] and 'bone' in item['tags']) or ('metal' in item['tags'] and not any(
            word in item['name'] for word in ('Padlock','Latch','Drill','Shears','Catch'))):
        row['rare_yields']=[]
        item['description']=item['description'].split(';')[0]+'.'
    elif item['id']=='core:tangled_embroidery':
        row['rare_yields'][0]['item_id']=iid('Silver Filament')
        item['description']=item['description'].replace('tough fiber','silver filament')
        item['description']+=' The decorative metallic thread is silver-plated copper.'
    elif 'paper' in item['tags']:
        row['rare_yields'][0]['item_id']=iid('Tough Fiber')
        item['description']=item['description'].replace('silver filament','tough fiber')
for item in new_items:
    if item['id']=='core:bone_chips':
        item['description']='Clean bone and workable horn or keratin fragments, sorted for carving, animal glue and mineral fertilizer.'
    elif item['id']=='core:cloth_scraps':
        item['description']='Cleaned textile scraps and soft recovered animal fibers for felt, yarn and dressing cloth.'
    elif item['id']=='core:clear_crystal':
        item['description']='An intact transparent crystalline or optical-glass fragment, suitable for precision lenses and fine cutting edges.'
    elif item['id']=='core:silver_filament':
        item['description']='A fine strand of silver-plated copper decorative thread, recovered intact from old embroidery for reinforced cords and precision instruments.'

# Recovery follows the actual donor material. Plant residue does not contain
# pitch, ordinary stone props do not hide jewels, and bare glass has no wire.
RESIN_DONORS={iid(n) for n in ('Resinous Pine Cone','Spruce Pitch Knot','Amberroot Crown',
                              'Split Pine Pitch Pot')}
WIRE_DONORS={iid(n) for n in ('Broken Spectacle Lens','Split Lamp Chimney',
                             'Broken Lantern Globe','Cracked Mirror Edge','Broken Glass Pendant')}
AROMATIC_DONORS={iid(n) for n in ('Juniper Bough','Spruce Pitch Knot','Moonmint Sprig',
    'Saffron Crocus Tuft','Sunspice Rhizome','Bog Myrtle Branch','Sweet Flag Root',
    'Frost Sage Branch','Amberroot Crown','Marsh Amber Bulb','Spoiled Herb Sachet',
    'Discarded Tea Stems','Old Spice Sweepings','Crumbled Herb Wreath','Dried Citrus Peel')}
GEAR_DONORS={iid(n) for n in ('Jammed Ratchet Wheel','Broken Spinning Reel','Seized Music Box',
                             'Bent Loom Ratchet','Cracked Orrery Arm','Seized Clock Pendulum')}
items_by_id={item['id']:item for item in new_items}
source_by_id={row['item_id']:row for row in manifest['misc']}
for row in salvage:
    item=items_by_id[row['item_id']]
    if ('plant' in item['tags'] or 'provisions' in item['tags']) and row['item_id'] not in RESIN_DONORS:
        row['yields'].pop(iid('Resin Lumps'),None)
    if 'glass' in item['tags'] and row['item_id'] not in WIRE_DONORS:
        row['yields'].pop(iid('Copper Wire'),None)
    if 'stone' in item['tags']:
        row['rare_yields']=[]
    if 'mixed' in item['tags'] and row['item_id'] not in GEAR_DONORS:
        if item['name'] in ('Damaged Spring Trap','Jammed Door Closer','Broken Crossbow Trigger'):
            row['rare_yields'][0]['item_id']=iid('Tempered Spring')
        elif item['name'] in ('Damaged Sighting Tube','Damaged Survey Compass'):
            row['rare_yields'][0]['item_id']=iid('Clear Crystal')
        else:
            row['rare_yields']=[]
    row['rare_yields']=[drop for drop in row['rare_yields'] if
                       drop['item_id']!=iid('Aromatic Oil') or row['item_id'] in AROMATIC_DONORS]
    if 'animal_part' in item['tags'] and 'cloth' in item['tags']:
        row['yields'][iid('Cloth Scraps')]=[1,2]
    parts=', '.join(k.split(':')[1].replace('_',' ') for k in row['yields'])
    action={'unfasten':'unfastening','carve':'carving','strip':'stripping',
            'crush':'crushing','sort':'sorting','clean':'cleaning'}[row['method']]
    item['description']=f'{item["name"]}. Careful {action} recovers {parts}.'
    if row['rare_yields']:
        rare_names=', '.join(items_by_id[drop['item_id']]['name'].lower() for drop in row['rare_yields'])
        item['description']+=f' An intact {rare_names} may survive careful recovery.'
    if item['id']=='core:tangled_embroidery':
        item['description']+=' Its decorative metallic thread is silver-plated copper.'
    row['description']=f'Recover reusable {parts} from the {item["name"].lower()} while protecting sound material.'
    waste=5 if source_by_id[row['item_id']]['source']=='animal' else 40
    item['mass_g']=sum(component_masses[k]*v[1] for k,v in row['yields'].items())+sum(
        component_masses[drop['item_id']]*drop['max'] for drop in row['rare_yields'])+waste
    item['volume_ml']=max(35,item['mass_g']*2)

# Recipe authoring follows below; save() is called once at the bottom.

def save():
    for filename, additions in [('items.json',new_items),('recipes.json',new_recipes)]:
        original=json.loads((DATA/filename).read_text())
        if filename=='items.json':
            original=[x for x in original if not str(x.get('sprite_tag','')).startswith(('salvage_','craft_','component_'))]
        else:
            original=[x for x in original if not x['id'].startswith('core:craft_')]
        original.extend(additions)
        (DATA/filename).write_text(json.dumps(original,indent=2)+'\n')
    (DATA/'salvage.json').write_text(json.dumps(salvage,indent=2)+'\n')
    (DATA/'crafting_expansion.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Added {len(new_items)} items, {len(salvage)} recovery inputs, {len(new_recipes)} recipes.')

PROFESSION = {
 'smith':('smithing','forge','metalworking'),
 'carpenter':('crafting','workbench','woodcraft'),
 'weaver':('crafting','loom','textiles'),
 'tanner':('crafting','tanning_frame','leatherwork'),
 'mason':('crafting','masonry_bench','masonry'),
 'potter':('crafting','pottery_wheel','pottery'),
 'miller':('crafting','millstone','milling'),
 'baker':('cooking','bakery_oven','baking'),
 'cook':('cooking','campfire','cooking'),
 'brewer':('cooking','brewery_vat','brewing'),
 'butcher':('hunting','butcher_table','butchery'),
 'fisher':('fishing','smoke_rack','fishery'),
 'farmer':('farming',None,'farming'),
 'herder':('survival',None,'husbandry'),
 'hunter':('hunting',None,'hunting'),
 'lumberjack':('woodcutting',None,'forestry'),
 'miner':('mining',None,'mining'),
 'healer':('medicine','herbalist_table','medicine'),
 'scholar':('scholarship','workbench','scholarship'),
}


def tool(**qualities):
    return dict(category='tool',tags=['tool'],tool_qualities=qualities)


def weapon(damage,kind='cut',cls='knife',reach=1,**opts):
    return dict(category='weapon',tags=['weapon'],weapon_damage=damage,damage_type=kind,
                weapon_class=cls,reach=reach,accuracy=2,stamina_cost=5+damage//3,**opts)


def armor(slot,protection,warmth=1):
    body={'head':'head','body':'torso','hands':'arms','legs':'legs'}[slot]
    return dict(category='armor',tags=['armor','clothing'],equip_slot=slot,
                armor=protection,coverage=[body],insulation=warmth)


def food(shelf=72,groups=()):
    return dict(category='food',tags=['food','cooked'],spoilage_hours=shelf,food_groups=list(groups))


def craft(profession,name,inputs,kind=None,tier=1,qty=1,minutes=None,qualities=None,station='default',
          use='',mat=None,catalysts=None,output=None,description=None,process=None,knowledge=None):
    skill,default_station,category=PROFESSION[profession]
    out=iid(output or name)
    recipe_id='core:craft_'+slug(name)
    costs={iid(k):v for k,v in inputs.items()}
    skill_station=default_station if station=='default' else station
    row=dict(id=recipe_id,name=name,inputs=costs,outputs={out:qty},
        minutes=minutes or (12,30,65)[tier-1],category=category,skill=skill,
        difficulty=(1,3,6)[tier-1],tool_qualities=qualities or {},
        discovery_items=list(costs)[:5],discovery_mode='experiment',
        description=description or f'{name}: {use or "shape and prepare the materials for the next stage of the craft"}.')
    if skill_station:row['station']=iid(skill_station)
    if catalysts:row['catalysts']={iid(k):v for k,v in catalysts.items()}
    if process:row['process']=process
    if knowledge:row['knowledge']=knowledge
    new_recipes.append(row)
    if output is None:
        opts=dict(kind or {})
        category_item=opts.pop('category','material')
        tags=opts.pop('tags',['craft_intermediate'])
        if category_item=='material':tags.append('craft_intermediate') if 'craft_intermediate' not in tags else None
        art_family={'smith':'metal','carpenter':'wood','weaver':'cloth','tanner':'leather','mason':'stone',
             'potter':'ceramic','miller':'food','baker':'food','cook':'food','brewer':'glass',
             'butcher':'bone','fisher':'fish','farmer':'plant','herder':'cloth','hunter':'bone',
             'lumberjack':'wood','miner':'stone','healer':'plant','scholar':'paper'}[profession]
        material=mat or {'metal':'iron','wood':'wood','cloth':'fiber','leather':'leather','stone':'stone',
                  'ceramic':'clay','food':'organic','glass':'organic','bone':'bone','fish':'organic','plant':'organic','paper':'fiber'}[art_family]
        asset='craft_'+slug(name)
        new_items.append(dict(id=out,name=name,asset=asset,sprite_tag=asset,category=category_item,
             material=iid(material),mass_g=1,volume_ml=1,base_value=(5,14,32)[tier-1],tags=tags,
             description=use or f'A carefully prepared {name.lower()} used in the next stage of {category}.',
             flavor=f'"Good {category} gives {name.lower()} a job to do."',**opts))
    else:
        art_family='existing'
    manifest['recipes'].append(dict(recipe_id=recipe_id,output_item=out,profession=profession,tier=tier,art_family=art_family))
    return out

# Recovery components also have conventional sources. The same downstream
# trees work for a smith with smelted metal and for a scavenger with old hinges.
craft('lumberjack','Split Sound Wood',{'wood':1},output='wood_pieces',qty=20,station=None,use='split stock into measured wood pieces')
craft('smith','Shear Iron Offcuts',{'iron_bloom':1},output='metal_scraps',qty=20,use='cut reusable metal scraps from a sound bloom')
craft('smith','Forge Fasteners',{'metal_scraps':2},output='nuts_and_bolts',qty=4,use='forge matching nuts and bolts',qualities={'hammer':1})
craft('carpenter','Carve Replacement Handles',{'wood_pieces':2},output='tool_handles',qty=1,use='fit a replacement tool handle',qualities={'cut':1})
craft('farmer','Sort Brush Offcuts',{'brush':1},output='plant_scraps',qty=8,station=None,use='sort plant offcuts for paper and compost')
craft('weaver','Cut Cloth Offcuts',{'woven_cloth':1},output='cloth_scraps',qty=10,use='cut damaged cloth into usable scraps')
craft('tanner','Trim Leather Offcuts',{'leather':1},output='leather_scraps',qty=10,use='trim leather scraps for laces and grips',qualities={'cut':1})
craft('butcher','Crush Clean Bone',{'bone':1},output='bone_chips',qty=12,use='crush clean bones for glue and carving',qualities={'crush':1})
craft('potter','Break Defective Pottery',{'clay_pot':1},output='ceramic_shards',qty=8,use='recover fired ceramic for grog and masonry')
craft('miner','Sift Crushed Stone',{'stone':1},output='mineral_grit',qty=20,station=None,use='sift mineral grit for mortar and polishing',qualities={'crush':1})
craft('smith','Draw Copper Wire',{'copper_ingot':1},output='copper_wire',qty=30,use='draw fine copper wire for mechanisms',qualities={'hammer':1})
craft('lumberjack','Collect Bark Pitch',{'bark':3},output='resin_lumps',qty=2,station=None,use='collect resin for adhesives and weatherproofing')
craft('smith','Smelt Sorted Iron Fragments',{'washed_ore_fragments':1,'coal':2},output='iron_bloom',tier=2,minutes=180,process='smelt_iron',use='smelt iron-bearing sorted fragments with controlled furnace fuel')
craft('smith','Smelt Selected Copper Granules',{'copper_granules':2,'coal':1},output='copper_ingot',tier=2,minutes=80,process='smelt_copper',use='smelt selected copper-bearing granules into conventional copper stock')

# Smithing: fastening -> blanks -> specialized work tools and real armor.
craft('smith','Rivet Set',{'metal_scraps':2},qty=3,use='small rivets for lamellar armor and saw frames')
craft('smith','Hinge Pair',{'metal_scraps':3,'nuts_and_bolts':1},use='matched hinges for folding tools and shields',qualities={'hammer':1})
craft('smith','Iron Tool Blank',{'metal_scraps':6,'coal':1},use='a consolidated blank for edged iron tools',qualities={'hammer':1},catalysts={'ceramic_mould':1})
craft('smith','Copper Sheet',{'copper_ingot':1},qty=3,use='thin copper sheet for kettles and lure blades',qualities={'hammer':1},mat='copper')
craft('smith','Claw Hammer',{'iron_tool_blank':1,'tool_handles':1},tool(hammer=4,crush=2),tier=2,use='drive fasteners and crush rock with a balanced claw hammer')
craft('smith','Iron Chisel',{'iron_tool_blank':1,'leather_scraps':1},tool(cut=3,scrape=3),tier=2,use='cut joints, dress stone and scrape hides',qualities={'hammer':2})
craft('smith','Iron Adze',{'iron_tool_blank':1,'tool_handles':1,'rivet_set':1},tool(chop=4,cut=2),tier=2,use='hew timber and carve plank stock',qualities={'hammer':2})
craft('smith','Salvage Driver',{'iron_tool_blank':1,'tool_handles':1,'nuts_and_bolts':2},tool(pierce=3,hammer=2),tier=2,use='release seized fastenings and work precise riveted joints',qualities={'hammer':2})
craft('smith','Segmented Armor Plates',{'metal_scraps':12,'rivet_set':2},tier=3,qty=2,use='overlapping plates for an iron lamellar vest',qualities={'hammer':3},catalysts={'stoneware_crucible':1})
craft('smith','Iron Lamellar Vest',{'segmented_armor_plates':2,'leather_lace':2,'felt_padding':1},armor('body',9,2),tier=3,use='protect the torso while a padded backing reduces cold metal contact')
craft('smith','Metal Frame Saw',{'iron_tool_blank':2,'hinge_pair':1,'tempered_spring':1,'tool_handles':1},tool(cut=5),tier=3,use='saw dense stock for advanced joinery and mechanism frames',qualities={'hammer':3})
craft('smith','Socketed Iron Hoe',{'iron_tool_blank':2,'tool_handles':2,'rivet_set':1},tool(till=5,dig=3),tier=3,use='till farm plots and dig tough soil',qualities={'hammer':3})

# Carpentry: cut joints and flexible frames lead to ranged weapons and shields.
craft('carpenter','Wooden Dowels',{'wood_pieces':2},qty=4,use='wooden pins joining dry-fit assemblies',qualities={'cut':1})
craft('carpenter','Planed Board',{'wood_pieces':4},use='straight timber for presses and instrument frames',qualities={'cut':1})
craft('carpenter','Bentwood Frame',{'wood_pieces':4,'resin_lumps':1},use='a curved frame for shield and fishing gear',qualities={'cut':1})
craft('carpenter','Fitted Grip',{'tool_handles':1,'leather_scraps':1},use='a wrapped grip for high-force bows and precision tools',qualities={'cut':1})
craft('carpenter','Woodworking Mallet',{'wood_pieces':5,'tool_handles':1},tool(hammer=3,crush=1),tier=2,use='seat joints without shattering wooden pegs')
craft('carpenter','Carpenter Brace',{'planed_board':1,'iron_tool_blank':1,'fitted_grip':1},tool(pierce=4),tier=2,use='bore accurately aligned holes for shield grips and pumps')
craft('carpenter','Wood Plane',{'planed_board':1,'iron_chisel':1,'nuts_and_bolts':2},tool(cut=4,scrape=2),tier=2,use='smooth stock for laminated bow limbs and fitted handles')
craft('carpenter','Laminated Bow Limbs',{'planed_board':3,'hide_glue':1,'wooden_dowels':2},tier=2,use='glued wooden laminations for a durable hunting bow',qualities={'cut':2})
craft('carpenter','Recurve Hunting Bow',{'laminated_bow_limbs':2,'fitted_grip':1,'waxed_thread':2},weapon(15,'pierce','bow',ammo_item='core:wood_arrow',range=7,two_handed=True),tier=3,use='shoot standard wood arrows with greater reach',qualities={'cut':3})
craft('carpenter','Folding Pole Spear',{'planed_board':2,'hinge_pair':1,'iron_tool_blank':1,'fitted_grip':1},weapon(14,'pierce','spear',reach=2),tier=3,use='keep large animals at reach while remaining portable',qualities={'pierce':2,'cut':3})
craft('carpenter','Ribbed Wood Shield',{'bentwood_frame':2,'planed_board':3,'wooden_dowels':3,'leather_lace':2},
      dict(category='armor',tags=['armor','shield'],equip_slot='offhand',shield_type='round',shield_melee_coverage=65,shield_ranged_coverage=65,shield_block=7,shield_stability=53,shield_stamina_cost=3,shield_body_coverage={'head':42,'torso':77,'arms':85,'legs':34}),tier=3,use='block melee blows and incoming missiles with a ribbed wooden shield',qualities={'cut':3,'pierce':2})
craft('carpenter','Levered Nutcracker',{'planed_board':1,'hinge_pair':1,'nuts_and_bolts':2},tool(crush=4),tier=3,use='crush seeds, grain, shells and mineral samples without a forge',qualities={'cut':3})

# Weaving: cloth processes produce climate protection, fishing equipment and
# medical ingredients. Every intermediate is consumed by another real process.
craft('weaver','Spun Yarn',{'fiber':2},qty=2,use='twisted yarn for felt, cloth and fine thread')
craft('weaver','Felt Padding',{'cloth_scraps':6,'spun_yarn':1},use='dense padding beneath armor and quilted coats')
craft('weaver','Linen Panel',{'flax':3,'spun_yarn':1},use='a strong linen panel for dressings and summer clothes')
craft('weaver','Canvas Panel',{'plant_cordage':2,'cloth_scraps':8},use='heavy canvas for protective clothing and nets')
craft('weaver','Waxed Thread',{'spun_yarn':2,'resin_lumps':1},tier=2,qty=2,use='sealed thread for bowstrings, line and leather seams')
craft('weaver','Reinforced Cloth',{'canvas_panel':1,'tough_fiber':1,'waxed_thread':1},tier=2,use='cloth reinforced with recovered tough fiber for travel coats',qualities={'sew':1})
craft('weaver','Padded Coif',{'felt_padding':1,'linen_panel':1,'spun_yarn':1},armor('head',2,6),tier=2,use='insulate the head and soften minor blows',qualities={'sew':1})
craft('weaver','Quilted Jerkin',{'felt_padding':2,'canvas_panel':1,'waxed_thread':1},armor('body',3,8),tier=2,use='protect and warm the torso while traveling',qualities={'sew':2})
craft('weaver','Layered Winter Trousers',{'felt_padding':2,'reinforced_cloth':1,'waxed_thread':1},armor('legs',3,10),tier=3,use='retain warmth in the legs during cold travel',qualities={'sew':2})
craft('weaver','Sailcloth Travel Coat',{'reinforced_cloth':2,'oiled_leather':1,'waxed_thread':2},armor('body',4,6),tier=3,use='provide modest armor and insulation in a durable coat',qualities={'sew':2})
craft('weaver','Waxed Casting Line',{'waxed_thread':3,'tough_fiber':1},dict(category='material',tags=['fishing_line'],tool_qualities={'line_quality':5}),tier=3,use='resist larger fish during line fishing')
craft('weaver','Knotted Cast Net',{'reinforced_cloth':1,'plant_cordage':8,'waxed_thread':2},dict(category='tool',tags=['tool','fishing_net'],tool_qualities={'net_quality':4}),tier=3,use='fish open shallow water with a sturdy cast net')

# Tanning: offcuts become grips, horn-working tools and fitted body protection.
craft('tanner','Leather Lace',{'leather_scraps':3},qty=2,use='tough lacing for armor, shields and leather seams',qualities={'cut':1})
craft('tanner','Cured Leather Panel',{'leather_scraps':8,'bark':1},use='a stitched panel for new leather garments',qualities={'scrape':1})
craft('tanner','Hide Glue',{'fresh_hide':1,'bone_chips':3},use='animal glue binding timber laminations and paper boards',station='campfire')
craft('tanner','Leather Grip Wrap',{'leather_lace':1,'resin_lumps':1},qty=2,use='grip wrapping for axes, cutting tools and pole weapons')
craft('tanner','Hardened Leather',{'cured_leather_panel':1,'resin_lumps':2},tier=2,use='stiffened leather for breastpieces and reinforced gloves')
craft('tanner','Oiled Leather',{'cured_leather_panel':1,'animal_fat':1},tier=2,use='flexible conditioned leather for coats and fitted boots')
craft('tanner','Leatherworker Awl',{'bone_chips':5,'leather_grip_wrap':1,'tool_handles':1},tool(sew=3,pierce=3),tier=2,use='pierce tough seams and stitch reinforced clothing',qualities={'cut':2})
craft('tanner','Riveted Work Gloves',{'hardened_leather':1,'rivet_set':1,'leather_lace':1},armor('hands',4,2),tier=2,use='protect the forearms and hands when working or fighting',qualities={'sew':2})
craft('tanner','Hardened Leather Cuirass',{'hardened_leather':3,'leather_lace':2,'felt_padding':1},armor('body',7,3),tier=3,use='cover the torso with stiff leather backed by felt',qualities={'sew':2})
craft('tanner','Fur Lined Hood',{'oiled_leather':1,'fur_felt':1,'waxed_thread':1},armor('head',4,10),tier=3,use='keep the head warm without heavy iron headgear',qualities={'sew':2})
craft('tanner','Reinforced Gaiters',{'hardened_leather':1,'oiled_leather':1,'leather_lace':2},armor('legs',5,4),tier=3,use='protect the lower body during rough travel',qualities={'sew':2})
craft('tanner','Horn Faced Buckler',{'hardened_leather':1,'horn_laminate':2,'bentwood_frame':1,'leather_lace':2},
      dict(category='armor',tags=['armor','shield'],equip_slot='offhand',shield_type='buckler',shield_melee_coverage=67,shield_ranged_coverage=27,shield_block=6,shield_stability=42,shield_stamina_cost=2,shield_body_coverage={'head':20,'torso':50,'arms':88,'legs':12}),tier=3,use='turn close blows with a light horn-faced hand shield',qualities={'sew':2})

# Masonry: recovered stone enters abrasives, edged tools and construction stock.
craft('mason','Mortar Mix',{'mineral_grit':4,'clay_lump':1},use='a mineral binder for dressed construction blocks')
craft('mason','Abrasive Powder',{'mineral_grit':3,'glass_shards':2},qty=2,use='hard grinding grains for polished optics and fine steel',qualities={'crush':1})
craft('mason','Stone Blade Blank',{'stone':1,'ceramic_shards':1},qty=2,use='selected hard flakes for cutting and scraping implements',qualities={'hammer':1})
craft('mason','Grinding Slab',{'stone':1,'mineral_grit':2},tool(crush=2),use='grind seeds and medicines into finer powders',qualities={'hammer':1})
craft('mason','Granite Pestle',{'stone':1,'tool_handles':1},tool(crush=3),tier=2,use='crush tough seeds, bone and dried herbs',qualities={'hammer':1})
craft('mason','Flint Hide Scraper',{'stone_blade_blank':1,'leather_grip_wrap':1},tool(scrape=3,skin=2),tier=2,use='dress fresh hides and strip bark without iron',qualities={'cut':1})
craft('mason','Mason Hand Hammer',{'stone':1,'tool_handles':1,'leather_lace':1},tool(hammer=3,crush=3),tier=2,use='dress blocks and crack mineral specimens')
craft('mason','Notched Stone Knife',{'stone_blade_blank':1,'tool_handles':1,'resin_lumps':1},tool(cut=3,butcher=2),tier=2,use='cut plant stock and butcher small carcasses',qualities={'cut':1})
craft('mason','Quarry Sledge',{'stone':3,'fitted_grip':1,'wooden_dowels':2},tool(hammer=5,crush=5,mine=2),tier=3,use='break rock, crush ore and perform heavy masonry',qualities={'hammer':2})
craft('mason','Basalt Head Mace',{'stone':2,'tool_handles':2,'leather_lace':2},weapon(13,'blunt','club'),tier=3,use='deliver heavy blunt attacks with a securely hafted stone head',qualities={'hammer':2})
craft('mason','Crystal Edge Scalpel',{'clear_crystal':2,'abrasive_powder':1,'fitted_grip':1},tool(cut=5,skin=4,butcher=3),tier=3,use='make fine skinning and cutting work possible with a ground crystal edge',qualities={'crush':2})
craft('mason','Bind Dressed Blocks',{'stone':2,'mortar_mix':1},output='dressed_stone',tier=3,qty=2,use='bind dressed stone for practical construction',qualities={'hammer':2})

# Pottery: clay tools and reusable process catalysts support other professions.
craft('potter','Kiln Grog',{'ceramic_shards':3},qty=2,use='crushed fired ceramic temper for heat-resistant clay',qualities={'crush':1})
craft('potter','Tempered Clay',{'clay_lump':2,'kiln_grog':1},qty=2,use='grog-tempered clay that tolerates hot workshop processes')
craft('potter','Ceramic Mould',{'tempered_clay':2},use='a reusable casting mould for iron tool blanks')
craft('potter','Ceramic Filter Media',{'kiln_grog':2,'mineral_grit':1},qty=2,use='porous mineral media used while filtering herbal extracts')
craft('potter','Ceramic Thimble',{'tempered_clay':1},tool(sew=3),tier=2,use='control a sewing needle when stitching tough fabric')
craft('potter','Hardened Ceramic Edge',{'tempered_clay':1,'abrasive_powder':1},tool(cut=3,scrape=3),tier=2,use='cut soft stock and scrape hide with a hardened ceramic blade')
craft('potter','Ceramic Pestle',{'tempered_clay':2,'tool_handles':1},tool(crush=3),tier=2,use='grind grain, herbs and pigments in workshop recipes')
craft('potter','Kiln Piercing Spike',{'tempered_clay':1,'leather_grip_wrap':1},tool(pierce=3),tier=2,use='pierce leather seams and bore small workshop joints')
craft('potter','Stoneware Crucible',{'tempered_clay':3,'kiln_grog':2},dict(category='material',tags=['craft_intermediate','pot','water_container']),tier=3,use='a reusable heat-resistant vessel for refined metalwork and boiling gathered freshwater')
craft('potter','Glazed Lure Bead',{'tempered_clay':1,'glass_shards':3,'copper_wire':1},tier=3,qty=4,use='a bright bead used to weight and finish fishing lures')
craft('potter','Ceramic Distillation Coil',{'tempered_clay':3,'copper_wire':3},tier=3,use='a reusable coil for condensing concentrated botanical preparations')
craft('potter','Porous Filter Candle',{'ceramic_filter_media':3,'tempered_clay':1},tier=3,use='a reusable filter for clean botanical preparations')

# Milling processes remain distinct: flour, meal, paste and starch are separate
# preparation routes, with all food energy conserved from edible inputs.
craft('miller','Barley Meal',{'barley':3},food(240,('grain',)),qty=2,use='coarse meal for porridge and fermented grain drinks')
craft('miller','Cornmeal',{'corn':3},food(240,('grain',)),qty=2,use='dry meal for griddle cakes and grain porridges')
craft('miller','Bean Flour',{'beans':3},food(240,('protein',)),qty=2,use='milled bean flour for protein-rich crackers')
craft('miller','Cattail Starch',{'cattail_root':3},food(120,('vegetable',)),qty=2,use='strained starch for thickening broth and baking')
craft('miller','Wholegrain Flour',{'wheat':3},food(240,('grain',)),tier=2,qty=2,use='unsifted flour for hearty bread and hardtack')
craft('miller','Flax Meal',{'flax':3},food(168,('grain',)),tier=2,qty=2,use='crushed flax used to enrich travel cakes',qualities={'crush':1})
craft('miller','Roasted Grain Crumble',{'barley_meal':1,'wheat':1},food(336,('grain',)),tier=2,use='toasted grain crumble for durable trail food',station='campfire')
craft('miller','Root Flour',{'wild_carrot':2,'cattail_starch':1},food(168,('vegetable',)),tier=2,use='dried root flour for cakes and thickened stews')
craft('miller','Fine Sifted Flour',{'wholegrain_flour':2},food(240,('grain',)),tier=3,use='fine flour sifted through a reusable cloth sieve',qualities={'crush':2},catalysts={'linen_panel':1})
craft('miller','Mushroom Powder',{'morel':2,'bolete':2},food(168,('vegetable',)),tier=3,qty=2,use='dry mushroom powder for concentrated savory broths')
craft('miller','Grain Binder Paste',{'barley_meal':1,'cattail_starch':1,'clean_water':1},tier=3,use='starch binder used in pulp boards and paper shields',mat='organic')
craft('miller','Grooved Mill Pestle',{'dressed_stone':1,'wooden_dowels':2,'fitted_grip':1},tool(crush=5),tier=3,use='crush hard grain, bone and ore efficiently',qualities={'hammer':2})

# Baking expands techniques rather than enumerating arbitrary ingredient mixes.
craft('baker','Bread Dough',{'wholegrain_flour':2,'clean_water':1},food(18,('grain',)),use='hydrated wholegrain dough for loaves, dumplings and wrapped meals')
craft('baker','Sourdough Starter',{'wholegrain_flour':1,'clean_water':1},food(48,('grain',)),use='an active grain starter for sourdough and malt culture')
craft('baker','Unleavened Flatbread',{'bread_dough':1},food(96,('grain',)),qty=2,use='thin bread cooked rapidly with modest fuel')
craft('baker','Twice Baked Rusk',{'bread':2},food(504,('grain',)),qty=3,use='twice-bake bread into dry, crisp portions for travel meals')
craft('baker','Sourdough Loaf',{'bread_dough':2,'sourdough_starter':1},food(120,('grain',)),tier=2,qty=2,use='fermented bread with a moist crumb')
craft('baker','Bean Crispbread',{'bean_flour':2,'clean_water':1},food(336,('protein','grain')),tier=2,qty=2,use='dry protein-rich crackers for travel meals')
craft('baker','Corn Griddle Cake',{'cornmeal':2,'animal_fat':1},food(96,('grain',)),tier=2,qty=2,use='fat-bound corn cakes cooked on the oven hearth')
craft('baker','Root Dumplings',{'root_flour':1,'bread_dough':1},food(72,('vegetable','grain')),tier=2,qty=2,use='dense dumplings eaten directly or in broth')
craft('baker','Trail Hardtack',{'wholegrain_flour':2,'clean_water':1},food(720,('grain',)),tier=3,qty=3,use='bake dense, dry grain biscuits for travel meals')
craft('baker','Savory Hand Pie',{'bread_dough':1,'minced_game':1,'onion':1},food(96,('grain','protein','vegetable')),tier=3,qty=2,use='seal cooked meat and vegetables into portable baked meals')
craft('baker','Flax Travel Cake',{'flax_meal':1,'roasted_grain_crumble':1,'animal_fat':1},food(336,('grain','fats')),tier=3,qty=2,use='bake dense fat-and-grain cakes for long journeys')
craft('baker','Steam Raised Grain Bun',{'fine_sifted_flour':1,'sourdough_starter':1,'clean_water':1},food(72,('grain',)),tier=3,qty=2,use='steam fermented dough into soft buns',station='campfire')

# Cooking prepares staple techniques and concentrates existing edible sources.
craft('cook','Root Broth',{'wild_carrot':1,'wild_onion':1,'clean_water':1},food(36,('vegetable',)),use='simmer roots into a hydrating edible broth')
craft('cook','Bone Stock',{'bone':1,'clean_water':2,'wild_onion':1},food(36,('vegetable',)),use='extract stock for thickened soup and braised meat')
craft('cook','Wilted Greens',{'dandelion_greens':2,'nettles':1},food(36,('vegetable',)),use='cook gathered greens to make an edible vegetable meal')
craft('cook','Berry Reduction',{'blueberries':3},food(96,('fruit',)),qty=2,use='reduce gathered blueberries into a concentrated ingredient for preserves')
craft('cook','Grain Porridge',{'barley_meal':1,'clean_water':2},food(36,('grain',)),tier=2,qty=2,use='hydrate milled grain into a filling porridge')
craft('cook','Seared Game Portions',{'raw_game_meat':2},food(60,('protein',)),tier=2,qty=2,use='cook game at high heat into safe immediate meals',qualities={'butcher':1})
craft('cook','Braised Meat',{'seared_game_portions':1,'bone_stock':1,'carrot':1},food(48,('protein','vegetable')),tier=2,qty=2,use='slow-cook seared meat with stock and roots')
craft('cook','Thickened Mushroom Soup',{'mushroom_powder':1,'cattail_starch':1,'clean_water':2},food(48,('vegetable',)),tier=2,qty=2,use='thicken a mushroom infusion with extracted root starch')
craft('cook','Potted Meat',{'minced_game':2,'animal_fat':2},food(240,('protein',)),tier=3,qty=2,use='cook and seal minced meat under rendered fat into dense protein portions')
craft('cook','Fruit Preserve',{'berry_reduction':2,'aromatic_oil':1},food(504,('fruit',)),tier=3,qty=2,use='finish reduced berries into an aromatic fruit preserve')
craft('cook','Cabbage Ferment',{'cabbage':3,'clean_water':1},food(336,('vegetable',)),tier=3,qty=2,use='prepare a preserved vegetable ferment')
craft('cook','Travel Stew Concentrate',{'braised_meat':1,'root_dumplings':1,'roasted_grain_crumble':1},food(168,('protein','grain','vegetable')),tier=3,qty=2,use='reduce a complete stew into portable dense portions')

# Brewing: malt, wort, vinegar and aromatic infusions have distinct downstream
# applications; beverages draw all calories and hydration from their ingredients.
craft('brewer','Malted Grain',{'barley':3},food(168,('grain',)),qty=2,use='germinate and dry grain for brewing wort')
craft('brewer','Brewing Wort',{'malted_grain':2,'clean_water':2},food(48,('grain',)),qty=2,use='extract fermentable grain into a brewing base')
craft('brewer','Grain Vinegar',{'small_ale':2},food(504,('grain',)),use='ferment weak ale into preserving vinegar')
craft('brewer','Botanical Brewing Sachet',{'moonmint_sprig':1,'cloth_scraps':2},use='a wrapped rare aromatic plant for clean steeping',mat='organic')
craft('brewer','Malt Tonic Drink',{'brewing_wort':2,'clean_water':1},food(72,('grain',)),tier=2,qty=2,use='make a diluted non-fermented malt drink')
craft('brewer','Grain Table Beer',{'brewing_wort':2,'sourdough_starter':1},food(168,('grain',)),tier=2,qty=2,use='ferment grain wort into a mild drink')
craft('brewer','Soured Root Pickle',{'grain_vinegar':1,'turnip':2},food(336,('vegetable',)),tier=2,qty=2,use='preserve cut roots in grain vinegar')
craft('brewer','Moonmint Infusion',{'botanical_brewing_sachet':1,'clean_water':2,'brewing_wort':1},food(72,('grain',)),tier=2,qty=2,use='steep rare moonmint into a mild aromatic drink')
craft('brewer','Spiced Grain Cordial',{'brewing_wort':2,'sunspice_rhizome':1,'aromatic_oil':1},food(240,('grain',)),tier=3,qty=2,use='condense a rare aromatic grain cordial',catalysts={'ceramic_distillation_coil':1})
craft('brewer','Frost Sage Brew',{'frost_sage_branch':1,'brewing_wort':2,'clean_water':1},food(168,('grain',)),tier=3,qty=2,use='brew cold-habitat sage with malted grain')
craft('brewer','Coastal Kelp Vinegar',{'pearl_kelp_knot':1,'grain_vinegar':2},food(504,('grain',)),tier=3,use='steep coastal kelp into preserving vinegar')
craft('brewer','Filtered Malt Culture',{'brewing_wort':2,'malted_grain':1,'sourdough_starter':1},tier=3,use='a concentrated malt culture for sizing writing stock',catalysts={'porous_filter_candle':1},mat='organic')

# Butchery: animal remains supply real tools, edible preparations and bindings.
craft('butcher','Minced Game',{'meat':2},dict(category='food',tags=['food','raw_meat'],spoilage_hours=24,food_groups=['protein']),qty=2,use='finely cut raw game for hand pies and potted meat',qualities={'butcher':1})
craft('butcher','Rendered Tallow',{'animal_fat':2},food(336,('fats',)),use='rendered edible fat for food preservation and leather care',station='campfire')
craft('butcher','Horn Laminate',{'bone_chips':8,'resin_lumps':1},use='pressed bone-and-keratin scales for shield and armor reinforcement')
craft('butcher','Carved Bone Barb',{'bone_chips':4},qty=3,use='small piercing barbs for hunting arrows and fishing hooks',qualities={'cut':1})
craft('butcher','Butcher Cleaver',{'iron_tool_blank':1,'tool_handles':1,'leather_grip_wrap':1},tool(cut=3,butcher=4),tier=2,use='portion large carcasses with a broad, heavy blade')
craft('butcher','Bone Marrow Scoop',{'bone_chips':6,'tool_handles':1},tool(butcher=3,scrape=2),tier=2,use='work carcass interiors and scrape fresh hides',qualities={'cut':1})
craft('butcher','Hide Fleshing Beam',{'wood_pieces':8,'stone_blade_blank':2},tool(scrape=4),tier=2,use='scrape hides clean before tanning',qualities={'cut':2})
craft('butcher','Sinew Stripper',{'bone_chips':6,'leather_lace':1},tool(cut=2,skin=3),tier=2,use='separate sinew and skin with a shaped keratin edge',qualities={'cut':1})
craft('butcher','Smoked Offal Sausage',{'offal':2,'minced_game':1,'rendered_tallow':1},food(168,('protein',)),tier=3,qty=2,use='smoke seasoned offal and meat into portable sausage',station='smoke_rack')
craft('butcher','Articulated Bone Awl',{'horn_laminate':1,'carved_bone_barb':2,'leather_lace':1},tool(sew=4,pierce=4),tier=3,use='stitch tough leather and pierce reinforced cloth',qualities={'cut':2})
craft('butcher','Antler Skinning Knife',{'deer_antler_tip':2,'abrasive_powder':1,'fitted_grip':1},tool(cut=4,skin=4),tier=3,use='shape intact antler directly into a specialized skinning blade',qualities={'cut':2})
craft('butcher','Bone Hand Shears',{'horn_laminate':2,'hinge_pair':1,'nuts_and_bolts':1},tool(cut=4,sew=3),tier=3,use='trim heavy seams and cut cloth with a hinged bone-and-metal tool',qualities={'pierce':2})

# Fishing: terminal outputs use the existing rod/line/net/lure quality contracts.
craft('fisher','Twisted Reed Line',{'star_reed_tuft':1,'plant_cordage':2},dict(category='material',tags=['fishing_line'],tool_qualities={'line_quality':3}),use='braid rare star reed directly into a fishing line')
craft('fisher','Carved Bone Hook',{'carved_bone_barb':2,'sinew':1},dict(category='utility',tags=['fishing_lure'],tool_qualities={'lure_quality':2}),use='a barbed bone lure for line fishing',station=None)
craft('fisher','Copper Spinner Blade',{'copper_sheet':1,'copper_wire':2},use='a hammered blade for an articulated spinner lure',station='workbench',qualities={'hammer':1})
craft('fisher','Float Rig',{'wood_pieces':1,'copper_wire':1,'resin_lumps':1},dict(category='utility',tags=['fishing_lure'],tool_qualities={'lure_quality':2}),use='a buoyant lure rig for line fishing',station=None)
craft('fisher','Weighted River Net',{'plant_cordage':6,'mineral_grit':2,'waxed_thread':1},dict(category='tool',tags=['tool','fishing_net'],tool_qualities={'net_quality':3}),tier=2,use='keep a net spread in shallow moving water',station=None)
craft('fisher','Jointed Fishing Rod',{'bentwood_frame':1,'fitted_grip':1,'copper_wire':3},dict(category='tool',tags=['tool','fishing_rod'],tool_qualities={'rod_quality':4}),tier=2,use='fight larger fish with a strong jointed rod',station='workbench')
craft('fisher','Split Fish Fillets',{'common_carp':1},dict(category='food',tags=['food','raw_meat','fish'],spoilage_hours=24,food_groups=['protein']),tier=2,qty=2,use='cut fresh carp into boneless cooking portions',qualities={'cut':2})
craft('fisher','Rack Dried Fish',{'split_fish_fillets':2},food(240,('protein',)),tier=2,qty=2,use='dry cut fish into portable protein rations')
craft('fisher','Articulated Spinner Lure',{'copper_spinner_blade':1,'glazed_lure_bead':2,'copper_wire':2,'fine_gear':1},dict(category='utility',tags=['fishing_lure'],tool_qualities={'lure_quality':5}),tier=3,use='attract fish with a moving metal spinner and bright bead',station='workbench')
craft('fisher','Spring Tension Fishing Rod',{'jointed_fishing_rod':1,'tempered_spring':1,'waxed_casting_line':1},dict(category='tool',tags=['tool','fishing_rod'],tool_qualities={'rod_quality':6}),tier=3,use='absorb surges from difficult fish',station='workbench')
craft('fisher','Barbed Fishing Trident',{'iron_tool_blank':2,'planed_board':1,'fitted_grip':1},dict(category='tool',tags=['tool','fishing_spear','weapon'],tool_qualities={'fish_spear':5},weapon_damage=12,damage_type='pierce',weapon_class='spear',reach=2),tier=3,use='spear fish in shallows and defend at pole reach',station='workbench',qualities={'hammer':2})
craft('fisher','Vinegar Preserved Fish',{'split_fish_fillets':2,'coastal_kelp_vinegar':1},food(336,('protein',)),tier=3,qty=2,use='preserve cut fish using coastal aromatic vinegar')

# Farming turns plant waste into conventional fiber, mineralized compost and
# useful cultivation tools; planted crops still obey existing crop definitions.
craft('farmer','Compost Blend',{'plant_scraps':8,'bone_chips':2},use='a matured organic-mineral blend processed into bone meal',station=None)
craft('farmer','Seed Cleaning Screen',{'wood_pieces':3,'plant_cordage':2},tool(scrape=2),use='clean and separate harvested plant stock',station=None)
craft('farmer','Plant Fiber Pulp',{'plant_scraps':6,'clean_water':1},use='washed fiber pulp for cords and paper boards',station=None)
craft('farmer','Garden Dibber',{'tool_handles':1,'bone_chips':3},tool(dig=2,till=1),use='plant and cultivate small plots',station=None,qualities={'cut':1})
craft('farmer','Harvest Sickle',{'iron_tool_blank':1,'tool_handles':1,'leather_grip_wrap':1},tool(cut=3),tier=2,use='cut harvested plants and gather fiber stock',station=None)
craft('farmer','Soil Turning Fork',{'wood_pieces':6,'iron_tool_blank':1,'nuts_and_bolts':2},tool(till=3,dig=3),tier=2,use='turn soil and prepare cultivated plots',station=None)
craft('farmer','Root Lifting Spade',{'iron_tool_blank':2,'tool_handles':1},tool(dig=4,till=2),tier=2,use='dig roots and cultivate compact ground',station=None)
craft('farmer','Save Fiber From Pulp',{'plant_fiber_pulp':1},output='fiber',tier=2,qty=3,use='recover clean conventional fiber from sorted plant scraps',station=None)
craft('farmer','Mineralized Compost Meal',{'compost_blend':2,'mineral_grit':1},output='bone_meal',tier=3,qty=2,use='make existing supported fertilizer from compost and crushed bone',station=None,qualities={'crush':2})
craft('farmer','Long Handled Field Hoe',{'socketed_iron_hoe':1,'planed_board':1,'fitted_grip':1},tool(till=6,dig=4),tier=3,use='prepare larger cultivated plots efficiently',station=None)
craft('farmer','Winnowing Sickle',{'harvest_sickle':1,'hardened_leather':1,'tempered_spring':1},tool(cut=5),tier=3,use='cut tough stalks and prepare advanced fiberwork',station=None)
craft('farmer','Pressed Plant Binder',{'plant_fiber_pulp':2,'resin_lumps':2,'grain_binder_paste':1},tier=3,use='fiber-rich binder for pressed shields and durable paper boards',station=None)

# Herding products are made from butchery remains and gathered pasture stock.
# No recipes create milk, eggs or live animals unsupported by the simulation.
craft('herder','Wool Roving',{'sheep_wool_locks':2},use='cleaned sheep wool for warm felt and yarn',station=None)
craft('herder','Horn Button Set',{'cow_horn_ring':2},qty=3,use='carved horn buttons for reinforced garments',station=None,qualities={'cut':1})
craft('herder','Bristle Brush',{'boar_bristle_patch':2,'tool_handles':1,'resin_lumps':1},tool(scrape=2),use='scrape and clean hide and plant stock',station=None)
craft('herder','Pasture Fiber Bundle',{'sweet_clover_tops':1,'plant_scraps':3},use='sorted pasture fiber for warm cord and felt',station=None)
craft('herder','Fur Felt',{'wool_roving':1,'fox_tail_tuft':1,'spun_yarn':1},tier=2,use='warm layered felt for winter hood and clothing',station=None)
craft('herder','Horn Seam Needle',{'goat_horn_sheath':2,'horn_button_set':1},tool(sew=3,pierce=2),tier=2,use='sew wool and hide garments with a durable horn needle',station=None,qualities={'cut':1})
craft('herder','Braided Wool Cord',{'wool_roving':1,'pasture_fiber_bundle':1},tier=2,qty=2,use='warm strong cord for padded garments and sling straps',station=None)
craft('herder','Tallow Dressing',{'rendered_tallow':1,'amberroot_crown':1},tier=2,use='condition leather with rendered fat and rare resin-bearing root',station=None)
craft('herder','Wool Lined Mitts',{'fur_felt':1,'oiled_leather':1,'braided_wool_cord':1},armor('hands',3,10),tier=3,use='keep hands and forearms warm on cold journeys',station=None,qualities={'sew':2})
craft('herder','Pasture Winter Coat',{'fur_felt':3,'reinforced_cloth':1,'horn_button_set':2},armor('body',4,12),tier=3,use='insulate the torso heavily using wool recovered from carcasses',station=None,qualities={'sew':2})
craft('herder','Horn Shod Staff',{'horn_laminate':1,'planed_board':2,'braided_wool_cord':1},weapon(9,'blunt','staff',reach=2),tier=3,use='strike at reach with a horn-capped walking staff',station=None)
craft('herder','Condition Leather With Tallow',{'cured_leather_panel':1,'tallow_dressing':1},output='leather',tier=3,use='recover flexible conventional leather for equipment and trade',station=None)

# Hunting outputs integrate standard projectile and carcass processing loops.
craft('hunter','Feather Fletching',{'turkey_quill_fan':1,'chicken_quill_bundle':1},qty=4,use='trim intact bird quills into arrow fletching',station=None,qualities={'cut':1})
craft('hunter','Bone Arrow Point',{'wolf_fang_pair':1,'bone_chips':2},qty=3,use='sharp bone points for finished wood arrows',station=None,qualities={'cut':1})
craft('hunter','Shaft Bundle',{'wood_pieces':4},qty=3,use='straightened shafts for standard arrows and hunting spears',station=None,qualities={'cut':1})
craft('hunter','Fur Grip Pad',{'rabbit_foot_tuft':1,'leather_scraps':2},use='a soft grip pad for hunting knives and sling cradles',station=None)
craft('hunter','Make Fletched Arrows',{'shaft_bundle':1,'feather_fletching':1,'bone_arrow_point':1,'resin_lumps':1},output='wood_arrow',tier=2,qty=3,use='make the existing supported arrows used by hunting bows',station=None)
craft('hunter','Bone Hunting Knife',{'bone_arrow_point':2,'fitted_grip':1,'fur_grip_pad':1},tool(cut=3,skin=3,butcher=2),tier=2,use='skin and portion medium game without iron',station=None)
craft('hunter','Weighted Hide Sling',{'leather_lace':3,'fur_grip_pad':1,'braided_wool_cord':1},weapon(8,'blunt','sling',ammo_item='core:sling_stone',range=5),tier=2,use='throw standard sling stones at game',station=None)
craft('hunter','Antler Throwing Dart',{'deer_antler_tip':1,'shaft_bundle':1,'feather_fletching':1},weapon(9,'pierce','thrown',range=4,throwable=True,recovery_percent=75),tier=2,use='throw a recoverable antler-tipped hunting projectile',station=None)
craft('hunter','Barbed Hunting Spear',{'iron_tool_blank':1,'shaft_bundle':2,'carved_bone_barb':2,'leather_lace':1},weapon(16,'pierce','spear',reach=2),tier=3,use='deliver piercing attacks from pole reach',station=None)
craft('hunter','Hunting Reflex Bow',{'laminated_bow_limbs':2,'waxed_casting_line':1,'fur_grip_pad':1},weapon(18,'pierce','bow',ammo_item='core:wood_arrow',range=8,two_handed=True),tier=3,use='shoot standard arrows accurately over longer distances',station=None)
craft('hunter','Tracker Skinning Set',{'antler_skinning_knife':1,'bear_claw_sheath':1,'leather_grip_wrap':1},tool(skin=6,cut=4,butcher=4),tier=3,use='process high-value carcasses with strong skinning tools',station=None)
craft('hunter','Layered Hunter Bracers',{'horn_laminate':1,'fur_felt':1,'hardened_leather':1,'leather_lace':2},armor('hands',6,5),tier=3,use='protect forearms while stalking and fighting game',station=None,qualities={'sew':2})

# Forestry: measured stock, adhesives and bark insulation feed equipment trees.
craft('lumberjack','Timber Wedge',{'wood_pieces':4},qty=2,use='hard wooden wedges for splitting mauls and log tools',station=None,qualities={'cut':1})
craft('lumberjack','Pitch Binder',{'resin_lumps':3,'bark':1},use='thick pitch adhesive for laminated timber shields',station=None)
craft('lumberjack','Hardwood Blank',{'wood':1},qty=2,use='selected straight-grained timber for axes and log hooks',station=None,qualities={'cut':1})
craft('lumberjack','Bark Felt',{'bark':3,'fiber':2},use='layered bark-and-fiber insulation for forestry clothing',station=None)
craft('lumberjack','Timber Hook',{'iron_tool_blank':1,'hardwood_blank':1,'leather_grip_wrap':1},tool(chop=3,pierce=3),tier=2,use='work and pierce timber with a hooked edged head',station=None)
craft('lumberjack','Splitting Maul',{'hardwood_blank':1,'timber_wedge':2,'stone':1},tool(chop=4,hammer=3),tier=2,use='split logs and drive timber wedges',station=None)
craft('lumberjack','Felling Axe',{'iron_tool_blank':2,'hardwood_blank':1,'leather_lace':2},tool(chop=5,cut=2),tier=2,use='harvest substantial trees with a long hafted axe',station=None)
craft('lumberjack','Wood Boring Auger',{'iron_tool_blank':1,'hardwood_blank':1,'nuts_and_bolts':2},tool(pierce=4,cut=3),tier=2,use='bore joinery holes and cut fitted timber',station=None)
craft('lumberjack','Bark Lined Forester Hood',{'bark_felt':2,'oiled_leather':1,'leather_lace':1},armor('head',4,7),tier=3,use='protect and insulate the head during cold forestry work',station=None,qualities={'sew':2})
craft('lumberjack','Pitch Laminated Shield',{'planed_board':3,'pitch_binder':2,'bentwood_frame':1,'leather_lace':2},
      dict(category='armor',tags=['armor','shield'],equip_slot='offhand',shield_type='round',shield_melee_coverage=62,shield_ranged_coverage=72,shield_block=8,shield_stability=60,shield_stamina_cost=4,shield_body_coverage={'head':48,'torso':83,'arms':82,'legs':35}),tier=3,use='block attacks behind pitch-bonded layers of timber',station=None)
craft('lumberjack','Loggers Mattock',{'iron_tool_blank':2,'hardwood_blank':1,'fitted_grip':1},tool(chop=4,dig=4,mine=3),tier=3,use='clear timber roots, dig soil and break softer stone',station=None)
craft('lumberjack','Tensioned Timber Saw',{'metal_frame_saw':1,'tempered_spring':2,'fitted_grip':2,'nuts_and_bolts':2},tool(cut=6,chop=5),tier=3,use='saw and harvest dense timber using a tensioned blade',station=None)

# Mining uses ores and existing tool-quality interactions; no lamp is added
# without an illumination owner and no geological material is created by magic.
craft('miner','Washed Ore Fragments',{'iron_ore':1,'clean_water':1},use='sorted iron-bearing fragments for consolidation in the forge',station=None)
craft('miner','Polishing Slurry',{'abrasive_powder':1,'clean_water':1},use='wet abrasive for grinding optics and crystal cutting edges',station=None)
craft('miner','Sorted Crystal Faces',{'clear_crystal':2,'mineral_grit':1},qty=2,use='selected clear faces for polished lenses and fine blades',station=None)
craft('miner','Copper Granules',{'copper_ore':1},qty=2,use='sorted copper-bearing granules for specialist copper sheet work',station=None,qualities={'hammer':1})
craft('miner','Ore Sifting Screen',{'canvas_panel':1,'wooden_dowels':4,'metal_scraps':2},tool(scrape=3,crush=2),tier=2,use='scrape and work mineral stock in ore-preparation recipes',station=None)
craft('miner','Geologists Hammer',{'iron_tool_blank':1,'tool_handles':1},tool(mine=3,hammer=3,crush=3),tier=2,use='break small veins and dress mineral specimens',station=None)
craft('miner','Iron Splitting Wedges',{'iron_tool_blank':2,'nuts_and_bolts':2},tool(mine=4,hammer=1),tier=2,use='split exposed rock while mining veins',station=None)
craft('miner','Padded Mining Cap',{'felt_padding':1,'hardened_leather':1,'leather_lace':1},armor('head',5,4),tier=2,use='protect the head during travel and underground combat',station=None,qualities={'sew':1})
craft('miner','Hardened Ore Auger',{'iron_tool_blank':2,'tempered_spring':1,'fitted_grip':1,'nuts_and_bolts':3},tool(mine=6,pierce=4),tier=3,use='mine dense exposed mineral seams with a hardened auger',station=None)
craft('miner','Plated Mining Gauntlets',{'segmented_armor_plates':1,'hardened_leather':1,'felt_padding':1,'rivet_set':2},armor('hands',8,3),tier=3,use='protect forearms with padded metal plates',station=None,qualities={'sew':2})
craft('miner','Heavy Quarry Pick',{'iron_tool_blank':3,'hardwood_blank':1,'leather_grip_wrap':2,'rivet_set':1},tool(mine=7,hammer=3),tier=3,use='mine the toughest supported veins with a heavy reinforced pick',station=None)
craft('miner','Crystal Burnisher',{'sorted_crystal_faces':2,'polishing_slurry':1,'fitted_grip':1},tool(crush=5,cut=4,scrape=4),tier=3,use='cut and crush hard stock while preparing fine crafted surfaces',station=None)

# Apothecary intermediates end in existing supported treatments. New names do
# not promise unimplemented wound effects; bandages, splints, tonic and soap
# retain their authoritative combat/disease/sanitation behavior.
craft('healer','Clean Dressing Pad',{'cloth_scraps':4,'linen_panel':1,'clean_water':1},use='washed folded dressing pads finished into supported bandages')
craft('healer','Bitter Herbal Extract',{'medicinal_herb':1,'yarrow':1,'clean_water':1},use='a strained medicinal-herb preparation for tonic')
craft('healer','Silverleaf Powder',{'silverleaf_sprig':1,'medicinal_herb':1},use='rare silverleaf ground for apothecary tonic preparation',qualities={'crush':1})
craft('healer','Marsh Resin Balm',{'marsh_amber_bulb':1,'resin_lumps':2,'animal_fat':1},use='a botanical resin-and-fat base finished into sanitation soap')
craft('healer','Filtered Herb Concentrate',{'bitter_herbal_extract':2,'ceramic_filter_media':1,'saffron_crocus_tuft':1},tier=2,use='filtered rare-botanical concentrate for infection-supportive tonic',catalysts={'porous_filter_candle':1})
craft('healer','Orchid Lotus Essence',{'ghost_orchid_stem':1,'blue_lotus_stalk':1,'aromatic_oil':1},tier=2,use='an aromatic rare-plant essence used in the apothecary tonic process',catalysts={'ceramic_distillation_coil':1})
craft('healer','Fitted Splint Frame',{'tool_handles':2,'cloth_scraps':3,'leather_lace':1},tier=2,use='a fitted frame braced into existing supported fracture splints',qualities={'cut':1})
craft('healer','Stonecrop Cleansing Paste',{'crimson_stonecrop_crown':1,'grain_vinegar':1},tier=2,use='a botanical acidic preparation used in sanitation soap')
craft('healer','Finish Clean Bandages',{'clean_dressing_pad':2,'waxed_thread':1},output='bandage',tier=3,qty=3,use='finish supported wound bandages from washed cloth pads',qualities={'sew':1})
craft('healer','Brace Fitted Splints',{'fitted_splint_frame':2,'leather_lace':1},output='splint',tier=3,qty=2,use='finish supported fracture braces from fitted splint frames')
craft('healer','Compound Botanical Tonic',{'filtered_herb_concentrate':1,'silverleaf_powder':1,'orchid_lotus_essence':1},output='herbal_tonic',tier=3,qty=3,use='compound the existing supported infection-care tonic')
craft('healer','Cure Botanical Soap',{'marsh_resin_balm':1,'stonecrop_cleansing_paste':1},output='soap',tier=3,qty=4,use='finish existing sanitation soap for player trade and household use')

# Scholar crafts bind recovered fibers, prepare optics and supply parchment to
# the existing knowledge-copying economy; terminal gear is mechanically usable.
craft('scholar','Recycled Rag Paper',{'plant_fiber_pulp':1,'cloth_scraps':4},qty=2,use='clean rag paper for parchment stock and layered paper armor')
craft('scholar','Pressed Pulp Board',{'recycled_rag_paper':2,'grain_binder_paste':1},use='dense paper board for reinforced shields and garments')
craft('scholar','Carbon Pigment',{'coal':1,'resin_lumps':1},qty=2,use='resin-bound carbon used to seal paper laminations',qualities={'crush':1})
craft('scholar','Binding Cord',{'spun_yarn':2,'silver_filament':1},qty=2,use='fine reinforced cord for precision needles and layered paper gear')
craft('scholar','Sealed Paper Panel',{'pressed_pulp_board':1,'carbon_pigment':1,'pressed_plant_binder':1},tier=2,use='resin-sealed paper composite for protective clothing and shields')
craft('scholar','Layered Paper Cap',{'recycled_rag_paper':3,'pressed_plant_binder':1,'binding_cord':1},armor('head',3,4),tier=2,use='light layered head protection made from recovered fiber',qualities={'sew':1})
craft('scholar','Bookbinders Needle',{'bone_chips':4,'copper_wire':2,'binding_cord':1},tool(sew=4,pierce=3),tier=2,use='stitch heavy bound paper, leather and textile seams',qualities={'cut':1})
craft('scholar','Polished Crystal Lens',{'sorted_crystal_faces':1,'abrasive_powder':1,'polishing_slurry':1},tier=2,use='a clear magnifying lens for precision sewing tools',qualities={'crush':2})
craft('scholar','Prepare Writing Stock',{'recycled_rag_paper':3,'filtered_malt_culture':1,'grain_binder_paste':1},output='parchment',tier=3,qty=3,use='prepare supported writing stock consumed by the knowledge-copying economy')
craft('scholar','Laminated Paper Shield',{'sealed_paper_panel':3,'bentwood_frame':1,'binding_cord':2,'leather_lace':2},
      dict(category='armor',tags=['armor','shield'],equip_slot='offhand',shield_type='round',shield_melee_coverage=54,shield_ranged_coverage=63,shield_block=5,shield_stability=35,shield_stamina_cost=2,shield_body_coverage={'head':37,'torso':75,'arms':79,'legs':27}),tier=3,use='block attacks with a lightweight frame and layered sealed fiber')
craft('scholar','Lens Mounted Needle',{'polished_crystal_lens':1,'bookbinders_needle':1,'silver_filament':1,'fine_gear':1},tool(sew=5,pierce=4),tier=3,use='control fine sewing under a built-in magnifying lens')
craft('scholar','Layered Paper Coat',{'sealed_paper_panel':2,'reinforced_cloth':1,'binding_cord':2},armor('body',5,5),tier=3,use='protect and insulate the torso with sealed paper laminations',qualities={'sew':2})


def finalize():
    """Resolve physical measures and food statistics without creating energy.

    Food receives 90% of input calories/macros, divided across the batch.
    Water-only/botanical ingredients cannot create nutrition. Artifacts and
    intermediate components use 80% of input mass after processing losses.
    Existing item definitions are not changed.
    """
    base={x['id']:x for x in json.loads((DATA/'items.json').read_text())
          if not str(x.get('sprite_tag','')).startswith(('salvage_','craft_','component_'))}
    catalog={**base,**{x['id']:x for x in new_items}}
    made={x['id']:x for x in new_items if x.get('sprite_tag','').startswith('craft_')}
    pending=[r for r in new_recipes if next(iter(r['outputs'])) in made]
    resolved=set(catalog)-set(made)
    while pending:
        progress=False
        for r in pending[:]:
            if not set(r['inputs']).issubset(resolved):continue
            out=next(iter(r['outputs']));qty=r['outputs'][out];item=made[out]
            mass=sum(catalog[k]['mass_g']*n for k,n in r['inputs'].items())
            volume=sum(catalog[k]['volume_ml']*n for k,n in r['inputs'].items())
            item['mass_g']=max(1,mass*80//(100*qty))
            item['volume_ml']=max(1,volume*75//(100*qty))
            if item['category']=='food':
                for stat in ('calories','protein','carbs','fat','fiber','nutrition','hydration'):
                    raw=sum(catalog[k].get(stat,0)*n for k,n in r['inputs'].items())
                    item[stat]=max(0,raw*90//(100*qty))
                if item.get('calories',0)>0:item['nutrition']=max(1,item['calories']//12)
                item['food_groups']=sorted({group for k in r['inputs']
                    if catalog[k].get('calories',0)>0 or catalog[k].get('nutrition',0)>0
                    for group in catalog[k].get('food_groups',())
                    if group in {'protein','vegetable','grain','fruit','fats'}})
            resolved.add(out);pending.remove(r);progress=True
        if not progress:
            raise ValueError('Unreachable/cyclic craft inputs: '+', '.join(r['id'] for r in pending))
    # Thermal processing of known base foods keeps conservative ingredient
    # energy; tags determine dynamic cooking eligibility, not extra nutrition.
    assert len({x['id'] for x in new_items})==len(new_items), 'duplicate output item'
    assert len({x['id'] for x in new_recipes})==len(new_recipes), 'duplicate recipe'
    assert len(salvage)>200 and len(new_recipes)>200
    coverage=Counter(row['profession'] for row in manifest['recipes'])
    assert set(coverage)==set(PROFESSION) and min(coverage.values())>=12, coverage
    recoverable_rares={drop['item_id'] for row in salvage for drop in row['rare_yields']}
    assert set(manifest['rare_components'])<=recoverable_rares, 'rare component without a physical source'
    sources={x['id'] for x in catalog.values()}
    for r in new_recipes:
        assert set(r['inputs'])<=sources, r
        assert len(r['discovery_items'])<=5, r
        out=next(iter(r['outputs']))
        output_mass=catalog[out]['mass_g']*r['outputs'][out]
        input_mass=sum(catalog[k]['mass_g']*n for k,n in r['inputs'].items())
        if output_mass>input_mass:
            raise ValueError(f'Mass creation in {r["id"]}: {input_mass} -> {output_mass}')
        if out in made and made[out]['category']=='food':
            if catalog[out].get('nutrition',0)<=0:
                raise ValueError('Inedible food output in '+r['id'])
            assert set(catalog[out].get('food_groups',())) <= {'protein','vegetable','grain','fruit','fats'}, r
    # Every intermediate must lead to a real terminal effect. A declaration of
    # utility_roles alone is deliberately insufficient for this catalog.
    sinks={k for r in new_recipes for k in (*r['inputs'],*r.get('catalysts',{}))}
    for item in made.values():
        actual=bool(item.get('tool_qualities') or item.get('weapon_damage') or item.get('equip_slot')
                    or item.get('nutrition') or item.get('hydration'))
        if not actual and item['id'] not in sinks:
            raise ValueError('No implemented use for '+item['id'])


if __name__=='__main__':
    finalize()
    save()
    print('Professions:', dict(Counter(x['profession'] for x in manifest['recipes'])))
