"""Offline-first authoring requests for Scenario, Meshy and ElevenLabs.

Nothing in this module is imported by gameplay. Planning and doctor never use
the network; submit/status require --execute and credentials from the process
environment. Results remain in ignored scratch space pending human review.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
ENV = {
    "scenario": ("SCENARIO_API_KEY", "SCENARIO_API_SECRET"),
    "meshy": ("MESHY_API_KEY",),
    "elevenlabs": ("ELEVENLABS_API_KEY",),
}
SOURCES = {
    "scenario": "https://docs.scenario.com/get-started/generation/third-party-model-generation",
    "meshy": "https://docs.meshy.ai/en/api/text-to-3d",
    "elevenlabs": "https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert",
}
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}\Z")
ASPECTS = {"21:9", "16:9", "3:2", "4:3", "5:4", "1:1", "4:5", "3:4", "2:3", "9:16", "auto"}


def _text(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty text of at most {limit} characters")
    return value


def _number(value, name, low, high, *, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not low <= value <= high or not math.isfinite(value)
            or (integer and not isinstance(value, int))):
        raise ValueError(f"{name} must be {'an integer' if integer else 'a number'} from {low} to {high}")
    return value


def load_brief(path):
    with Path(path).open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("brief exceeds 64 KiB")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError):
        raise ValueError("brief must contain valid UTF-8 JSON") from None


def build_plan(brief):
    """Return a credential-free request, without reading environment or HTTP."""
    if not isinstance(brief, dict) or set(brief) - {"id", "provider", "prompt", "model", "settings", "license_note"}:
        raise ValueError("brief must be an object with supported fields only")
    asset_id = brief.get("id")
    if not isinstance(asset_id, str) or not ID.fullmatch(asset_id):
        raise ValueError("id must use 1-64 lowercase letters, digits, underscores or hyphens")
    provider = brief.get("provider")
    if not isinstance(provider, str) or provider not in ENV:
        raise ValueError("provider must be scenario, meshy or elevenlabs")
    prompt = _text(brief.get("prompt"), "prompt", 800 if provider == "meshy" else 10000)
    license_note = _text(brief.get("license_note"), "license_note", 1000)
    settings = brief.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    model = brief.get("model")
    body = {}
    if provider == "scenario":
        if not isinstance(model, str) or not TOKEN.fullmatch(model):
            raise ValueError("scenario requires a model identifier")
        if set(settings) - {"aspectRatio"}:
            raise ValueError("unsupported scenario setting; this adapter supports aspectRatio")
        aspect = settings.get("aspectRatio", "1:1")
        if not isinstance(aspect, str) or aspect not in ASPECTS:
            raise ValueError("unsupported aspectRatio")
        body = {"prompt": prompt, "aspectRatio": aspect}
        endpoint = f"https://api.cloud.scenario.com/v1/generate/custom/{model}"
    elif provider == "meshy":
        model = model or "meshy-7.1"
        if model not in ("meshy-7.1", "meshy-6", "meshy-6-lite"):
            raise ValueError("unsupported meshy model")
        if set(settings) - {"target_polycount"}:
            raise ValueError("unsupported meshy setting")
        body = {"mode": "preview", "prompt": prompt, "ai_model": model, "target_formats": ["glb"]}
        if "target_polycount" in settings:
            body["target_polycount"] = _number(settings["target_polycount"], "target_polycount", 100, 300000, integer=True)
            body["should_remesh"] = True
        endpoint = "https://api.meshy.ai/openapi/v2/text-to-3d"
    else:
        model = model or "eleven_text_to_sound_v2"
        if model not in ("eleven_text_to_sound_v2", "eleven_text_to_sound_v3"):
            raise ValueError("unsupported elevenlabs model")
        if set(settings) - {"duration_seconds", "prompt_influence", "loop"}:
            raise ValueError("unsupported elevenlabs setting")
        body = {"text": prompt, "model_id": model}
        for name, low, high in (("duration_seconds", 0.5, 30), ("prompt_influence", 0, 1)):
            if name in settings:
                body[name] = _number(settings[name], name, low, high)
        if "loop" in settings:
            if not isinstance(settings["loop"], bool):
                raise ValueError("loop must be boolean")
            body["loop"] = settings["loop"]
        endpoint = "https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128"
    plan = {"id": asset_id, "provider": provider, "model": model,
            "method": "POST", "endpoint": endpoint, "body": body,
            "required_environment": list(ENV[provider]), "license_note": license_note,
            "source": SOURCES[provider], "review_status": "unreviewed"}
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    plan["request_sha256"] = hashlib.sha256(canonical).hexdigest()
    return plan


def doctor():
    return {provider: {name: bool(os.environ.get(name, "").strip()) for name in names}
            for provider, names in ENV.items()}


def _credentials(provider):
    names = ENV[provider]
    values = [os.environ.get(name, "").strip() for name in names]
    if not all(values):
        raise ValueError("missing credentials; configure " + ", ".join(names))
    if any("\r" in value or "\n" in value for value in values):
        raise ValueError("credentials must not contain newlines")
    if provider == "scenario":
        combined = base64.b64encode(":".join(values).encode()).decode()
        return {"Authorization": "Basic " + combined}, values + [combined, ":".join(values)]
    if provider == "meshy":
        return {"Authorization": "Bearer " + values[0]}, values
    return {"xi-api-key": values[0]}, values


def _redact(value, secrets):
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {_redact(key, secrets): _redact(item, secrets) for key, item in value.items()}
    return value


def _stage(asset_id):
    if not isinstance(asset_id, str) or not ID.fullmatch(asset_id):
        raise ValueError("invalid staging id")
    target = ROOT / "scratch" / "external-tools" / asset_id
    if target.resolve() != target.absolute():
        raise ValueError("staging path must not contain symlinks")
    target.mkdir(parents=True, exist_ok=True)
    return target


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http(endpoint, method, headers, body, timeout, limit):
    payload = None if body is None else json.dumps(body).encode()
    req = request.Request(endpoint, data=payload, headers={"Content-Type": "application/json", **headers}, method=method)
    try:
        # Never follow an authenticated redirect or retry a billable POST.
        with request.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
            content = response.read(limit + 1)
            if len(content) > limit:
                raise ValueError("provider response exceeded the size limit")
            return content, response.headers.get_content_type()
    except error.HTTPError as exc:
        raise ValueError(f"provider HTTP {exc.code}; request was not retried") from None
    except (error.URLError, TimeoutError, OSError):
        raise ValueError("provider connection failed; request was not retried; check provider task history before resubmitting") from None


def _write_json(path, value, *, exclusive=False):
    if path.is_symlink():
        raise ValueError("record path must not be a symlink")
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def execute(plan, *, action="submit", task_id=None, timeout=60):
    _number(timeout, "timeout", 1, 120)
    provider = plan["provider"]
    headers, secrets = _credentials(provider)
    if "REPLACE" in plan["model"]:
        raise ValueError("replace the example model identifier before submitting")
    endpoint = plan["endpoint"]
    if action == "status":
        if provider == "elevenlabs":
            raise ValueError("elevenlabs returns audio directly; no asynchronous status endpoint")
        if not isinstance(task_id, str) or not TOKEN.fullmatch(task_id):
            raise ValueError("task-id must be a provider identifier")
        endpoint = ("https://api.cloud.scenario.com/v1/jobs/" if provider == "scenario"
                    else "https://api.meshy.ai/openapi/v2/text-to-3d/") + task_id
    elif action != "submit":
        raise ValueError("unsupported action")
    folder = _stage(plan["id"])
    if action == "submit":
        try:
            _write_json(folder / "request.json", _redact(plan, secrets), exclusive=True)
        except FileExistsError:
            raise ValueError("this id already has a submission record; check task history or use a new id") from None
    content, mime = _http(endpoint, "POST" if action == "submit" else "GET", headers,
                          plan["body"] if action == "submit" else None, timeout,
                          20 * 1024 * 1024 if provider == "elevenlabs" else 2 * 1024 * 1024)
    if provider == "elevenlabs":
        if not content or not (mime.startswith("audio/") or mime == "application/octet-stream"):
            raise ValueError("provider did not return audio")
        output = folder / "unreviewed.mp3"
        with output.open("xb") as stream:
            stream.write(content)
        result = {"status": "unreviewed", "file": output.name,
                  "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    else:
        try:
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise ValueError("provider returned invalid JSON; check task history before resubmitting") from None
        result = _redact(result, secrets)
    filename = "response.json" if action == "submit" else f"status-{task_id}.json"
    _write_json(folder / filename, result)
    job = result.get("job", {})
    job = job if isinstance(job, dict) else {}
    returned_id = job.get("jobId", result.get("result", task_id))
    if action == "submit" and provider != "elevenlabs" and (
            not isinstance(returned_id, str) or not TOKEN.fullmatch(returned_id)):
        raise ValueError("provider response has no valid task id; inspect the staged response and provider history before resubmitting")
    return _redact({"provider": provider, "id": plan["id"],
                    "task_id": returned_id,
                    "status": job.get("status", result.get("status", "submitted" if action == "submit" else "unknown")),
                    "record": str(folder / filename), "review_status": "unreviewed"}, secrets)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="report credential configuration booleans only")
    for name in ("plan", "submit", "status"):
        command = commands.add_parser(name)
        command.add_argument("--brief", type=Path, required=True)
        if name != "plan":
            command.add_argument("--execute", action="store_true", help="allow an authenticated provider request (submit can spend credits)")
            command.add_argument("--timeout", type=float, default=60)
        if name == "status":
            command.add_argument("--task-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
        else:
            plan = build_plan(load_brief(args.brief))
            if args.command == "plan":
                result = plan
            else:
                if not args.execute:
                    raise ValueError("network access requires --execute; run plan first")
                result = execute(plan, action=args.command,
                                 task_id=getattr(args, "task_id", None), timeout=args.timeout)
        secrets = [os.environ.get(name, "") for names in ENV.values() for name in names]
        print(json.dumps(_redact(result, [s for s in secrets if s]), indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError):
        # Messages from arbitrary files and providers must not echo credentials.
        exc = sys.exc_info()[1]
        if isinstance(exc, ValueError):
            secrets = [os.environ.get(name, "") for names in ENV.values() for name in names]
            print("error: " + _redact(str(exc), [s for s in secrets if s]), file=sys.stderr)
        else:
            print("error: cannot read brief or write staging files", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
