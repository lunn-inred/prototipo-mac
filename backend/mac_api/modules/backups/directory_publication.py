"""Publicação reversível dentro do volume; nunca renomeia o mount point."""
import os
import shutil
from uuid import uuid4


class DirectoryPublication:
    def __init__(self, root):
        self.root = root
        self.previous = root / f'.mac-before-{uuid4().hex}'
        self.incoming = root / f'.mac-incoming-{uuid4().hex}'
        self.old_names, self.new_names = [], []

    def publish(self, stage):
        self.root.mkdir(parents=True, exist_ok=True)
        # Copiar para o volume ANTES dos renames evita EXDEV entre overlay e bind.
        shutil.copytree(stage, self.incoming)
        self.previous.mkdir()
        children = [p for p in self.root.iterdir() if p not in (self.previous, self.incoming)]
        for child in children:
            os.replace(child, self.previous / child.name)
            self.old_names.append(child.name)
        for child in self.incoming.iterdir():
            os.replace(child, self.root / child.name)
            self.new_names.append(child.name)

    def rollback(self):
        for name in reversed(self.new_names):
            os.replace(self.root / name, self.incoming / name)
        for name in reversed(self.old_names):
            os.replace(self.previous / name, self.root / name)
        self.cleanup()

    def cleanup(self):
        for path in (self.previous, self.incoming):
            if path.exists():
                shutil.rmtree(path)
