"""Authored expansion has physical suppliers and executable gameplay sinks."""
from collections import Counter
import json
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import unittest

from tools.audit_content import audit
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.farm_compounds import starting_farm_seeds, terrain_crop_ids
from worldseed.systems.food import FOOD_GROUPS, NutritionSystem
from worldseed.systems.metallurgy import MetallurgySystem
from worldseed.systems.state import LivingWorldState


PROFESSIONS = {
    'smith', 'carpenter', 'weaver', 'tanner', 'mason', 'potter', 'miller',
    'baker', 'cook', 'brewer', 'butcher', 'fisher', 'farmer', 'herder',
    'hunter', 'lumberjack', 'miner', 'healer', 'scholar',
}


class CraftingExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.manifest = json.loads((Path(DATA_DIR) / 'crafting_expansion.json').read_text())
        cls.rows = cls.manifest['recipes']
        cls.recipes = [cls.registry.recipes[row['recipe_id']] for row in cls.rows]
        cls.raw_items = {row['id']: row for row in json.loads((Path(DATA_DIR) / 'items.json').read_text())}
        cls.new_outputs = {iid for iid, row in cls.raw_items.items()
                           if row.get('sprite_tag', '').startswith('craft_')}

    def test_all_professions_have_distinct_multistage_work(self):
        counts = Counter(row['profession'] for row in self.rows)
        self.assertEqual(set(counts), PROFESSIONS)
        self.assertGreater(len(self.manifest['misc']), 200)
        self.assertGreater(len(self.recipes), 200)
        self.assertGreater(len(self.new_outputs), 200)
        self.assertEqual(len({recipe.id for recipe in self.recipes}), len(self.recipes))
        for profession in PROFESSIONS:
            self.assertGreaterEqual(counts[profession], 12, profession)
            self.assertEqual({row['tier'] for row in self.rows if row['profession'] == profession}, {1, 2, 3})
        self.assertEqual(audit(self.registry), [])

    def test_every_recipe_can_be_learned_from_carried_samples(self):
        for recipe in self.recipes:
            with self.subTest(recipe=recipe.id):
                state = LivingWorldState(player_crafting_discovery_enabled=True)
                crafting = CraftingSystem(state, self.registry)
                signature = crafting.discovery_signature(recipe)
                self.assertTrue(1 <= len(signature) <= 5)
                self.assertLessEqual(set(signature), set(recipe.inputs) | {"tag:" + tag for tag in recipe.input_tags})
                samples = crafting.discovery_examples(recipe)
                self.assertTrue(crafting.discovery_matches(recipe, samples))
                inv = Inventory(dict(Counter(samples)))
                candidates = crafting.pot_candidates(samples, inv)
                self.assertIn(recipe.id, {candidate.id for candidate in candidates})
                # Each successful mix consumes physical samples and removes one
                # unknown candidate, so ambiguous recipes still have a bound.
                for _ in candidates:
                    inv.items = dict(Counter(samples))
                    before = set(state.player_discovered_recipes)
                    self.assertTrue(crafting.combine_in_pot(samples, inv, b'content-learn')[0])
                    self.assertEqual(len(set(state.player_discovered_recipes) - before), 1)
                    learned_id=next(iter(set(state.player_discovered_recipes)-before))
                    expected={iid:1 for iid,n in self.registry.recipes[learned_id].outputs.items() if n>0}
                    self.assertEqual(inv.items,expected)
                    if crafting.recipe_is_discovered(recipe.id):
                        break
                self.assertTrue(crafting.recipe_is_discovered(recipe.id))

    def test_recovery_and_crafting_conserve_mass(self):
        for definition in self.registry.salvage.values():
            maximum = sum(self.registry.items[iid].mass_g * high
                          for iid, (_, high) in definition.yields.items())
            maximum += sum(self.registry.items[drop.item_id].mass_g * drop.max
                           for drop in definition.rare_yields)
            self.assertLessEqual(maximum, self.registry.items[definition.item_id].mass_g, definition.id)
        for recipe in self.recipes:
            output = sum(self.registry.items[iid].mass_g * n for iid, n in recipe.outputs.items())
            consumed = sum(self.registry.items[iid].mass_g * n for iid, n in recipe.inputs.items())
            consumed += sum(min(Fraction(item.mass_g, recipe.input_units.get(item.id, 1))
                                for item in self.registry.items.values() if tag in item.tags) * n
                            for tag, n in recipe.input_tags.items())
            self.assertLessEqual(output, consumed, recipe.id)
            for iid in recipe.outputs:
                self.assertGreater(self.registry.items[iid].mass_g, 0, iid)
                self.assertGreater(self.registry.items[iid].volume_ml, 0, iid)

    def test_food_energy_and_diet_groups_come_from_edible_inputs(self):
        for recipe in self.recipes:
            for iid, count in recipe.outputs.items():
                if iid not in self.new_outputs or self.registry.items[iid].category != 'food':
                    continue
                with self.subTest(food=iid):
                    item = self.registry.items[iid]
                    self.assertGreater(item.nutrition, 0)
                    for stat in ('calories', 'protein', 'carbs', 'fat', 'fiber', 'hydration'):
                        raw = sum(getattr(self.registry.items[k], stat) * n for k, n in recipe.inputs.items())
                        self.assertEqual(getattr(item, stat), raw * 90 // (100 * count), stat)
                    groups = {g for k in recipe.inputs
                              if self.registry.items[k].calories or self.registry.items[k].nutrition
                              for g in self.registry.items[k].food_groups if g in FOOD_GROUPS}
                    self.assertEqual(set(item.food_groups), groups)
                    state = LivingWorldState()
                    vitals = Vitals(hunger=100, thirst=100)
                    NutritionSystem(state, self.registry).consume_item(iid, vitals, 0)
                    self.assertLess(vitals.hunger, 100)
                    self.assertEqual(set(state.player_diet_history[-1]['groups']), groups)

    def test_every_intermediate_reaches_an_implemented_terminal_use(self):
        useful = {iid for iid, item in self.registry.items.items()
                  if item.tool_qualities or item.weapon_damage or item.equip_slot
                  or item.nutrition or item.hydration}
        # Existing medicines, fertilizer, writing stock and construction stock
        # have authoritative consumers outside generic item-stat behavior.
        useful.update({'core:bandage', 'core:splint', 'core:herbal_tonic', 'core:soap',
                       'core:bone_meal', 'core:parchment', 'core:dressed_stone'})
        while True:
            before = len(useful)
            for recipe in self.recipes:
                if set(recipe.outputs) & useful:
                    useful.update(recipe.inputs)
                    useful.update(recipe.catalysts)
            if len(useful) == before:
                break
        self.assertLessEqual(self.new_outputs, useful)
        for row in self.manifest['misc']:
            item = self.registry.items[row['item_id']]
            self.assertEqual(item.nutrition, 0, item.id)
            self.assertNotIn('food', item.tags, item.id)
            definition = self.registry.salvage[item.id]
            self.assertLessEqual(set(definition.yields), useful)
            if row['source'] == 'wild' and row['rarity'] == 'rare':
                self.assertTrue(any(item.id in recipe.inputs for recipe in self.recipes), item.id)

    def test_rare_returns_have_physical_sources(self):
        drops = {drop.item_id for definition in self.registry.salvage.values()
                 for drop in definition.rare_yields}
        self.assertLessEqual(set(self.manifest['rare_components']), drops)
        for iid in ('core:cow_horn_ring', 'core:wolf_fang_pair', 'core:deer_antler_tip'):
            self.assertFalse(self.registry.salvage[iid].rare_yields, iid)
        for iid in ('core:turkey_quill_fan', 'core:chicken_quill_bundle', 'core:heron_pinion_quills'):
            self.assertNotIn('core:bone_chips', self.registry.salvage[iid].yields)
        for iid in ('core:reindeer_lichen_mat', 'core:flax_seed_capsule', 'core:dried_onion_skins'):
            self.assertNotIn('core:resin_lumps', self.registry.salvage[iid].yields)
        for iid in ('core:split_chalk_marker', 'core:cracked_hearth_brick', 'core:fractured_mortar_block'):
            self.assertFalse(self.registry.salvage[iid].rare_yields)
        embroidery = self.registry.salvage['core:tangled_embroidery']
        self.assertIn('core:silver_filament', {drop.item_id for drop in embroidery.rare_yields})

    def test_new_intermediate_dependencies_have_no_required_cycle(self):
        resolved = set(self.registry.items) - self.new_outputs
        pending = [recipe for recipe in self.recipes if set(recipe.outputs) & self.new_outputs]
        while pending:
            ready = [recipe for recipe in pending if set(recipe.inputs) | set(recipe.catalysts) <= resolved]
            self.assertTrue(ready, 'Required crafting cycle: ' + ', '.join(recipe.id for recipe in pending))
            for recipe in ready:
                resolved.update(recipe.outputs)
                pending.remove(recipe)

    def test_primitive_supplier_graph_unlocks_every_recipe_and_station(self):
        r = self.registry
        reached = {row['item_id'] for row in self.manifest['misc'] if row['source'] == 'village'}
        # Seed capital is allocated by the real terrain-first new-town setup,
        # so seeds can enter trade without presuming storage loot creates them.
        for wetness, fertility in ((80, 50), (50, 80), (20, 50), (50, 50)):
            stocks = {'core:wheat_seed': 40, 'core:turnip_seed': 20}
            env = SimpleNamespace(wetness=wetness, soil_fertility=fertility)
            starting_farm_seeds(stocks, terrain_crop_ids(env, r), r)
            reached.update(iid for iid, n in stocks.items() if n > 0)
        stations, executed = set(), set()
        quality_keys = {'cut', 'chop', 'mine', 'skin', 'butcher'} | {
            key for item in r.items.values() for key in item.tool_qualities}
        for _ in range(len(r.items)):
            before = (len(reached), len(stations), len(executed))
            quality = {key: max((r.items[iid].quality(key) for iid in reached), default=0)
                       for key in quality_keys}
            for feature in r.resources.values():
                key = {'axe': 'chop', 'pick': 'mine', 'knife': 'cut'}.get(feature.required_tool_tag, feature.required_tool_tag)
                if not key or quality.get(key, 0) >= feature.required_tool_power:
                    reached.update(feature.yields)
                    reached.update(feature.container_loot)
            for terrain in r.terrains.values():
                if terrain.gather_item and (not {'rock', 'ore'} & set(terrain.tags) or quality['mine'] >= 1):
                    reached.add(terrain.gather_item)
            if quality['cut'] >= 1:
                for species in r.species.values():
                    reached.update(species.carcass)
                    reached.update(part['item'] for part in species.harvest_parts if part.get('item'))
            for fish in r.fish.values():
                if 'hand' in fish.methods or any(quality.get(key, 0) for key in ('fish_spear', 'rod_quality', 'net_quality')):
                    reached.add(fish.item_id)
            for crop in r.crops.values():
                if crop.seed_item in reached:
                    reached.add(crop.harvest_item)
            for structure in r.structures.values():
                if set(structure.cost) <= reached:
                    stations.add(structure.id)
            # CollectWaterCommand boils a real freshwater source using a pot
            # and an established fire station; water is not granted on spawn.
            if 'core:campfire' in stations and any('pot' in r.items[iid].tags for iid in reached):
                reached.add('core:clean_water')
            for definition in r.salvage.values():
                if definition.item_id in reached and all(quality.get(k, 0) >= n for k, n in definition.tool_qualities.items()):
                    reached.update(definition.yields)
                    reached.update(drop.item_id for drop in definition.rare_yields)
            for recipe in r.recipes.values():
                if (set(recipe.inputs) | set(recipe.catalysts) <= reached
                        and (not recipe.station or recipe.station in stations)
                        and all(quality.get(k, 0) >= n for k, n in recipe.tool_qualities.items())):
                    reached.update(recipe.outputs)
                    executed.add(recipe.id)
            if before == (len(reached), len(stations), len(executed)):
                break
        self.assertLessEqual({recipe.id for recipe in self.recipes}, executed)
        self.assertLessEqual(self.new_outputs, reached)

    def test_refined_ores_create_real_metal_batches(self):
        for rid, process, iid in (
            ('core:craft_smelt_sorted_iron_fragments', 'smelt_iron', 'core:iron_bloom'),
            ('core:craft_smelt_selected_copper_granules', 'smelt_copper', 'core:copper_ingot'),
        ):
            state = LivingWorldState()
            metallurgy = MetallurgySystem(state, self.registry, b'content-metal')
            crafting = CraftingSystem(state, self.registry, metallurgy=metallurgy)
            recipe = self.registry.recipes[rid]
            self.assertEqual(recipe.process, process)
            inv = Inventory(dict(recipe.inputs))
            self.assertTrue(crafting.craft(rid, inv, {recipe.station}, 10)[0])
            self.assertEqual(inv.items, {iid: 1})
            batches = metallurgy.batches('player', iid)
            self.assertEqual(len(batches), 1)
            self.assertEqual(batches[0].mass_g, self.registry.items[iid].mass_g)
            self.assertEqual(batches[0].heat_until_minute, 10 + recipe.minutes)


if __name__ == '__main__':
    unittest.main()
