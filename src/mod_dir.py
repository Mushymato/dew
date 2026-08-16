import logging
from pathlib import Path
from typing import Dict, List
from dotenv import dotenv_values
from rich.text import Text
import pyjson5

from .updooter import Updooter

logger = logging.getLogger(__name__)

MANIFEST = "manifest.json"


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
    def __init__(self, manifest_path: Path, enabled: bool):
        self.manifest_path: Path = manifest_path.absolute().resolve()
        with open(self.manifest_path, "r", encoding="utf-8-sig") as fn:
            try:
                self._data = CaselessDict(pyjson5.load(fn))
            except:
                raise
        self.folder_path: Path = self.manifest_path.parent
        self.unique_id: str = self._data["UniqueId"]
        self.name: str = self._data["Name"]
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
        self.dependents: List[Manifest] = []
        self.content_packs: List[Manifest] = []
        # for manager
        self.current_enabled = enabled
        self.pending_enabled = self.current_enabled

    def __repr__(self):
        return f"{self.unique_id} [{self.status_mark}](n:{self.nexus_id})"

    @property
    def richtext(self):
        if self.pending_enabled:
            return Text(str(self))
        return Text(str(self), style="strike")

    @property
    def status_mark(self):
        return "✔" if self.pending_enabled else " "

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

    def toggle_pending_status(self):
        self.pending_enabled = not self.pending_enabled

    def apply_pending_status(self, mod_path: Path, mod_disabled_path: Path):
        if self.pending_enabled == self.current_enabled:
            return
        if self.current_enabled and not self.pending_enabled:
            self.folder_path = self.folder_path.move_into(mod_disabled_path)
        elif not self.current_enabled and self.pending_enabled:
            self.folder_path = self.folder_path.move_into(mod_path)
        self.manifest_path = self.folder_path / MANIFEST
        self.current_enabled = self.pending_enabled


class ModDir:
    def __init__(self, rel_path: str):
        self.dotenv: Dict[str, str] = dotenv_values()
        self.rel_path = rel_path
        self.stardew_path: Path = Path(self.dotenv["stardew_path"])
        self.mod_path: Path = self.stardew_path / self.rel_path
        self.mod_path.mkdir(exist_ok=True)
        self.mod_disabled_path: Path = self.mod_path / ".disabled"
        self.mod_disabled_path.mkdir(exist_ok=True)
        logger.info(f"Dir: {self.mod_path}")
        self.updooter: Updooter = Updooter(self.mod_path, self.dotenv["nexus_apikey"])
        self._mods_installed: CaselessDict[str, Manifest] = None

    @property
    def mods_installed(self) -> dict[str, Manifest]:
        if self._mods_installed is not None:
            return self._mods_installed
        self._mods_installed = self.init_mods_installed()
        return self._mods_installed

    def init_mods_installed(self) -> dict[str, Manifest]:
        mods_installed: dict[str, Manifest] = {}
        for root, dirs, files in self.mod_path.walk(follow_symlinks=True):
            if MANIFEST in files:
                dirs.clear()
                manifest_path = (root / MANIFEST).absolute()
                if not manifest_path.is_file():
                    continue
                enabled = all(
                    (
                        not part.startswith(".")
                        for part in manifest_path.relative_to(self.mod_path).parts
                    )
                )
                manifest = Manifest(manifest_path, enabled)
                upper_id = manifest.unique_id.upper()
                if upper_id in mods_installed:
                    continue
                mods_installed[manifest.unique_id.upper()] = manifest
        for manifest in mods_installed.values():
            manifest.add_dependents(mods_installed)
        return mods_installed

    def pprint_mods_installed(self):
        for manifest in self.mods_installed.values():
            if manifest.is_root:
                manifest.pprint()

    def apply_all_pending_status(self):
        for manifest in self.mods_installed.values():
            manifest.apply_pending_status(self.mod_path, self.mod_disabled_path)
