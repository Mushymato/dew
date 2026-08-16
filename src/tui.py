import os
import subprocess
from collections import deque
from typing import List
from textual import work
from textual.app import App, ComposeResult
from textual.command import Provider, Hits, Hit, DiscoveryHit
from textual.widgets import Tree, Footer, TabbedContent, TabPane, DataTable
from .mod_dir import ModDir, Manifest


class ManifestTree(Tree[str]):

    def __init__(
        self, label, data=None, *, name=None, id=None, classes=None, disabled=False
    ):
        super().__init__(
            label, data, name=name, id=id, classes=classes, disabled=disabled
        )
        self.root_manifests = None

    def set_root_manifests(self, root_manifests):
        self.root_manifests = root_manifests
        if self.root_manifests is None:
            return
        for root_mani in self.root_manifests:
            walk_queue: deque[(int, Manifest, ManifestTree)] = deque()
            walk_queue.append((0, root_mani, self.root))
            depth: int = 0
            curr: Manifest = None
            tree: ManifestTree = None
            while len(walk_queue) > 0:
                next_tree: ManifestTree = None
                depth, curr, tree = walk_queue.popleft()
                if len(curr.content_packs) == 0 and len(curr.dependents) == 0:
                    next_tree = tree.add_leaf(curr.richtext)
                    next_tree.data = curr
                else:
                    next_tree = tree.add(curr.richtext)
                    next_tree.data = curr
                    next_tree.expand()
                    for manifest in curr.content_packs:
                        walk_queue.append((depth + 1, manifest, next_tree))
                    for manifest in curr.dependents:
                        walk_queue.append((depth + 1, manifest, next_tree))


class ManifestTable(DataTable):
    def set_all_manifests(self, all_manifests: List[Manifest]):
        self.all_manifests = all_manifests
        if self.all_manifests is None:
            return
        self.add_column("Nexus", key="nexus")
        self.add_column("", key="status")
        self.add_column("Mod", key="mod")
        for mani in self.all_manifests:
            self.add_row(
                mani.nexus_id,
                mani.status_mark,
                mani.unique_id,
                key=mani.unique_id,
            )
        self.sort("mod", key=lambda txt: txt)


class SMAPICommands(Provider):
    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        assert isinstance(self.app, DewApp)
        score = matcher.match("smapi")
        if score > 0:
            yield Hit(
                score,
                matcher.highlight("Launch SMAPI"),
                self.app.run_smapi,
                help="Launch SMAPI",
            )

    async def discover(self) -> Hits:
        yield DiscoveryHit(
            "Launch SMAPI",
            self.app.run_smapi,
            help="Launch SMAPI",
        )


class DewApp(App):
    CSS = """
    TabbedContent { height: auto; width: 100%; align: center middle; }
    TabPane { width: 100%; align: center middle; }
    ManifestTable { width: 100%; }
    ManifestTree { width: 100%; }
    """

    COMMANDS = App.COMMANDS | {SMAPICommands}

    def __init__(
        self,
        mod_dir: ModDir,
        driver_class=None,
        css_path=None,
        watch_css=False,
        ansi_color=None,
    ):
        super().__init__(driver_class, css_path, watch_css, ansi_color)
        self.mod_dir: ModDir = mod_dir
        self.title = "dew"
        self.smapi_procs: List[subprocess.Popen] = []

    def run_smapi(self):
        # do any required moves now
        mod_dir: ModDir = self.app.mod_dir
        mod_dir.apply_all_pending_status()
        # launch
        environ = dict(os.environ)
        environ["SMAPI_MODS_PATH"] = str(mod_dir.mod_path)
        # TODO: configure console
        self.smapi_procs.append(
            subprocess.Popen(
                [
                    "konsole",
                    "--new-tab",
                    "-e",
                    self.mod_dir.stardew_path / "StardewModdingAPI",
                ],
                cwd=self.mod_dir.stardew_path,
                env=environ,
            )
        )

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="list"):
            with TabPane("list", id="list"):
                yield ManifestTable(cursor_type="row", zebra_stripes=True)
            with TabPane("tree", id="tree"):
                tree: ManifestTree = ManifestTree(self.mod_dir.rel_path)
                tree.root.expand()
                tree.root.allow_expand = False
                yield tree

        yield Footer()

    def on_mount(self) -> None:
        tbl = self.query_one(ManifestTable)
        tbl.set_all_manifests(list(self.mod_dir.mods_installed.values()))
        tree = self.query_one(ManifestTree)
        tree.set_root_manifests(
            [
                manifest
                for manifest in self.mod_dir.mods_installed.values()
                if manifest.is_root
            ]
        )

    # def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
    #     event.node.data.toggle_pending_status()
    #     event.node.set_label(event.node.data.richtext)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        mani: Manifest = self.mod_dir.mods_installed.get(event.row_key.value.upper())
        mani.toggle_pending_status()
        event.control.update_cell(
            event.row_key,
            "status",
            mani.status_mark,
        )

    async def action_quit(self) -> None:
        for smapi in self.smapi_procs:
            smapi.kill()
        self.exit()
