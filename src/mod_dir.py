from collections import deque
import logging
from pathlib import Path
from typing import Dict, Generator, List
from dotenv import dotenv_values
import pyjson5

from .updooter import Updooter

logger = logging.getLogger(__name__)


class CaselessDict(dict):
    """Dict with a backing case insensitive dict"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fallback_dict = dict(self)
        for key, value in self.items():
            if isinstance(value, dict):
                value = CaselessDict(value)
            elif isinstance(value, list):
                value = [
                    CaselessDict(subv) if isinstance(subv, dict) else subv
                    for subv in value
                ]
            self[key] = value
            self._fallback_dict[key.upper()] = value

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            return self._fallback_dict[key.upper()]

    def get(self, key, default=None):
        return super().get(key) or self._fallback_dict.get(key.upper()) or default


class Manifest:
    def __init__(self, manifest_path):
        self._path = manifest_path
        with open(self._path, "r", encoding="utf-8-sig") as fn:
            try:
                self._data = CaselessDict(pyjson5.load(fn))
            except:
                raise
        self.unique_id = self._data["UniqueId"]
        self.nexus_id = None
        for upkey in self._data.get("UpdateKeys", []):
            if upkey.lower().startswith("nexus:"):
                self.nexus_id = upkey[6:].split("@")[0].strip()
                if not self.nexus_id.isdigit():
                    self.nexus_id = None
        try:
            self.content_pack_for = self._data["ContentPackFor"]["UniqueId"]
        except KeyError:
            self.content_pack_for = None
        self.dependent_on = [
            (dep["UniqueId"], dep.get("IsRequired"))
            for dep in self._data.get("Dependencies", [])
        ]
        # update in pass 2
        self.dependents = []
        self.content_packs = []

    def __repr__(self):
        return f"{self.unique_id}(n:{self.nexus_id})"

    @property
    def is_root(self):
        return not self.dependent_on and not self.content_pack_for

    def pprint(self, depth=0, prefix=""):
        print(" " * depth + prefix + str(self))
        for manifest in self.content_packs:
            manifest.pprint(depth=depth + 1, prefix="◆ ")
        for manifest in self.dependents:
            manifest.pprint(depth=depth + 1, prefix="◈ ")

    def add_dependents(self, mods_installed):
        mapped_dependent_on = []
        for dep in self.dependent_on:
            try:
                depon = mods_installed[dep[0].upper()]
            except Exception:
                continue
            mapped_dependent_on.append(depon)
            depon.dependents.append(self)
        self.dependent_on = mapped_dependent_on

        if self.content_pack_for:
            try:
                conpack = mods_installed[self.content_pack_for.upper()]
                conpack.content_packs.append(self)
                self.content_pack_for = conpack
            except:
                pass


class ModDir:
    def __init__(self, rel_path: str):
        self.dotenv: Dict[str, str] = dotenv_values()
        self.rel_path = rel_path
        self.path: Path = Path(self.dotenv["stardew_path"]) / self.rel_path
        self.path.mkdir(exist_ok=True)
        logger.info(f"Dir: {self.path}")
        self.updooter: Updooter = Updooter(self.path, self.dotenv["nexus_apikey"])
        self._mods_installed: CaselessDict[str, Manifest] = None

    @property
    def mods_installed(self) -> dict[str, Manifest]:
        if self._mods_installed is not None:
            return self._mods_installed
        self._mods_installed = {}
        for root, dirs, _files in self.path.walk():
            for dirname in dirs:
                manifest_path = root / dirname / "manifest.json"
                if not manifest_path.is_file():
                    continue
                manifest = Manifest(manifest_path)
                self._mods_installed[manifest.unique_id.upper()] = manifest
        for manifest in self._mods_installed.values():
            manifest.add_dependents(self._mods_installed)
        return self._mods_installed

    def pprint_mods_installed(self):
        root_manifests = [
            manifest for manifest in self.mods_installed.values() if manifest.is_root
        ]
        for manifest in root_manifests:
            manifest.pprint()
