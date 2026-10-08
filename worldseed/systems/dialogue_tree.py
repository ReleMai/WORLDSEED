"""Immutable authored conversation trees and declarative causal storylets.

This module never reads simulation state. Callers provide an observational fact
snapshot; missing facts fail closed, including inside comparisons and gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from worldseed.core.rng import hash_u64


LEGACY_TOPICS = frozenset({"root", "area", "personal", "relations", "knowledge"})
_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_FACT = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_:-]+)+$")
_OPS = frozenset({"eq", "ne", "gte", "lte", "gt", "lt", "in", "contains"})


@dataclass(frozen=True, slots=True)
class Predicate:
    kind: str
    fact: str = ""
    op: str = ""
    value: object = None
    children: tuple["Predicate", ...] = ()

    def matches(self, facts: Mapping[str, object]) -> bool:
        # Unknown is not false: negating an unknown observation must not grant
        # access to a branch. All/any retain their normal short-circuit logic.
        if self.kind == "not" and not self.children[0].known(facts):
            return False
        if self.kind == "all":
            return all(child.matches(facts) for child in self.children)
        if self.kind == "any":
            return any(child.matches(facts) for child in self.children)
        if self.kind == "not":
            return not self.children[0].matches(facts)
        if self.fact not in facts:
            return False
        actual = facts[self.fact]
        if actual is None or isinstance(actual, dict):
            return False
        if self.op in {"gt", "gte", "lt", "lte"}:
            if isinstance(actual, bool) or not isinstance(actual, (int, float)):
                return False
            if not math.isfinite(actual):
                return False
            if self.op == "gt":
                return actual > self.value
            if self.op == "gte":
                return actual >= self.value
            if self.op == "lt":
                return actual < self.value
            return actual <= self.value
        if self.op == "eq":
            return type(actual) is type(self.value) and actual == self.value or (
                not isinstance(actual, bool) and not isinstance(self.value, bool)
                and isinstance(actual, (int, float)) and isinstance(self.value, (int, float))
                and actual == self.value)
        if self.op == "ne":
            return not Predicate("comparison", self.fact, "eq", self.value).matches(facts)
        if self.op == "in":
            return any(Predicate("comparison", self.fact, "eq", value).matches(facts)
                       for value in self.value)
        if self.op == "contains":
            if isinstance(actual, str):
                return isinstance(self.value, str) and self.value in actual
            return isinstance(actual, (tuple, list, frozenset)) and self.value in actual
        return False

    def known(self, facts: Mapping[str, object]) -> bool:
        if self.kind == "comparison":
            actual=facts.get(self.fact)
            return isinstance(actual,(str,bool,int,float)) and (
                not isinstance(actual,float) or math.isfinite(actual))
        return all(child.known(facts) for child in self.children)


@dataclass(frozen=True, slots=True)
class TopicLink:
    phrase: str
    topic: str


@dataclass(frozen=True, slots=True)
class Storylet:
    uid: str
    priority: int
    requirements: Predicate
    paragraphs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TopicNode:
    uid: str
    parent: str
    label: str
    paragraphs: tuple[str, ...]
    links: tuple[TopicLink, ...]
    requirements: Predicate
    variants: tuple[Storylet, ...]
    content_id: str = ""


@dataclass(frozen=True, slots=True)
class DialogueTree:
    nodes: Mapping[str, TopicNode]

    def allows(self, topic: str, facts: Mapping[str, object]) -> bool:
        """Check every ancestor, so a forged deep topic cannot skip a gate."""
        while topic not in LEGACY_TOPICS:
            node = self.nodes.get(topic)
            if node is None or not node.requirements.matches(facts):
                return False
            topic = node.parent
        return True

    def paragraphs(self, topic: str, facts: Mapping[str, object], seed: bytes,
                   npc_uid: str, minute: int) -> tuple[str, ...]:
        node = self.nodes[topic]
        candidates = tuple(v for v in node.variants if v.requirements.matches(facts))
        if not candidates:
            return node.paragraphs
        # Causal applicability and priority precede seeded tie-breaking. JSON
        # order never affects the winner, and the same snapshot is identical.
        priority = max(v.priority for v in candidates)
        candidates = tuple(sorted((v for v in candidates if v.priority == priority),
                                  key=lambda v: v.uid))
        pick = hash_u64(seed, "dialogue.storylet", npc_uid, topic, int(minute)//180)
        return candidates[pick % len(candidates)].paragraphs


def _predicate(raw: object, depth: int = 0) -> Predicate:
    if raw is None:
        return Predicate("all")
    if not isinstance(raw, dict) or depth > 12:
        raise ValueError("Dialogue requirement must be an object of bounded depth")
    if len(raw) == 1 and next(iter(raw)) in {"all", "any", "not"}:
        kind, children = next(iter(raw.items()))
        if kind == "not":
            return Predicate(kind, children=(_predicate(children, depth+1),))
        if not isinstance(children, list) or not children or len(children) > 64:
            raise ValueError("Dialogue all/any requires a nonempty predicate list")
        return Predicate(kind, children=tuple(_predicate(c, depth+1) for c in children))
    if set(raw) != {"fact", "op", "value"}:
        raise ValueError("Dialogue comparison requires fact, op and value")
    fact, op, value = raw["fact"], raw["op"], raw["value"]
    if not isinstance(fact, str) or not _FACT.fullmatch(fact) or not isinstance(op,str) or op not in _OPS:
        raise ValueError("Invalid dialogue fact or comparison operator")
    scalar = lambda v: isinstance(v, (str, bool, int, float)) and (
        not isinstance(v, float) or math.isfinite(v))
    if op == "in":
        if not isinstance(value, list) or not value or not all(scalar(v) for v in value):
            raise ValueError("Dialogue in comparison requires scalar values")
        value = tuple(value)
    elif not scalar(value):
        raise ValueError("Dialogue comparison value must be a finite scalar")
    if op in {"gt", "gte", "lt", "lte"} and (
            isinstance(value, bool) or not isinstance(value, (int, float))):
        raise ValueError("Dialogue ordering comparison requires a number")
    return Predicate("comparison", fact, op, value)


def _paragraphs(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or len(raw) > 12:
        raise ValueError("Dialogue content requires a nonempty paragraph list")
    if any(not isinstance(p, str) or not p.strip() or len(p) > 12000 for p in raw):
        raise ValueError("Dialogue paragraphs must be nonempty bounded text")
    return tuple(raw)


def validate_dialogue_data(raw: object) -> DialogueTree:
    """Compile JSON into a frozen tree, rejecting IDs, cycles and bad types."""
    if not isinstance(raw, dict) or type(raw.get("version")) is not int or raw.get("version") != 1:
        raise ValueError("Unsupported dialogue data version")
    rows = raw.get("nodes")
    if not isinstance(rows, list) or not rows or len(rows) > 512:
        raise ValueError("Dialogue nodes must be a bounded nonempty list")
    nodes = {}
    content_ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Dialogue node must be an object")
        uid, parent, label = row.get("id"), row.get("parent"), row.get("label")
        content_id=row.get("content_id","")
        if not isinstance(content_id,str) or content_id and (not re.fullmatch(r"[a-z][a-z0-9_-]*:[a-z][a-z0-9_.-]*",content_id) or content_id in content_ids):
            raise ValueError("Invalid or duplicate namespaced dialogue content ID")
        if content_id:content_ids.add(content_id)
        if not isinstance(uid, str) or not _ID.fullmatch(uid) or uid in LEGACY_TOPICS or uid in nodes:
            raise ValueError(f"Invalid or duplicate dialogue ID: {uid!r}")
        if not isinstance(parent, str) or not _ID.fullmatch(parent):
            raise ValueError(f"Invalid dialogue parent for {uid}")
        if not isinstance(label, str) or not label.strip() or len(label) > 120:
            raise ValueError(f"Invalid dialogue label for {uid}")
        paragraphs = _paragraphs(row.get("paragraphs"))
        raw_links = row.get("links", [])
        if not isinstance(raw_links, list) or len(raw_links) > 64:
            raise ValueError("Dialogue links must be a bounded list")
        links = []
        for link in raw_links:
            if not isinstance(link, dict) or set(link) != {"phrase", "topic"}:
                raise ValueError("Dialogue link requires phrase and topic")
            phrase, target = link["phrase"], link["topic"]
            if not isinstance(phrase, str) or not phrase.strip() or phrase not in "\n\n".join(paragraphs):
                raise ValueError(f"Dialogue link phrase absent from {uid}")
            if not isinstance(target, str) or not _ID.fullmatch(target):
                raise ValueError("Invalid dialogue link target")
            if any(existing.phrase == phrase for existing in links):
                raise ValueError(f"Duplicate dialogue phrase in {uid}")
            links.append(TopicLink(phrase, target))
        variants = []
        raw_variants = row.get("variants", [])
        if not isinstance(raw_variants, list) or len(raw_variants) > 64:
            raise ValueError("Dialogue variants must be a bounded list")
        for variant in raw_variants:
            if not isinstance(variant, dict):
                raise ValueError("Dialogue variant must be an object")
            vid, priority = variant.get("id"), variant.get("priority", 0)
            if not isinstance(vid, str) or not _ID.fullmatch(vid) or any(v.uid == vid for v in variants):
                raise ValueError(f"Invalid/duplicate variant ID in {uid}")
            if isinstance(priority, bool) or not isinstance(priority, int) or abs(priority) > 10000:
                raise ValueError("Dialogue variant priority must be a bounded integer")
            variant_paragraphs=_paragraphs(variant.get("paragraphs"))
            if any(link.phrase not in "\n\n".join(variant_paragraphs) for link in links):
                raise ValueError(f"Dialogue variant {uid}:{vid} removes a linked phrase")
            variants.append(Storylet(vid, priority, _predicate(variant.get("requirements")),variant_paragraphs))
        nodes[uid] = TopicNode(uid, parent, label, paragraphs, tuple(links),
                              _predicate(row.get("requirements")), tuple(variants),content_id)
    for node in nodes.values():
        if node.parent not in nodes and node.parent not in LEGACY_TOPICS:
            raise ValueError(f"Missing dialogue parent: {node.parent}")
        for link in node.links:
            if link.topic not in nodes and link.topic not in LEGACY_TOPICS:
                raise ValueError(f"Missing dialogue target: {link.topic}")
        seen, cursor = set(), node.uid
        while cursor in nodes:
            if cursor in seen:
                raise ValueError(f"Dialogue parent cycle: {node.uid}")
            seen.add(cursor)
            cursor = nodes[cursor].parent
    return DialogueTree(MappingProxyType(nodes))


@lru_cache(maxsize=1)
def load_dialogue_tree() -> DialogueTree:
    path = Path(__file__).resolve().parents[1] / "data" / "dialogue_topics.json"
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return validate_dialogue_data(raw)
