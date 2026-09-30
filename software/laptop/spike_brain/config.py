"""Settings, personas and secrets.

Layers, later wins:
  1. spike_brain/config/default.toml       (shipped defaults, documented)
  2. software/laptop/spike_settings.toml   (the owner's overrides, optional)
  3. command-line flags (applied by app.py)
Secrets never live in TOML: they come from software/laptop/.env (git-ignored)
or real environment variables.
"""
from __future__ import annotations

import copy
import os
import random
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
LAPTOP_DIR = PACKAGE_DIR.parent                     # software/laptop
CONFIG_DIR = PACKAGE_DIR / "config"
DEFAULT_TOML = CONFIG_DIR / "default.toml"
USER_TOML = LAPTOP_DIR / "spike_settings.toml"
ENV_FILE = LAPTOP_DIR / ".env"


class ConfigError(Exception):
    """A setting is missing or has a bad value."""


def read_toml(path: Path) -> dict:
    """The owner's own TOML file. Tolerates the byte-order mark Notepad and PowerShell write, and
    turns a syntax mistake into a ConfigError that names the file (logged, not a silent crash)."""
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.name} has a mistake: {e}") from e
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"cannot read {path}: {e}") from e


def deep_merge(base: dict, override: dict) -> dict:
    """Return base with override merged in (dicts recursively, others replaced)."""
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class Section:
    """Read-only attribute view over a dict of settings (nested dicts become Sections)."""

    def __init__(self, data: dict, path: str = ""):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if name not in data:
            raise ConfigError(f"missing setting '{self._path + name}'")
        v = data[name]
        return Section(v, f"{self._path}{name}.") if isinstance(v, dict) else v

    def __setattr__(self, name, value):
        raise AttributeError("settings are read-only; use Settings.override()")

    def get(self, name: str, default: Any = None) -> Any:
        v = self._data.get(name, default)
        return Section(v, f"{self._path}{name}.") if isinstance(v, dict) else v

    def to_dict(self) -> dict:
        return copy.deepcopy(self._data)

    def __contains__(self, name: str) -> bool:
        return name in self._data

    def __repr__(self) -> str:
        return f"Section({self._path or 'root'})"


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse a KEY=VALUE .env file (comments, blank lines and quotes allowed).

    Real environment variables win over the file, so a key can be supplied
    either way. Never logs values."""
    values: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
                val = val[1:-1]
            values[key] = val
    for key in list(values):
        if key in os.environ:
            values[key] = os.environ[key]
    for key in ("SPIKE_TOKEN", "GEMINI_API_KEY"):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


@dataclass
class Persona:
    """One character (Spike the dog, Spicy the cat). Loaded from config/personas/*.toml."""

    id: str
    mode: str
    name: str
    wake_words: list[str]
    wake_aliases: dict[str, list[str]]
    voice_file: Path | None
    pitch: float
    speed: float
    noise_scale: float
    noise_w: float
    wake_sound: str
    listen_mood: str
    system_prompt: str
    lines: dict[str, list[str]] = field(default_factory=dict)
    vocative_only: list[str] = field(default_factory=list)
    voice_cfg: dict = field(default_factory=dict)      # the persona's whole [voice] table (speech/voices.py)

    def line(self, key: str, rng: random.Random | None = None, **fmt: Any) -> str:
        """A random scripted line for `key` (falls back to 'fallback'), formatted."""
        options = self.lines.get(key) or self.lines.get("fallback") or ["[mood:neutral] ..."]
        return Persona.format_line(self, (rng or random).choice(options), **fmt)

    def pick(self, key: str, rng: random.Random | None = None, **fmt: Any) -> tuple[str, str]:
        """(line id, formatted line). The id, e.g. "alarm.2", names the scripted line for the
        owner's own recordings (voice_recordings/<persona>/<id>.wav)."""
        options = self.lines.get(key)
        if not options:
            key, options = "fallback", self.lines.get("fallback") or ["[mood:neutral] ..."]
        idx = (rng or random).randrange(len(options))
        return f"{key}.{idx}", self.format_line(options[idx], **fmt)

    def format_line(self, text: str, **fmt: Any) -> str:
        """Fill {owner}, {when}... in one raw scripted line (no name known: "Good evening.")."""
        if fmt.get("owner") in (None, "", "you"):
            # no name known yet: "Good evening, {owner}." -> "Good evening." (not "Good evening, you.")
            text = re.sub(r"\s*,?\s*\{owner\}(?=[.!?,])", "", text)
            text = re.sub(r"\]\s*[.,](?!\.)\s*", "] ", text).replace("{owner}", "you")   # keep "...Fine"
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text

    def has_line(self, key: str) -> bool:
        return bool(self.lines.get(key))


def resolve_voice(voice_dir: Path, file: str) -> Path | None:
    """The configured voice file, or the first .onnx alphabetically."""
    if file:
        p = Path(file)
        p = p if p.is_absolute() else voice_dir / p
        return p if p.exists() else None
    candidates = sorted(voice_dir.glob("*.onnx")) if voice_dir.exists() else []
    return candidates[0] if candidates else None


def load_persona(persona_id: str, root: Path = LAPTOP_DIR) -> Persona:
    path = CONFIG_DIR / "personas" / f"{persona_id}.toml"
    if not path.exists():
        raise ConfigError(f"persona file not found: {path}")
    with path.open("rb") as f:
        d = tomllib.load(f)
    try:
        voice = d.get("voice", {})
        voice_dir = Path(voice.get("voice_dir", f"models/piper/{persona_id}"))
        voice_dir = voice_dir if voice_dir.is_absolute() else root / voice_dir
        aliases = {k: [a.lower() for a in v] for k, v in d.get("wake_aliases", {}).items()}
        for w in d["wake_words"]:
            aliases.setdefault(w, [])
            if w.lower() not in aliases[w]:
                aliases[w].insert(0, w.lower())
        return Persona(
            id=d["id"], mode=d["mode"], name=d["name"],
            wake_words=list(d["wake_words"]), wake_aliases=aliases,
            voice_file=resolve_voice(voice_dir, voice.get("file", "")),
            pitch=float(voice.get("pitch", 1.0)), speed=float(voice.get("speed", 1.0)),
            noise_scale=float(voice.get("noise_scale", 0.667)), noise_w=float(voice.get("noise_w", 0.8)),
            wake_sound=voice.get("wake_sound", "yip"), listen_mood=voice.get("listen_mood", "curious"),
            system_prompt=d["prompt"]["system"].strip(),
            lines={k: list(v) for k, v in d.get("lines", {}).items()},
            vocative_only=[str(v).lower() for v in d.get("vocative_only", [])],
            voice_cfg=dict(voice),
        )
    except KeyError as e:
        raise ConfigError(f"persona {persona_id}: missing {e}") from e


def add_personal_wake_words(persona: Persona, table: dict) -> None:
    """Merge the owner's PERSONAL extra wake words (his own laptop only) into a persona.

    The file ([wake] personal_file, default data/personal_wake_words.toml) lives in the
    git-ignored data/ folder and is never shipped. One table per mode:

        [dog]
        wake_words = ["Rex"]                  # extra names he answers to
        vocative_only = []                    # aliases that are everyday words
        [dog.wake_aliases]
        "Rex" = ["rex", "hey rex", "wrecks"]  # how Vosk/Whisper may hear it
    """
    extra_words = [str(w) for w in table.get("wake_words", []) if str(w).strip()]
    aliases = {str(k): [str(a).lower() for a in v] for k, v in table.get("wake_aliases", {}).items()}
    for w in extra_words:
        if w not in persona.wake_words:
            persona.wake_words.append(w)
        aliases.setdefault(w, [])
    for canonical, extra in aliases.items():
        have = persona.wake_aliases.setdefault(canonical, [])
        for a in [canonical.lower(), *extra]:
            if a not in have:
                have.append(a)
    for v in table.get("vocative_only", []):
        v = str(v).lower()
        if v not in persona.vocative_only:
            persona.vocative_only.append(v)


class Settings:
    """All settings plus secrets and both personas."""

    def __init__(self, data: dict, env: dict[str, str], root: Path = LAPTOP_DIR, models_root: Path | None = None):
        self._data = data
        self.env = env
        self.root = root
        self.models_root = models_root      # desktop app: the models ship read-only beside the brain
        self.cfg = Section(data)
        self.personas = {
            "dog": load_persona(data["persona"]["dog"], root),
            "cat": load_persona(data["persona"]["cat"], root),
        }
        personal = str(data.get("wake", {}).get("personal_file", "") or "")
        if personal and self.path(personal).exists():
            table = read_toml(self.path(personal))
            for mode, persona in self.personas.items():
                if isinstance(table.get(mode), dict):
                    add_personal_wake_words(persona, table[mode])

    @classmethod
    def load(cls, user_toml: Path | None = USER_TOML, env_file: Path = ENV_FILE,
             overrides: dict | None = None, root: Path = LAPTOP_DIR, profile: str | None = None,
             models_root: Path | None = None) -> "Settings":
        """profile: an extra shipped layer between the defaults and the owner's file, e.g.
        "desktop" = config/desktop.toml (the Windows app's light brain). root: where data/ and the
        owner's files live (the desktop app passes its own app-data folder); models_root: where
        "models/..." paths point instead of root/models (the desktop package's read-only models)."""
        with DEFAULT_TOML.open("rb") as f:
            data = tomllib.load(f)
        if profile:
            prof = CONFIG_DIR / f"{profile}.toml"
            if not re.fullmatch(r"[a-z0-9_]+", profile) or not prof.exists():
                raise ConfigError(f"unknown settings profile '{profile}'")
            with prof.open("rb") as f:
                data = deep_merge(data, tomllib.load(f))
        if user_toml is not None and Path(user_toml).exists():
            data = deep_merge(data, read_toml(Path(user_toml)))
        if overrides:
            data = deep_merge(data, overrides)
        return cls(data, load_env(env_file), root, models_root)

    def override(self, overrides: dict) -> "Settings":
        return Settings(deep_merge(self._data, overrides), self.env, self.root, self.models_root)

    def path(self, rel: str) -> Path:
        """A config path, made absolute relative to software/laptop (or the desktop app's data
        folder); "models/..." goes to models_root when one is set."""
        p = Path(rel)
        if p.is_absolute():
            return p
        if self.models_root is not None and p.parts and p.parts[0] == "models":
            return self.models_root.joinpath(*p.parts[1:])
        return self.root / p

    def secret(self, key: str) -> str | None:
        """A secret from .env / the environment; placeholders count as missing."""
        v = (self.env.get(key) or "").strip()
        if not v or re.search(r"paste|your[-_ ]?(new[-_ ]?)?key|changeme|xxxx|example", v, re.I):
            return None
        return v

    def helpline(self) -> dict[str, str]:
        country = self.cfg.safety.country
        lines = self._data["safety"].get("helplines", {})
        h = lines.get(country) or lines.get("AU") or {}
        return {
            "helpline_name": h.get("crisis_name", "a crisis line"),
            "helpline_number": h.get("crisis_number", ""),
            "helpline_hours": h.get("crisis_hours", "any time"),
            "emergency_number": h.get("emergency_number", "your emergency number"),
        }

    def say_as(self) -> dict[str, str]:
        """How the voice says the helpline numbers for this country, e.g. {"000": "triple zero"}."""
        lines = self._data["safety"].get("helplines", {})
        h = lines.get(self.cfg.safety.country) or lines.get("AU") or {}
        return {str(k): str(v) for k, v in (h.get("say_as") or {}).items()}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name == "cfg":
            raise AttributeError(name)
        return getattr(self.cfg, name)
