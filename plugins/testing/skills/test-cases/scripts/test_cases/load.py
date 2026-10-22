import datetime
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]


class LoadError(Exception):
    pass


# -rdate is required: Ruby 2.6 YAML.safe_load dies with "uninitialized constant Date" without it.
RUBY_SCRIPT = (
    'def n(o) case o when Hash then o.each_with_object({}) { |(k, v), h| h[n(k).is_a?(String) ? n(k) : (k.nil? ? "null" : n(k).to_s)] = n(v) } '
    'when Array then o.map { |v| n(v) } '
    'when Time then t = o.utc; t.strftime("%Y-%m-%dT%H:%M:%S") + (t.usec > 0 ? format(".%06d", t.usec) : "") + "Z" '
    "when Date then o.iso8601 when Symbol then \":\" + o.to_s else o end end; "
    "puts JSON.generate(n(YAML.safe_load(File.read(ARGV[0]), permitted_classes: [Date, Time, Symbol], aliases: true)))"
)

NO_BACKEND = "no YAML backend: pip install pyyaml, or install ruby"


def _pyyaml():
    try:
        import yaml
    except ImportError:
        return None
    return yaml


def _ruby_exe():
    return shutil.which("ruby")


def _canon_datetime(dt):
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    out = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if dt.microsecond:
        out += f".{dt.microsecond:06d}"
    return out + "Z"


def _norm_key(k):
    if isinstance(k, str):
        return k
    if isinstance(k, bool):
        return "true" if k else "false"
    if k is None:
        return "null"
    if isinstance(k, datetime.datetime):
        return _canon_datetime(k)
    if isinstance(k, datetime.date):
        return k.isoformat()
    return str(k)


def _normalize(o):
    if isinstance(o, dict):
        return {_norm_key(k): _normalize(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_normalize(v) for v in o]
    if isinstance(o, datetime.datetime):
        return _canon_datetime(o)
    if isinstance(o, datetime.date):
        return o.isoformat()
    return o


def _load_pyyaml(yaml, text, path):
    try:
        return yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    except yaml.YAMLError as e:
        raise LoadError(f"{path}: YAML parse failed: {e}") from e


def _load_ruby(ruby, path):
    try:
        r = subprocess.run(
            [ruby, "-rdate", "-ryaml", "-rjson", "-e", RUBY_SCRIPT, path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as e:
        raise LoadError(f"{path}: ruby YAML parse timed out") from e
    if r.returncode != 0:
        raise LoadError(f"{path}: ruby YAML parse failed: {r.stderr.strip()}")
    return json.loads(r.stdout)


def _parse_yaml(path):
    backend = os.environ.get("TEST_CASES_YAML_BACKEND", "auto")
    if backend not in ("auto", "pyyaml", "ruby"):
        raise LoadError(f"TEST_CASES_YAML_BACKEND: unknown backend {backend!r}")
    yaml = _pyyaml() if backend in ("auto", "pyyaml") else None
    if yaml is not None:
        return _load_pyyaml(yaml, Path(path).read_text(encoding="utf-8"), path)
    ruby = _ruby_exe() if backend in ("auto", "ruby") else None
    if ruby is None:
        raise LoadError(NO_BACKEND)
    return _load_ruby(ruby, str(path))


def load_doc(path):
    p = Path(path)
    if not p.is_file():
        raise LoadError(f"{path}: not found")
    if p.suffix == ".json":
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise LoadError(f"{path}: JSON parse failed: {e}") from e
    else:
        doc = _parse_yaml(path)
    doc = _normalize(doc)
    if not isinstance(doc, dict):
        raise LoadError(f"{path}: top-level is not a mapping")
    return doc


def load_profile(path):
    return None if path is None else load_doc(path)


def load_schema(name):
    p = SKILL_DIR / "schemas" / f"{name}.schema.json"
    if not p.is_file():
        raise LoadError(f"{p}: not found")
    return json.loads(p.read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
