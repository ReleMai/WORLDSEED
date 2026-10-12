"""Visible v2 variation and exact compatibility with the Dev61 face renderer."""
from __future__ import annotations

from dataclasses import fields, replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from worldseed.presentation import portraits
from worldseed.presentation.portraits import (
    PortraitComposer,
    portrait_catalog,
    portrait_spec,
    render_portrait,
    validate_portrait_catalog,
)
from worldseed.systems.state import LivingWorldState, NPCState


_OPTIONAL_PARTS = ("tattoo", "markings", "accessory", "shading", "cloth_detail")


def unobscured_spec():
    """Hold identity/proportions constant so overlays cannot hide variation."""
    spec = portrait_spec(b"WORLDSEED:Dev62:feature-proof", "npc:feature:baseline", "unknown", 35, version=2)
    changes = {
        "head": "core:oval", "jaw": "core:soft", "ears": "core:wide",
        "nose": "core:straight", "eyes": "core:round", "brows": "core:straight",
        "mouth": "core:full", "hair": "core:bald", "facial_hair": "core:none",
        "neck": "core:regular", "bust": "core:broad", "skin_palette": "core:sand",
        "hair_palette": "core:chestnut", "eye_palette": "core:blue",
        "cloth_palette": "core:indigo", "complexion": 0, "detail": 0,
        "eye_spacing": 0, "eye_height": 0, "asymmetry": 0,
    }
    catalog = portrait_catalog(version=2)
    for group in _OPTIONAL_PARTS:
        variants = catalog["parts"][group]
        plain = next((key for key, value in variants.items()
                      if value.get("style") in ("none", "plain", "balanced", "soft")), None)
        changes[group] = plain or next(iter(variants))
    return replace(spec, **changes)


class ExpandedPortraitIdentityTests(unittest.TestCase):
    def test_legacy_catalog_keeps_original_fingerprint_for_unsampled_faces(self):
        manifest = json.loads((Path(__file__).parent / "fixtures" / "portrait_v1_fingerprints.json").read_text())
        catalog_path = Path(portraits.__file__).resolve().parents[1] / "data" / "portrait_features_v1.json"
        # Git on Windows may check out this JSON with CRLF even though the
        # frozen Dev61 compatibility fixture was fingerprinted with LF.
        # Normalize only line endings; never relax the actual content hash.
        canonical_bytes = catalog_path.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(canonical_bytes).hexdigest(), manifest["catalog_sha256"])
        self.assertEqual(
            hashlib.sha256(canonical_bytes.replace(b"\n", b"\r\n").replace(b"\r\n", b"\n")).hexdigest(),
            manifest["catalog_sha256"],
        )

    def test_legacy_descriptors_keep_all_recorded_original_fields(self):
        manifest = json.loads((Path(__file__).parent / "fixtures" / "portrait_v1_fingerprints.json").read_text())
        self.assertEqual(len(manifest["cases"]), 48)
        for case in manifest["cases"]:
            with self.subTest(uid=case["uid"], age=case["age"]):
                spec = portrait_spec(bytes.fromhex(case["seed_hex"]), case["uid"], case["sex"], case["age"], version=1)
                self.assertEqual({name: getattr(spec, name) for name in case["spec"]}, case["spec"])

    def test_catalogs_are_detached_and_expansion_has_required_layers(self):
        legacy, expanded = portrait_catalog(version=1), portrait_catalog(version=2)
        self.assertEqual((legacy["version"], expanded["version"]), (1, 2))
        self.assertTrue(set(_OPTIONAL_PARTS).issubset(expanded["parts"]))
        self.assertTrue({"ink", "metal"}.issubset(expanded["palettes"]))
        for group in ("eyes", "hair", "bust", "head", "nose", "brows", "mouth"):
            self.assertGreater(len(expanded["parts"][group]), len(legacy["parts"][group]), group)
        for group in ("skin", "hair", "eye", "cloth"):
            self.assertGreater(len(expanded["palettes"][group]), len(legacy["palettes"][group]), group)
        expanded["parts"]["tattoo"].clear()
        self.assertTrue(portrait_catalog(version=2)["parts"]["tattoo"])
        self.assertEqual(portrait_catalog(version=1), legacy)

    def test_new_identity_does_not_depend_on_generation_order_or_catalog_order(self):
        uids = [f"npc:dev62:{index}" for index in range(60)]
        before_rng = random.getstate()
        forward = {uid: portrait_spec(b"v2-order", uid, "male", version=2) for uid in uids}
        reverse = {uid: portrait_spec(b"v2-order", uid, "male", version=2) for uid in reversed(uids)}
        self.assertEqual(forward, reverse)
        reordered = portrait_catalog(version=2)
        for section in ("parts", "palettes"):
            for group, variants in reordered[section].items():
                reordered[section][group] = dict(reversed(list(variants.items())))
        with patch.object(portraits, "_catalog", return_value=reordered):
            self.assertEqual(forward[uids[0]], portrait_spec(b"v2-order", uids[0], "male", version=2))
        self.assertEqual(random.getstate(), before_rng)

    def test_new_feature_domains_do_not_reroll_unrelated_parts(self):
        original = portrait_spec(b"feature-domain", "npc:fixed", "female", version=2)
        catalog = portrait_catalog(version=2)
        for group in _OPTIONAL_PARTS:
            edited = json.loads(json.dumps(catalog))
            existing = next(iter(edited["parts"][group].values()))
            edited["parts"][group]["core:additional_test_variant"] = existing.copy()
            with patch.object(portraits, "_catalog", return_value=edited):
                updated = portrait_spec(b"feature-domain", "npc:fixed", "female", version=2)
            for field in fields(original):
                if field.name != group:
                    self.assertEqual(getattr(original, field.name), getattr(updated, field.name), (group, field.name))

    def test_unsupported_versions_are_rejected_by_generation_and_catalog(self):
        for version in (0, 3, -1, "2", None, True):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    portrait_spec(b"version", "npc:version", "female", version=version)
                with self.assertRaises(ValueError):
                    portrait_catalog(version=version)

    def test_new_layers_reject_bad_styles_parameters_weights_and_palettes(self):
        validate_portrait_catalog(portrait_catalog(version=2))
        for group in _OPTIONAL_PARTS:
            for mutation in ("style", "extra_parameter", "weight"):
                catalog = portrait_catalog(version=2)
                variant = next(iter(catalog["parts"][group].values()))
                if mutation == "style":
                    variant["style"] = "unsupported_style"
                elif mutation == "extra_parameter":
                    variant["unexpected"] = 1
                else:
                    variant["weights"]["unknown"] = -1
                with self.subTest(group=group, mutation=mutation):
                    with self.assertRaises(ValueError):
                        validate_portrait_catalog(catalog)
        for group in ("ink", "metal"):
            for mutation in ("color", "length", "missing"):
                catalog = portrait_catalog(version=2)
                variants = catalog["palettes"][group]
                variant = next(iter(variants.values()))
                if mutation == "color":
                    variant["colors"][0][0] = 256
                elif mutation == "length":
                    variant["colors"].pop()
                else:
                    del catalog["palettes"][group]
                with self.subTest(group=group, mutation=mutation):
                    with self.assertRaises(ValueError):
                        validate_portrait_catalog(catalog)


