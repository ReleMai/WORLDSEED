"""Immutable, version-pinned production morphology recipes.

This module selects normalized planning hints only. Terrain legality, stable
plan objects, workers and economic capacity remain the planner's authority.
The v11 catalog is frozen geography: changes require a new versioned catalog.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from types import MappingProxyType

from worldseed.core.rng import hash_u64

LAYOUT_VERSION = 11
LAYOUT_NAMESPACE = "settlement-production-layout-v11"
RESOURCE_KINDS = frozenset({"mining", "logging", "farming", "livestock", "fishing"})
WORKSITE_PURPOSES = MappingProxyType({"mining": "mine_approach", "logging": "logging_yard",
                                    "farming": "field", "livestock": "animal_pen", "fishing": "fishery"})
RANKS = ("homestead", "hamlet", "village", "town", "city")
ENV_FIELDS = frozenset({"slope", "relief", "soil_fertility", "wetness", "drainage", "flood_risk",
                        "farmland", "resources.forage", "resources.timber", "resources.stone",
                        "resources.freshwater", "resource_opportunity"})
CULTURE_STYLES = frozenset({"timber_courtyard", "stone_lane", "wattle_common", "market_green", "fortified_lane", "riverfront"})
_ID = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$")


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in {low}..{high}")
    return value


def _weights(value, fields=ENV_FIELDS):
    if not isinstance(value, dict) or any(key not in fields for key in value):
        raise ValueError("Unknown or malformed scoring field")
    return MappingProxyType({key: _integer(weight, 0, 20, "weight") for key, weight in sorted(value.items())})


def _inverse_fields(raw, weights):
    if (not isinstance(raw, list) or any(not isinstance(field, str) for field in raw)
            or len(set(raw)) != len(raw) or any(field not in weights for field in raw)):
        raise ValueError("Inverse fields must be unique fields present in the weights")
    return tuple(sorted(raw))


def _field(env, path):
    value = env
    for part in path.split("."):
        value = value.get(part) if isinstance(value, Mapping) else getattr(value, part, None)
        if value is None:
            return 50  # Missing optional diagnostics are neutral, not invented resources.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Physical score {path} must be numeric")
    return max(0, min(100, int(value)))


def score_weights(env, weights, inverse_fields=()):
    """Integer 0..100 physical preference; no sampling or state mutation."""
    total = sum(weights.values())
    if not total:
        return 0
    inverted = frozenset(inverse_fields)
    return sum((100 - _field(env, key) if key in inverted else _field(env, key)) * weight
               for key, weight in weights.items()) // total


@dataclass(frozen=True, slots=True)
class ResourceDefinition:
    kind: str
    purpose: str
    size: tuple[int, int]
    weights: Mapping[str, int]
    inverse_fields: tuple[str, ...]

    def score(self, env, weights=None):
        return score_weights(env, self.weights if weights is None else weights, self.inverse_fields)


@dataclass(frozen=True, slots=True)
class LayoutRecipe:
    id: str
    morphology: str
    required_resources: tuple[str, ...]
    resource_preferences: Mapping[str, int]
    culture_preferences: Mapping[str, int]
    environment_weights: Mapping[str, int]
    inverse_fields: tuple[str, ...]
    district_weights: Mapping[str, Mapping[str, int]]
    frontage_spacing: int
    offsets: tuple[tuple[int, int], ...]
    street_links: tuple[tuple[int, int], ...]
    rank_counts: Mapping[str, int]

    def street_offsets(self, rank):
        if not isinstance(rank, str) or rank not in self.rank_counts:
            raise ValueError(f"Unsupported settlement rank: {rank}")
        return self.offsets[:self.rank_counts[rank]]

    def preference_score(self, resources, culture_style, env):
        resources = _resources(resources)
        return (30 * sum(self.resource_preferences.get(kind, 0) for kind in resources)
                + 10 * self.culture_preferences.get(culture_style, 0)
                + score_weights(env, self.environment_weights, self.inverse_fields))


@dataclass(frozen=True, slots=True)
class LayoutCatalog:
    version: int
    resources: Mapping[str, ResourceDefinition]
    recipes: tuple[LayoutRecipe, ...]


def _resources(resources):
    if isinstance(resources, (str, bytes)):
        raise ValueError("Resources must be a collection of known resource kinds")
    try:
        values = tuple(resources)
    except TypeError as exc:
        raise ValueError("Resources must be a collection of known resource kinds") from exc
    if any(not isinstance(value, str) or value not in RESOURCE_KINDS for value in values):
        raise ValueError("Unknown settlement resource kind")
    if len(set(values)) != len(values):
        raise ValueError("Duplicate settlement resource kind")
    return tuple(sorted(values))


def validate_catalog(raw):
    """Reject malformed generation data before it can become saved geography."""
    if not isinstance(raw, dict) or set(raw) != {"version", "resource_definitions", "recipes"}:
        raise ValueError("Malformed layout catalog")
    if type(raw["version"]) is not int or raw["version"] != LAYOUT_VERSION:
        raise ValueError("Unsupported layout catalog version")
    resources = {}
    if not isinstance(raw["resource_definitions"], list):
        raise ValueError("Resource definitions must be a list")
    for row in raw["resource_definitions"]:
        if not isinstance(row, dict) or set(row) != {"kind", "purpose", "size", "weights", "inverse_fields"}:
            raise ValueError("Malformed resource definition")
        kind = row["kind"]
        if not isinstance(kind, str) or kind not in RESOURCE_KINDS or kind in resources:
            raise ValueError("Unknown or duplicate resource kind")
        if not isinstance(row["purpose"], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", row["purpose"]):
            raise ValueError("Malformed worksite purpose")
        if row["purpose"] != WORKSITE_PURPOSES[kind]:
            raise ValueError("Worksite purpose must reference the existing handler for its resource")
        if not isinstance(row["size"], list) or len(row["size"]) != 2:
            raise ValueError("Worksite size must contain width and height")
        size = tuple(_integer(n, 5, 25, "worksite size") for n in row["size"])
        weights = _weights(row["weights"])
        resources[kind] = ResourceDefinition(kind, row["purpose"], size, weights, _inverse_fields(row["inverse_fields"], weights))
    if set(resources) != RESOURCE_KINDS:
        raise ValueError("Every existing resource kind needs a definition")
    recipes, ids = [], set()
    if not isinstance(raw["recipes"], list) or not 1 <= len(raw["recipes"]) <= 64:
        raise ValueError("Layout catalog must contain 1..64 recipes")
    keys = {"id", "morphology", "required_resources", "resource_preferences", "culture_preferences",
            "environment_weights", "inverse_fields", "district_weights", "frontage_spacing",
            "street_offsets", "street_links", "rank_counts"}
    for row in raw["recipes"]:
        if not isinstance(row, dict) or set(row) != keys:
            raise ValueError("Malformed layout recipe")
        uid = row["id"]
        if not isinstance(uid, str) or not _ID.fullmatch(uid) or uid in ids:
            raise ValueError("Malformed or duplicate layout ID")
        ids.add(uid)
        if not isinstance(row["morphology"], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", row["morphology"]):
            raise ValueError("Malformed morphology identifier")
        if not isinstance(row["required_resources"], list):
            raise ValueError("Required resources must be a list")
        required = _resources(row["required_resources"])
        preferences = _weights(row["resource_preferences"], RESOURCE_KINDS)
        cultures = _weights(row["culture_preferences"], CULTURE_STYLES)
        environment = _weights(row["environment_weights"])
        inverse = _inverse_fields(row["inverse_fields"], environment)
        overrides = row["district_weights"]
        if not isinstance(overrides, dict) or any(kind not in resources for kind in overrides):
            raise ValueError("Unknown district resource kind")
        districts = MappingProxyType({kind: _weights(overrides.get(kind, dict(definition.weights)))
                                     for kind, definition in sorted(resources.items())})
        offsets = row["street_offsets"]
        if not isinstance(offsets, list) or not 6 <= len(offsets) <= 10:
            raise ValueError("Street offsets must contain 6..10 targets")
        points = []
        for point in offsets:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("Malformed street target")
            points.append(tuple(_integer(n, -100, 100, "street offset") for n in point))
        if len(set(points)) != len(points) or (0, 0) in points:
            raise ValueError("Duplicate or central street target")
        counts = row["rank_counts"]
        if not isinstance(counts, dict) or set(counts) != set(RANKS):
            raise ValueError("Unsupported or missing rank")
        counts = MappingProxyType({rank: _integer(counts[rank], 6, len(points), "rank target count") for rank in RANKS})
        links = row["street_links"]
        if not isinstance(links, list) or len(links) > 5:
            raise ValueError("At most five secondary street links are supported")
        edges = []
        for pair in links:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("Malformed street link")
            edge = tuple(_integer(n, 0, min(counts.values()) - 1, "street link index") for n in pair)
            if edge[0] == edge[1] or tuple(sorted(edge)) in {tuple(sorted(e)) for e in edges}:
                raise ValueError("Self or duplicate street link")
            edges.append(edge)
        recipes.append(LayoutRecipe(uid, row["morphology"], required, preferences, cultures, environment, inverse,
                                    districts, _integer(row["frontage_spacing"], 4, 7, "frontage spacing"),
                                    tuple(points), tuple(edges), counts))
    return LayoutCatalog(LAYOUT_VERSION, MappingProxyType(resources), tuple(sorted(recipes, key=lambda r: r.id)))


@lru_cache(maxsize=1)
def layout_catalog(version=LAYOUT_VERSION):
    if type(version) is not int or version != LAYOUT_VERSION:
        raise ValueError("Unsupported layout catalog version")
    path = Path(__file__).resolve().parents[1] / "data" / "settlement_layouts_v11.json"
    return validate_catalog(json.loads(path.read_text(encoding="utf-8")))


def resource_definition(kind):
    if not isinstance(kind, str) or kind not in RESOURCE_KINDS:
        raise ValueError("Unknown settlement resource kind")
    return layout_catalog().resources[kind]


def choose_layout(seed, settlement_id, resources, culture_style, env):
    resources = _resources(resources)
    if not isinstance(seed, bytes) or not isinstance(settlement_id, str) or not settlement_id:
        raise ValueError("A byte seed and stable settlement identity are required")
    if not isinstance(culture_style, str):
        raise ValueError("Culture style must be text")
    available = frozenset(resources)
    candidates = [recipe for recipe in layout_catalog().recipes if set(recipe.required_resources) <= available]
    if not candidates:
        raise ValueError("No eligible production layout")
    return max(candidates, key=lambda recipe: (
        recipe.preference_score(resources, culture_style, env),
        hash_u64(seed, LAYOUT_NAMESPACE, settlement_id, ",".join(resources), culture_style, recipe.id), recipe.id))
