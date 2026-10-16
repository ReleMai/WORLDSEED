"""Render-only fade from currently seen interior furniture to last-seen memory.

Never interpolate hidden live state or NPCs. Only immutable observed furniture
already admitted by authoritative memory clips may participate.
"""
from __future__ import annotations
from dataclasses import replace

DURATION_SECONDS = .7
MEMORY_OPACITY = .62
MAX_FADES = 128
PREFIX = "interior-memory-object:"


def update_departures(previous, current, starts, now):
    """Bound transition lifecycle by plan ID and identical observed art."""
    if current is None:
        return {}
    old = {} if previous is None or previous.space_id != current.space_id else {
        row.uid:(row.kind,row.content_id,row.bounds)
        for row in previous.objects if row.kind in ("furniture","stairs","exit","pile")}
    allowed = {row.uid:(row.kind,row.content_id,row.bounds)
               for row in current.memory_objects
               if row.kind in ("furniture","stairs","exit","pile")}
    valid={uid:started for uid,started in starts.items()
           if uid in allowed and 0<=now-started<DURATION_SECONDS}
    for uid,signature in allowed.items():
        if uid in old and old[uid]==signature and uid not in valid:
            valid[uid]=now
    return dict(sorted(valid.items(),key=lambda pair:(pair[1],pair[0]))[-MAX_FADES:])


def fading(starts, now):
    return any(0<=now-started<DURATION_SECONDS for started in starts.values())


def faded_opacity(start, now):
    fraction=max(0.,min(1.,(now-start)/DURATION_SECONDS))
    smooth=fraction*fraction*(3.-2.*fraction)
    return 1.-(1.-MEMORY_OPACITY)*smooth


def fade_commands(commands, starts, now):
    """Change only the draw opacity; clip masks and memory classification stay."""
    if not starts:
        return commands
    result=[]
    for command in commands:
        uid=command.visual_id[len(PREFIX):] if command.visual_id.startswith(PREFIX) else None
        if uid is not None and command.remembered and uid in starts:
            result.append(replace(command,opacity=faded_opacity(starts[uid],now)))
        else:
            result.append(command)
    return tuple(result)
