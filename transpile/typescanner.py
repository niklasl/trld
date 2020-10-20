from __future__ import annotations
from typing import NamedTuple, Dict, List, Tuple, Union, Optional
import ast
from collections import OrderedDict
from pathlib import Path


class ClassType(NamedTuple):
    members: OrderedDict[str, str]
    base: Optional[str] = None


class FuncType(NamedTuple):
    args: OrderedDict[str, str]
    returns: str


Type = Union[str, ClassType, FuncType]


class TypeScanner(ast.NodeVisitor):

    def __init__(self, transpiler = None):
        self.modules: Dict[str, Dict[str, Type]] = {}
        self._in_src: List[Path] = []
        self._within: List[str] = []
        if transpiler:
            self._transpiler = transpiler
            self.repr_annot = transpiler.repr_annot
            self.map_name = transpiler.map_name

    @property
    def module(self):
        return self.modules.setdefault(str(self._in_src[-1]), {})

    def read(self, src):
        self._in_src.append(Path(src))
        with open(src) as f:
            code = f.read()
        tree = ast.parse(code)
        self.visit(tree)
        self._in_src.pop()

    def visit_ImportFrom(self, node):
        if node.module == 'typing':
            self._transpiler.visit_ImportFrom(node)
            return

        if node.level == 0:
            return

        if self._in_src:
            basedir = self._in_src[-1].parent
        if node.module is not None:
            src = node.module
            if basedir:
                for i in range(node.level - 1):
                    basedir = basedir.parent
                src = basedir / src
            src = src.with_suffix('.py')
            self.read(src)

    def visit_Assign(self, node):
        self._transpiler._handle_type_alias(node)

    def visit_AnnAssign(self, node):
        name = self.map_name(self.repr_annot(node.target))
        typename = self.repr_annot(node.annotation)
        self.addtype(name, typename)

    def visit_FunctionDef(self, node):
        name = self.map_name(node.name)
        args = OrderedDict()
        for arg in node.args.args:
            aname = self.map_name(arg.arg)
            args[aname] = self.repr_annot(arg.annotation)
        ret = self.repr_annot(node.returns) if node.returns else None
        self.addtype(name, FuncType(args, ret))

    def visit_ClassDef(self, node):
        name = self.map_name(node.name)
        self._within.append(name)
        self.module[name] = ClassType(
                OrderedDict(),
                self.repr_annot(node.bases[0]) if node.bases else None)
        self.generic_visit(node)
        self._within.pop()

    def addtype(self, name: str, typename: str, narrowed=False):
        ns = self.module[self._within[-1]] if self._within else self.module
        if isinstance(ns, ClassType):
            ns = ns.members
        ns[name] = typename


if __name__ == '__main__':
    import sys
    import json
    from .java import JavaTranspiler

    typescanner = TypeScanner(JavaTranspiler())
    for src in sys.argv[1:]:
        typescanner.read(src)

    print(json.dumps(typescanner.modules, indent=2))