@unittest.skipUnless(importlib.util.find_spec("pygame"), "requires pygame-ce")
class ExpandedPortraitRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pygame
        cls.pg = pygame

    def pixels(self, spec, size=64):
        return self.pg.image.tobytes(render_portrait(spec, size), "RGBA")

    def test_legacy_pixels_match_every_recorded_dev61_face(self):
        manifest = json.loads((Path(__file__).parent / "fixtures" / "portrait_v1_fingerprints.json").read_text())
        for case in manifest["cases"]:
            with self.subTest(uid=case["uid"], age=case["age"]):
                spec = portrait_spec(bytes.fromhex(case["seed_hex"]), case["uid"], case["sex"], case["age"], version=1)
                self.assertEqual(hashlib.sha256(self.pixels(spec, manifest.get("size", 64))).hexdigest(), case["rgba_sha256"])

    def test_every_expanded_style_changes_actual_pixels_on_same_face(self):
        baseline, catalog = unobscured_spec(), portrait_catalog(version=2)
        for group in catalog["parts"]:
            active = replace(baseline, hair="core:crop") if group == "accessory" else baseline
            for size in (64, 128):
                fingerprints = {}
                for key in catalog["parts"][group]:
                    pixels = self.pixels(replace(active, **{group: key}), size)
                    digest = hashlib.sha256(pixels).hexdigest()
                    with self.subTest(group=group, key=key, size=size):
                        self.assertNotIn(digest, fingerprints, f"{key} renders identically to {fingerprints.get(digest)}")
                    fingerprints[digest] = key

    def test_expanded_palettes_change_visible_features(self):
        catalog = portrait_catalog(version=2)
        baseline = replace(unobscured_spec(), hair="core:crop")
        for group in catalog["palettes"]:
            active = baseline
            associated = {"ink": "tattoo", "metal": "accessory"}.get(group)
            if associated:
                active_key = next(key for key, value in catalog["parts"][associated].items()
                                  if value.get("style") != "none")
                active = replace(active, **{associated: active_key})
            fingerprints = {}
            for key in catalog["palettes"][group]:
                digest = hashlib.sha256(self.pixels(replace(active, **{group + "_palette": key}))).hexdigest()
                with self.subTest(group=group, key=key):
                    self.assertNotIn(digest, fingerprints, f"{key} renders identically to {fingerprints.get(digest)}")
                fingerprints[digest] = key

    def test_expansion_aging_keeps_identity_and_changes_pixels(self):
        specs = [portrait_spec(b"v2-aging", "npc:age:fixed", "female", age, version=2) for age in (12, 35, 80)]
        self.assertEqual(len({spec.facial_identity for spec in specs}), 1)
        self.assertEqual(len({self.pixels(spec) for spec in specs}), 3)

    def test_skin_and_clothing_overlays_preserve_their_base_silhouette(self):
        baseline = unobscured_spec()
        alpha = self.pixels(baseline)[3::4]
        catalog = portrait_catalog(version=2)
        for group in ("tattoo", "markings", "cloth_detail", "shading"):
            for key in catalog["parts"][group]:
                with self.subTest(group=group, key=key):
                    self.assertEqual(self.pixels(replace(baseline, **{group: key}))[3::4], alpha)

    def test_neck_tattoos_do_not_paint_raised_clothing_or_the_lower_face(self):
        catalog = portrait_catalog(version=2)
        baseline = unobscured_spec()
        neck_colors = {tuple(color) for color in catalog["palettes"]["skin"][baseline.skin_palette]["colors"]}
        for head, jaw in (("core:oval", "core:soft"), ("core:long", "core:long_chin")):
            chin = 29 + catalog["parts"]["head"][head]["height"] + catalog["parts"]["jaw"][jaw]["chin"]
            # On the longer face the lowest jaw covers the upper tattoo band.
            # This central patch includes the chin's outer contour as well as
            # its fill, both of which must stay unchanged by a neck tattoo.
            lower_face = {(x, y) for y in range(44, chin + 1) for x in range(29, 36)}
            for bust in ("core:high_collar", "core:hood", "core:mantle"):
                plain = replace(baseline, head=head, jaw=jaw, bust=bust)
                before = render_portrait(plain, 64)
                tattooed = render_portrait(replace(plain, tattoo="core:neck_bands"), 64)
                changed = {(x, y) for y in range(64) for x in range(64)
                           if before.get_at((x, y)) != tattooed.get_at((x, y))}
                with self.subTest(head=head, jaw=jaw, bust=bust):
                    self.assertTrue(changed, "The exposed neck must still show its tattoo")
                    self.assertFalse(changed & lower_face, "Neck ink touched the lower face or its outline")
                    for point in changed:
                        self.assertIn(tuple(before.get_at(point))[:3], neck_colors,
                                      f"Neck ink covered clothing, an outline or a shaded face pixel at {point}")
                        self.assertTrue(27 <= point[0] <= 37 and 49 <= point[1] <= 55)
                    self.assertEqual(self.pg.image.tobytes(before, "RGBA")[3::4],
                                     self.pg.image.tobytes(tattooed, "RGBA")[3::4])

    def test_youth_keep_identity_without_adult_tattoos_or_facial_hair(self):
        catalog = portrait_catalog(version=2)
        youth = replace(unobscured_spec(), age_stage="youth")
        plain = self.pixels(youth)
        for group in ("tattoo", "facial_hair"):
            for key in catalog["parts"][group]:
                with self.subTest(group=group, key=key):
                    self.assertEqual(self.pixels(replace(youth, **{group: key})), plain)

    def test_cache_separates_versions_new_layers_and_stays_bounded(self):
        cache = PortraitComposer(max_entries=4, max_bytes=4 * 128 * 128 * 4)
        baseline = unobscured_spec()
        original = cache.render(baseline, 64)
        self.assertIs(cache.render(baseline, 64), original)
        catalog = portrait_catalog(version=2)
        for group in _OPTIONAL_PARTS:
            key = next(key for key in catalog["parts"][group] if key != getattr(baseline, group))
            changed = replace(baseline, **{group: key})
            self.assertIsNot(cache.render(changed, 64), original)
            self.assertLessEqual(cache.cache_size, 4)
            self.assertLessEqual(cache.cache_bytes, cache.max_bytes)
        for version in (1, 2):
            cache.render(portrait_spec(b"cache-version", "npc:same", "male", version=version), 128)
            self.assertLessEqual(cache.cache_size, 4)
            self.assertLessEqual(cache.cache_bytes, cache.max_bytes)

    def test_rendering_all_layers_is_read_only(self):
        state = LivingWorldState()
        npc = NPCState("npc:dev62:read-only", "Vera", 35, "healer", ["patient"], 1, 2, 0, "", "")
        state.npcs[npc.uid] = npc
        before, rng_before = state.to_dict(), random.getstate()
        composer = PortraitComposer(max_entries=4)
        spec = portrait_spec(b"read-only", npc.uid, npc.sex, npc.age, version=2)
        for size in (64, 128, 96, 64):
            composer.render(spec, size)
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(random.getstate(), rng_before)

    def test_renderer_rejects_unknown_version(self):
        with self.assertRaises(ValueError):
            render_portrait(replace(unobscured_spec(), version=3), 64)


if __name__ == "__main__":
    unittest.main()
