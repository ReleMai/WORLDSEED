from __future__ import annotations
import json, sqlite3, shutil, time, zlib
from pathlib import Path
from typing import Any
from worldseed.config import (
    ENGINE_VERSION, SAVE_SCHEMA_VERSION, WORLDGEN_VERSION, RESOURCEGEN_VERSION,
    HYDROLOGY_VERSION, SETTLEMENT_PLAN_VERSION, ROUTEGEN_VERSION,
)
from worldseed.core.coords import ChunkKey,WorldPos
from worldseed.persistence.validation import validate_sim_state

SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS world_meta(key TEXT PRIMARY KEY,value_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tile_deltas(x INTEGER NOT NULL,y INTEGER NOT NULL,z INTEGER NOT NULL,terrain_id TEXT NOT NULL,PRIMARY KEY(x,y,z));
CREATE TABLE IF NOT EXISTS entities(entity_id INTEGER PRIMARY KEY,archetype TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS components(entity_id INTEGER NOT NULL,kind TEXT NOT NULL,version INTEGER NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(entity_id,kind),FOREIGN KEY(entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS sim_state(slot INTEGER PRIMARY KEY CHECK(slot=1),payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS event_log(event_id TEXT PRIMARY KEY,minute INTEGER NOT NULL,event_type TEXT NOT NULL,payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_event_minute ON event_log(minute);
CREATE TABLE IF NOT EXISTS generated_chunks(
    chunk_x INTEGER NOT NULL, chunk_y INTEGER NOT NULL, z INTEGER NOT NULL,
    worldgen_version INTEGER NOT NULL, payload BLOB NOT NULL,
    PRIMARY KEY(chunk_x,chunk_y,z,worldgen_version)
);
CREATE TABLE IF NOT EXISTS generated_resource_chunks(
    chunk_x INTEGER NOT NULL, chunk_y INTEGER NOT NULL, z INTEGER NOT NULL,
    resourcegen_version INTEGER NOT NULL, season TEXT NOT NULL, payload BLOB NOT NULL,
    PRIMARY KEY(chunk_x,chunk_y,z,resourcegen_version,season)
);
CREATE TABLE IF NOT EXISTS generated_hydrology_domains(
    domain_x INTEGER NOT NULL, domain_y INTEGER NOT NULL, hydrology_version INTEGER NOT NULL,
    fingerprint TEXT NOT NULL, payload BLOB NOT NULL,
    PRIMARY KEY(domain_x,domain_y,hydrology_version)
);
CREATE TABLE IF NOT EXISTS generated_regional_plans(
    region_x INTEGER NOT NULL, region_y INTEGER NOT NULL, plan_version INTEGER NOT NULL,
    payload BLOB NOT NULL, PRIMARY KEY(region_x,region_y,plan_version)
);
CREATE TABLE IF NOT EXISTS generated_settlement_plans(
    settlement_uid TEXT NOT NULL, plan_version INTEGER NOT NULL,
    payload BLOB NOT NULL, PRIMARY KEY(settlement_uid,plan_version)
);
CREATE TABLE IF NOT EXISTS generated_route_plans(
    route_uid TEXT NOT NULL, routegen_version INTEGER NOT NULL,
    payload BLOB NOT NULL, PRIMARY KEY(route_uid,routegen_version)
);
CREATE TABLE IF NOT EXISTS physical_plan_deltas(
    object_uid TEXT PRIMARY KEY, plan_kind TEXT NOT NULL, revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
"""

class WorldDatabase:
    def __init__(self,path:Path,connection:sqlite3.Connection)->None:
        self.path=path;self.connection=connection;self.connection.row_factory=sqlite3.Row;self.connection.execute("PRAGMA foreign_keys=ON")
    @classmethod
    def create(cls,path:Path,world_name:str,world_seed_hex:str)->"WorldDatabase":
        path.parent.mkdir(parents=True,exist_ok=True);db=cls(path,sqlite3.connect(path));db.connection.executescript(SCHEMA)
        now=time.time();db.set_meta("save_schema",SAVE_SCHEMA_VERSION);db.set_meta("engine_version",ENGINE_VERSION);db.set_meta("worldgen_version",WORLDGEN_VERSION);db.set_meta("resourcegen_version",RESOURCEGEN_VERSION);db.set_meta("hydrology_version",HYDROLOGY_VERSION);db.set_meta("settlement_plan_version",SETTLEMENT_PLAN_VERSION);db.set_meta("routegen_version",ROUTEGEN_VERSION);db.set_meta("world_name",world_name);db.set_meta("world_seed",world_seed_hex);db.set_meta("turn",0);db.set_meta("created_at",now);db.set_meta("last_saved_at",now);db.connection.commit();return db
    @classmethod
    def open(cls,path:Path)->"WorldDatabase":
        db=cls(path,sqlite3.connect(path));db.connection.executescript(SCHEMA)
        try:schema=int(db.get_meta("save_schema"))
        except KeyError:raise RuntimeError("Not a WORLDSEED save")
        if schema>SAVE_SCHEMA_VERSION:raise RuntimeError(f"Save schema {schema} is newer than engine {SAVE_SCHEMA_VERSION}")
        if schema<SAVE_SCHEMA_VERSION:db._migrate(schema)
        db._ensure_rc14_generation_meta()
        return db
    def _migrate(self,old:int)->None:
        # Additive schema migrations. v1 introduced generic simulation state/event logs; v3 formalizes the living-world RC metadata boundary while retaining canonical JSON state compatibility.
        with self.connection:
            self.connection.executescript(SCHEMA);self.set_meta("save_schema",SAVE_SCHEMA_VERSION);self.set_meta("engine_version",ENGINE_VERSION)

    def _ensure_rc14_generation_meta(self)->None:
        """Add RC14 generator-contract metadata without rewriting legacy geography."""
        defaults={
            "hydrology_version":HYDROLOGY_VERSION,
            "settlement_plan_version":SETTLEMENT_PLAN_VERSION,
            "routegen_version":ROUTEGEN_VERSION,
        }
        changed=False
        for key,value in defaults.items():
            try:self.get_meta(key)
            except KeyError:self.set_meta(key,value);changed=True
        if changed:self.connection.commit()
    def backup(self,max_backups:int=3)->Path:
        """Create a consistent rotating SQLite backup before a checkpoint."""
        self.connection.commit()
        backup_dir=self.path.parent / "backups"
        backup_dir.mkdir(parents=True,exist_ok=True)
        base=self.path.stem
        # Rotate oldest generation upward. .bak1 is the newest prior checkpoint.
        for i in range(max_backups,1,-1):
            older=backup_dir/f"{base}.bak{i-1}.db";newer=backup_dir/f"{base}.bak{i}.db"
            if older.exists():shutil.copy2(older,newer)
        target=backup_dir/f"{base}.bak1.db"
        dest=sqlite3.connect(target)
        try:self.connection.backup(dest)
        finally:dest.close()
        return target

    @classmethod
    def restore_backup(cls,backup_path:Path,target_path:Path)->None:
        """Restore a backup only after it independently passes SQLite integrity."""
        probe=sqlite3.connect(backup_path)
        try:
            row=probe.execute("PRAGMA integrity_check").fetchone()
            if not row or row[0]!="ok":raise RuntimeError(f"Backup failed integrity check: {row[0] if row else 'unknown'}")
        finally:probe.close()
        shutil.copy2(backup_path,target_path)

    def close(self)->None:self.connection.close()
    def set_meta(self,key:str,value:Any)->None:
        text=json.dumps(value,separators=(",",":"),sort_keys=True);self.connection.execute("INSERT INTO world_meta(key,value_json) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",(key,text))
    def get_meta(self,key:str)->Any:
        row=self.connection.execute("SELECT value_json FROM world_meta WHERE key=?",(key,)).fetchone()
        if row is None:raise KeyError(key)
        return json.loads(row[0])
    @staticmethod
    def _pack_generated(values:list[str|None]|tuple[str|None,...])->bytes:
        raw=json.dumps(list(values),separators=(",",":"),ensure_ascii=False).encode("utf-8")
        return zlib.compress(raw,6)
    @staticmethod
    def _unpack_generated(payload:bytes)->tuple[str|None,...]:
        raw=zlib.decompress(payload).decode("utf-8")
        values=json.loads(raw)
        return tuple(None if v is None else str(v) for v in values)
    def load_generated_chunk(self,key:ChunkKey,worldgen_version:int)->tuple[str|None,...]|None:
        row=self.connection.execute(
            "SELECT payload FROM generated_chunks WHERE chunk_x=? AND chunk_y=? AND z=? AND worldgen_version=?",
            (key.x,key.y,key.z,int(worldgen_version))
        ).fetchone()
        if row is None:return None
        try:return self._unpack_generated(bytes(row[0]))
        except Exception:return None
    def store_generated_chunk(self,key:ChunkKey,worldgen_version:int,terrain_ids:list[str]|tuple[str,...])->None:
        payload=self._pack_generated(tuple(terrain_ids))
        self.connection.execute(
            "INSERT INTO generated_chunks(chunk_x,chunk_y,z,worldgen_version,payload) VALUES(?,?,?,?,?) "
            "ON CONFLICT(chunk_x,chunk_y,z,worldgen_version) DO UPDATE SET payload=excluded.payload",
            (key.x,key.y,key.z,int(worldgen_version),sqlite3.Binary(payload))
        )
    def load_generated_resource_chunk(self,key:ChunkKey,resourcegen_version:int,season:str)->tuple[str|None,...]|None:
        row=self.connection.execute(
            "SELECT payload FROM generated_resource_chunks WHERE chunk_x=? AND chunk_y=? AND z=? AND resourcegen_version=? AND season=?",
            (key.x,key.y,key.z,int(resourcegen_version),str(season))
        ).fetchone()
        if row is None:return None
        try:return self._unpack_generated(bytes(row[0]))
        except Exception:return None
    def store_generated_resource_chunk(self,key:ChunkKey,resourcegen_version:int,season:str,features:list[str|None]|tuple[str|None,...])->None:
        payload=self._pack_generated(tuple(features))
        self.connection.execute(
            "INSERT INTO generated_resource_chunks(chunk_x,chunk_y,z,resourcegen_version,season,payload) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(chunk_x,chunk_y,z,resourcegen_version,season) DO UPDATE SET payload=excluded.payload",
            (key.x,key.y,key.z,int(resourcegen_version),str(season),sqlite3.Binary(payload))
        )
    @staticmethod
    def _pack_generated_json(value:Any)->bytes:
        raw=json.dumps(value,separators=(",",":"),sort_keys=True,ensure_ascii=False).encode("utf-8")
        return zlib.compress(raw,6)
    @staticmethod
    def _unpack_generated_json(payload:bytes)->Any:
        return json.loads(zlib.decompress(payload).decode("utf-8"))
    def load_generated_hydrology_domain(self,domain_x:int,domain_y:int,hydrology_version:int)->dict[str,Any]|None:
        row=self.connection.execute(
            "SELECT fingerprint,payload FROM generated_hydrology_domains WHERE domain_x=? AND domain_y=? AND hydrology_version=?",
            (int(domain_x),int(domain_y),int(hydrology_version))
        ).fetchone()
        if row is None:return None
        try:
            value=self._unpack_generated_json(bytes(row["payload"]))
            if not isinstance(value,dict) or str(value.get("fingerprint",""))!=str(row["fingerprint"]):return None
            return value
        except Exception:return None
    def store_generated_hydrology_domain(self,domain_x:int,domain_y:int,hydrology_version:int,payload:dict[str,Any],fingerprint:str)->None:
        packed=self._pack_generated_json(payload)
        self.connection.execute(
            "INSERT INTO generated_hydrology_domains(domain_x,domain_y,hydrology_version,fingerprint,payload) VALUES(?,?,?,?,?) "
            "ON CONFLICT(domain_x,domain_y,hydrology_version) DO UPDATE SET fingerprint=excluded.fingerprint,payload=excluded.payload",
            (int(domain_x),int(domain_y),int(hydrology_version),str(fingerprint),sqlite3.Binary(packed))
        )
    def load_generated_regional_plan(self,region_x:int,region_y:int,plan_version:int)->dict[str,Any]|None:
        row=self.connection.execute("SELECT payload FROM generated_regional_plans WHERE region_x=? AND region_y=? AND plan_version=?",(int(region_x),int(region_y),int(plan_version))).fetchone()
        if row is None:return None
        try:
            value=self._unpack_generated_json(bytes(row[0]));return value if isinstance(value,dict) else None
        except Exception:return None
    def store_generated_regional_plan(self,region_x:int,region_y:int,plan_version:int,payload:dict[str,Any])->None:
        self.connection.execute(
            "INSERT INTO generated_regional_plans(region_x,region_y,plan_version,payload) VALUES(?,?,?,?) "
            "ON CONFLICT(region_x,region_y,plan_version) DO UPDATE SET payload=excluded.payload",
            (int(region_x),int(region_y),int(plan_version),sqlite3.Binary(self._pack_generated_json(payload)))
        )
    def load_generated_settlement_plan(self,settlement_uid:str,plan_version:int)->dict[str,Any]|None:
        row=self.connection.execute("SELECT payload FROM generated_settlement_plans WHERE settlement_uid=? AND plan_version=?",(str(settlement_uid),int(plan_version))).fetchone()
        if row is None:return None
        try:
            value=self._unpack_generated_json(bytes(row[0]));return value if isinstance(value,dict) else None
        except Exception:return None
    def store_generated_settlement_plan(self,settlement_uid:str,plan_version:int,payload:dict[str,Any])->None:
        self.connection.execute(
            "INSERT INTO generated_settlement_plans(settlement_uid,plan_version,payload) VALUES(?,?,?) "
            "ON CONFLICT(settlement_uid,plan_version) DO UPDATE SET payload=excluded.payload",
            (str(settlement_uid),int(plan_version),sqlite3.Binary(self._pack_generated_json(payload)))
        )
    def load_generated_route_plan(self,route_uid:str,routegen_version:int)->dict[str,Any]|None:
        row=self.connection.execute("SELECT payload FROM generated_route_plans WHERE route_uid=? AND routegen_version=?",(str(route_uid),int(routegen_version))).fetchone()
        if row is None:return None
        try:
            value=self._unpack_generated_json(bytes(row[0]));return value if isinstance(value,dict) else None
        except Exception:return None
    def store_generated_route_plan(self,route_uid:str,routegen_version:int,payload:dict[str,Any])->None:
        self.connection.execute(
            "INSERT INTO generated_route_plans(route_uid,routegen_version,payload) VALUES(?,?,?) "
            "ON CONFLICT(route_uid,routegen_version) DO UPDATE SET payload=excluded.payload",
            (str(route_uid),int(routegen_version),sqlite3.Binary(self._pack_generated_json(payload)))
        )
    def load_physical_plan_delta(self,object_uid:str)->dict[str,Any]|None:
        row=self.connection.execute("SELECT plan_kind,revision,payload_json FROM physical_plan_deltas WHERE object_uid=?",(str(object_uid),)).fetchone()
        if row is None:return None
        try:return {"object_uid":str(object_uid),"plan_kind":str(row["plan_kind"]),"revision":int(row["revision"]),"payload":json.loads(row["payload_json"])}
        except Exception:return None
    def store_physical_plan_delta(self,object_uid:str,plan_kind:str,revision:int,payload:dict[str,Any])->None:
        text=json.dumps(payload,separators=(",",":"),sort_keys=True)
        self.connection.execute(
            "INSERT INTO physical_plan_deltas(object_uid,plan_kind,revision,payload_json) VALUES(?,?,?,?) "
            "ON CONFLICT(object_uid) DO UPDATE SET plan_kind=excluded.plan_kind,revision=excluded.revision,payload_json=excluded.payload_json",
            (str(object_uid),str(plan_kind),int(revision),text)
        )
    def commit_generated(self)->None:self.connection.commit()
    def load_chunk_deltas(self,key:ChunkKey)->dict[tuple[int,int],str]:
        from worldseed.config import CHUNK_SIZE
        x0=key.x*CHUNK_SIZE;y0=key.y*CHUNK_SIZE
        rows=self.connection.execute("SELECT x,y,terrain_id FROM tile_deltas WHERE z=? AND x>=? AND x<? AND y>=? AND y<?",(key.z,x0,x0+CHUNK_SIZE,y0,y0+CHUNK_SIZE)).fetchall()
        return {(int(r["x"])-x0,int(r["y"])-y0):str(r["terrain_id"]) for r in rows}
    def load_component(self,entity_id:int,kind:str)->dict[str,Any]|None:
        row=self.connection.execute("SELECT payload_json FROM components WHERE entity_id=? AND kind=?",(entity_id,kind)).fetchone();return None if row is None else json.loads(row[0])
    def load_sim_state(self)->dict|None:
        row=self.connection.execute("SELECT payload_json FROM sim_state WHERE slot=1").fetchone();return None if row is None else json.loads(row[0])
    def save_state(self,*,turn:int,tile_deltas:dict[WorldPos,str],player_id:int,position:WorldPos,inventory:dict[str,int],vitals:dict|None=None,sim_state:dict|None=None)->None:
        with self.connection:
            self.set_meta("turn",turn);self.set_meta("engine_version",ENGINE_VERSION)
            self.connection.execute("INSERT INTO entities(entity_id,archetype) VALUES(?,?) ON CONFLICT(entity_id) DO UPDATE SET archetype=excluded.archetype",(player_id,"core:player"))
            self._save_component(player_id,"Position",1,{"x":position.x,"y":position.y,"z":position.z});self._save_component(player_id,"Inventory",2,{"items":inventory})
            if vitals is not None:self._save_component(player_id,"Vitals",1,vitals)
            for pos,tid in tile_deltas.items():self.connection.execute("INSERT INTO tile_deltas(x,y,z,terrain_id) VALUES(?,?,?,?) ON CONFLICT(x,y,z) DO UPDATE SET terrain_id=excluded.terrain_id",(pos.x,pos.y,pos.z,tid))
            if sim_state is not None:
                text=json.dumps(sim_state,separators=(",",":"),sort_keys=True);self.connection.execute("INSERT INTO sim_state(slot,payload_json) VALUES(1,?) ON CONFLICT(slot) DO UPDATE SET payload_json=excluded.payload_json",(text,))
                for e in sim_state.get("history",[])[-250:]:
                    self.connection.execute("INSERT OR IGNORE INTO event_log(event_id,minute,event_type,payload_json) VALUES(?,?,?,?)",(e.get("uid"),int(e.get("minute",0)),e.get("event_type","unknown"),json.dumps(e,separators=(",",":"),sort_keys=True)))
    def _save_component(self,entity_id:int,kind:str,version:int,payload:dict[str,Any])->None:
        text=json.dumps(payload,separators=(",",":"),sort_keys=True);self.connection.execute("INSERT INTO components(entity_id,kind,version,payload_json) VALUES(?,?,?,?) ON CONFLICT(entity_id,kind) DO UPDATE SET version=excluded.version,payload_json=excluded.payload_json",(entity_id,kind,version,text))
    def verify(self)->list[str]:
        issues=[];row=self.connection.execute("PRAGMA integrity_check").fetchone()
        if row and row[0]!="ok":issues.append(str(row[0]))
        issues.extend(f"foreign_key_check: {tuple(r)}" for r in self.connection.execute("PRAGMA foreign_key_check").fetchall())
        try:
            state=self.load_sim_state()
            if state:issues.extend(validate_sim_state(state))
        except Exception as exc:issues.append(f"sim_state parse error: {exc}")
        return issues
