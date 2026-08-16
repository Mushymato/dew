import argparse

from src.mod_dir import ModDir
from src.tui import DewApp


def run_updoot():
    parser = argparse.ArgumentParser(description="do nexus mod updoots")
    parser.add_argument("nexus_ids", nargs="*")
    parser.add_argument("--tui", action="store_true", default=False)
    parser.add_argument("-md", "--mods_dir", default="Mods")
    parser.add_argument("-ls", "--list_mods", action="store_true")
    args = parser.parse_args()

    mod_dir = ModDir(args.mods_dir)
    if args.tui:
        tui = DewApp(mod_dir)
        tui.run()
    elif args.nexus_ids:
        for nxid in args.nexus_ids:
            mod_dir.updooter.download_and_extract(nxid)
    elif args.list_mods:
        mod_dir.pprint_mods_installed()
    else:
        mod_dir.updooter.validate()


if __name__ == "__main__":
    run_updoot()
