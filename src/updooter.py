import json
from io import BytesIO
import logging
from pathlib import Path
from pprint import pprint
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile
from py7zr import SevenZipFile

logger = logging.getLogger(__name__)


def cli_choose_menu(title, options, prompt):
    print(title)
    print()
    for idx, option in options:
        print(f"  {idx}. {option}")
    print()
    choice = input(prompt)
    try:
        return int(choice)
    except ValueError:
        return options[0][0]


GAME = "stardewvalley"


class Updooter:
    def __init__(self, mods_dir: Path, nexus_apikey: str):
        self.nexus_apikey = nexus_apikey
        self.mod_dir = mods_dir
        self.mod_raw: Path = mods_dir / ".raw"
        self.mod_raw.mkdir(exist_ok=True)
        self._mods_installed = None

    def nexus_get(self, endpoint, method="GET", should_throw=False, callback=None):
        req = Request(
            f"https://api.nexusmods.com/{endpoint}",
            method=method,
            headers={
                "accept": "application/json",
                "apikey": self.nexus_apikey,
                "user-agent": "NexusDownloader/1.0",
            },
        )
        try:
            with urlopen(req) as response:
                if callback:
                    callback(response)
                return json.loads(response.read())
        except HTTPError as e:
            print(f"{e.code}: {e.read()}")
            if should_throw:
                raise e
            return None

    def is_premium(self):
        if data := self.nexus_get("v1/users/validate.json", should_throw=True):
            return data["is_premium"]
        return False

    def validate(self):
        def pprint_headers(response):
            print(response.headers)

        data = self.nexus_get(
            "v1/users/validate.json", should_throw=True, callback=pprint_headers
        )
        pprint(data)

    def download_and_extract(self, modid):
        try:
            self._download_and_extract(modid)
        except Exception as e:
            logger.error(f"ERROR: Failed to process mod ID {modid}: {e}")

    def _download_and_extract(self, modid):
        if not self.is_premium():
            raise PermissionError("Need nexus premium")
        if not (
            main_files := self.nexus_get(
                f"v1/games/{GAME}/mods/{modid}/files.json?category=main"
            )
        ):
            print(f"FAILED: download_mod {modid}")
            return
        dl_files = (main_files["files"][0],)
        if len(main_files["files"]) > 1:
            options = []
            for idx, file in enumerate(main_files["files"]):
                options.append((idx, file["name"]))
            option_all = len(main_files["files"])
            options.append((option_all, "all files"))
            choice = cli_choose_menu(
                "Multiple main files:",
                options,
                "Pick (0): ",
            )
            if choice == option_all:
                dl_files = main_files["files"]
            else:
                dl_files = (main_files["files"][choice],)
        for file in dl_files:
            if not (
                dl_data := self.nexus_get(
                    f"v1/games/{GAME}/mods/{modid}/files/{file['id'][0]}/download_link.json"
                )
            ):
                continue
            for entry in dl_data:
                link = entry["URI"].replace(" ", "%20")
                print(f"[{modid:>5}] {file['name']}: {link}")
                req = Request(
                    link,
                    headers={
                        "apikey": self.nexus_apikey,
                        "user-agent": "NexusDownloader/1.0",
                    },
                )
                try:
                    with urlopen(req, timeout=30) as response:
                        stream = BytesIO(response.read())

                        # save the file to <mod_dir>/.staging
                        file_path = self.mod_raw / file["file_name"]
                        with open(file_path, "wb") as f:
                            f.write(stream.getvalue())

                        # try to extract
                        if file["file_name"].endswith(".7z"):
                            try:
                                with SevenZipFile(stream) as modzip:
                                    modzip.extractall(self.mod_dir)
                            except Exception as e:
                                # If py7zr fails (e.g., unsupported compression like BCJ2), save the raw file
                                print(f"Extraction failed for {file['file_name']}: {e}")
                                file_path = self.mod_dir / file["file_name"]
                                with open(file_path, "wb") as f:
                                    f.write(stream.getvalue())
                                print(f"Saved raw file instead: {file['file_name']}")
                        elif file["file_name"].endswith(".zip"):
                            with ZipFile(stream) as modzip:
                                modzip.extractall(self.mod_dir)
                    break
                except HTTPError as e:
                    print(f"{e}({e.code}): {e.read()}")
