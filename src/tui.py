from collections import deque
from typing import List
from textual.app import App, ComposeResult
from textual.widgets import Tree, Header

from .mod_dir import ModDir, Manifest


class DewApp(App):
    CSS = """
    Screen { align: center middle; }
    Tree { width: auto; padding: 1 }
    """

    def compose(self) -> ComposeResult:
        yield Header()

        root_manifests: List[Manifest] = [
            manifest
            for manifest in self.mod_dir.mods_installed.values()
            if manifest.is_root
        ]
        tree: Tree[str] = Tree(self.mod_dir.rel_path)
        for root_mani in root_manifests:
            self.grow_tree(tree.root, root_mani)
        tree.root.expand()
        yield tree

    def grow_tree(self, root_tree, root_mani: Manifest):
        walk_queue: deque[(int, Manifest)] = deque()
        walk_queue.append((0, root_mani, root_tree))
        depth: int = 0
        curr: Manifest = None
        tree = None
        while len(walk_queue) > 0:
            depth, curr, tree = walk_queue.popleft()
            if len(curr.content_packs) == 0 and len(curr.dependents) == 0:
                next_tree = tree.add_leaf(str(curr))
            else:
                next_tree = tree.add(str(curr))
                next_tree.expand()
                for manifest in curr.content_packs:
                    walk_queue.append((depth + 1, manifest, next_tree))
                for manifest in curr.dependents:
                    walk_queue.append((depth + 1, manifest, next_tree))

    def __init__(
        self,
        mod_dir: ModDir,
        driver_class=None,
        css_path=None,
        watch_css=False,
        ansi_color=None,
    ):
        super().__init__(driver_class, css_path, watch_css, ansi_color)
        self.mod_dir = mod_dir
        self.title = "dew"
