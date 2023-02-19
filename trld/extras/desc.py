"""
Desc - Descriptions on Surfaces, about Subjects in a Space, viewed in Context.
"""
from __future__ import annotations

import abc
from typing import (Dict, Generic, Iterable, Iterator, List, Optional, Set,
                    TypeVar, Union, cast)

try:
    from typing_extensions import NamedTuple  # for Generic prior to 3.11
except ImportError:
    from typing import NamedTuple  # type: ignore[assignment]

from ..api import parse_rdf, serialize_rdf, text_input
from ..jsonld.base import (BASE, CONTEXT, GRAPH, ID, LANGUAGE, LIST, SET, TYPE,
                           VALUE, JsonMap, JsonObject)
from ..jsonld.compaction import compact, iri_compaction, shorten_iri
from ..jsonld.context import Context
from ..jsonld.expansion import expand
from ..jsonld.extras.frameblanks import frameblanks
from ..jsonld.flattening import flatten
from ..jsonld.rdf import RdfLiteral, to_jsonld_object
from ..platform.common import resolve_iri
from ..platform.io import Output
from ..rdfterms import RDF_LANGSTRING, RDF_TYPE, XSD, XSD_STRING


class Id:
    """
    That which is used to name a subject in RDF triples.
    """

    _s: str

    def __init__(self, s):
        self._s = s

    def __str__(self):
        return str(self._s)

    def __repr__(self):
        return f"{type(self).__name__}({self._s!r})"

    def to_jsonld(self) -> JsonMap:
        return {ID: self._s}


class Link(Id):
    """
    An IRI, or a URI. Commonly a URL. Let's call it a Link.
    """

    pass


class Blank(Id):
    """
    A mark on a surface. Local and not ussable for linking, or any
    identification beyond the surface it belongs to.
    """

    def __init__(self, s: str):
        super().__init__(f"_:{s}" if not s.startswith('_:') else s)


class Literal(NamedTuple):
    """
    Value which "represents itself". The pragmatic end-of-the-graph used when
    you need to get data out there. Tagged with a datatype for some semantics
    to remain, or with a language tag (defined out-of-band, link-wise).
    """

    value: str
    datatype: Description
    language: Optional[str] = None

    def __str__(self):
        return self.value

    def to_native(self):
        return to_jsonld_object(
            RdfLiteral(self.value, self.datatype.id, self.language), None, True
        )[VALUE]

    @staticmethod
    def from_jsonld(surface: Surface, idata: JsonMap) -> Literal:
        value = cast(str, idata[VALUE])
        datatype = (
            RDF_LANGSTRING
            if LANGUAGE in idata
            else cast(str, idata[TYPE])
            if TYPE in idata
            else XSD_STRING
        )
        typedesc = surface._desc(datatype)
        return Literal(value, typedesc, cast(Optional[str], idata.get(LANGUAGE)))

    def to_jsonld(self) -> JsonMap:
        literal: JsonMap = {VALUE: self.value}
        if self.language is not None:
            literal[LANGUAGE] = self.language
        elif self.datatype != XSD_STRING:
            literal[TYPE] = str(self.datatype.id)
        return literal


class OrderedList:
    surface: Surface
    _items: List[JsonMap]
    # _cache: List[Object]

    def __init__(self, surface: Surface, items: List):
        self.surface = surface
        self._items = items

    def __repr__(self) -> str:
        return f"{type(self).__name__}(items={len(self._items)})"

    def __iter__(self) -> Iterator[Object]:
        surface = self.surface
        for item in self._items:
            yield surface._make_object_view(item)

    def to_jsonld(self) -> JsonMap:
        return {LIST: self._items}


Described = TypeVar('Described', bound='About')


Object = Union[Described, OrderedList, Literal]


Ref = Union[str, Id, Described]


class About(abc.ABC, Generic[Described]):
    id: Optional[Id]

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r})"

    def __iter__(self) -> Iterator[PredicateObjects]:
        return iter(self.get_predicates_objects())

    def get_id(self) -> Optional[Id]:
        return self.id

    def get_compact_iri(self) -> Optional[str]:
        if self.id is None:
            return None
        return self._get_active_context().compact_iri(str(self.id))

    def get_vocab_term(self) -> Optional[str]:
        if self.id is None:
            return None
        return self._get_active_context().vocab_term(str(self.id))

    def get(self, p: str) -> Optional[Union[Object, Set[Object]]]:
        """
        Get a "compact" result:
        - `None` if there are no objects for this predicate.
        - One `Object` if only one, and context has not defined a `@set` for
          this term.
        - Otherwise, returns a Set of Objects.
        """
        objects = self.get_objects(p)
        if len(objects) == 0:
            return None
        if len(objects) == 1:
            term = self._get_active_context().context.terms.get(p)
            if term is None or SET not in term.container:
                for o in objects:
                    return o
        return objects

    @abc.abstractmethod
    def _get_active_context(self) -> ContextView:
        ...

    def get_type(self) -> Optional[Described]:
        for tdesc in self.get_types():
            return tdesc
        return None

    @abc.abstractmethod
    def get_types(self) -> Iterable[Described]:
        ...

    def get_objects(self, p: str) -> Set[Object]:
        pos = self.get_objects_by_predicate(p)
        return pos.objects if pos is not None else set()

    # TODO: def get_arcs(self) -> Arc: ...

    def get_predicates_objects(self) -> Iterable[PredicateObjects]:
        for p in self._predicate_keys():
            pos = self.get_objects_by_predicate(p)
            if pos is not None:
                yield pos

    @abc.abstractmethod
    def _predicate_keys(self) -> Iterable[str]:
        ...

    @abc.abstractmethod
    def get_objects_by_predicate(self, p: str) -> Optional[PredicateObjects]:
        ...


class PredicateObjects(Generic[Described], NamedTuple):
    predicate: Described
    objects: Set[Object[Described]]


# class Arc(NamedTuple):
#     predicate: Description
#     annotation: Optional[Description]
#     object: Object


class Description(About['Description']):
    id: Optional[Id]
    surface: Surface

    _data: JsonMap
    _cache: Dict[str, PredicateObjects]

    def __init__(self, surface: Surface, data: Optional[JsonMap] = None):
        self.surface = surface
        self._data = data or {}
        self.id = _make_id(cast(Optional[str], self._data.get(ID)))
        self._cache = {}

    def __len__(self) -> int:
        return len(self._data)

    def _predicate_keys(self) -> Iterable[str]:
        return self._data

    def get_types(self) -> Iterable[Description]:
        if TYPE not in self._data:
            return
        for t in _aslist(self._data[TYPE]):
            assert isinstance(t, str)
            yield self.surface._desc(t)

    def get_objects_by_predicate(
        self, p: str
    ) -> Optional[PredicateObjects[Description]]:
        if p == ID:
            return None
        p = self._expand_term(p)

        pos = self._cache.get(p)

        if pos is None:
            idata = self._data.get(p)
            if p in self._data:
                pdesc = self.surface._desc(p)
                pos = PredicateObjects(pdesc, set())
                self._cache[p] = pos
                for idata in cast(List, self._data[p]):
                    item = self._make_object_view(cast(JsonMap, idata))
                    pos.objects.add(item)

        return pos

    def add(self, ref: Ref, obj) -> bool:
        p = self._expand_term(ref)
        raw = cast(str, ref) if ref == TYPE else p

        # TODO: or if isinstance(Object) check index...
        if raw not in self._data:
            self._data[raw] = []

        item = self._make_object_view(obj) if isinstance(obj, Dict) else obj
        if p not in self._cache or item not in self._cache[p]:
            if isinstance(obj, (Description, OrderedList, Literal)):
                obj = obj.to_jsonld()
            # TODO: optimize (check item in set, convert all back to raw)?
            objects = cast(List, self._data[raw])
            if not any(o == obj for o in objects):
                self._cache.pop(p, None)
                objects.append(obj)
                self.get_objects_by_predicate(p)  # rebuild it all...
                self.surface.space._added(self.id, p, item)
                return True

        return False

    def remove(
        self, ref: Ref, matching: Optional[Union[Object, JsonMap]] = None
    ) -> int:
        p = self._expand_term(ref)
        raw = cast(str, ref) if ref == TYPE else p
        if raw not in self._data:
            return -1

        count = 0
        objects = cast(List, self._data[raw])
        if matching:
            # TODO: or if isinstance(Object) check index...
            try:
                idx = objects.index(matching)
            except ValueError:
                idx = -1
            if idx > -1:
                objects.pop(idx)
                count = 1
                if len(objects) == 0:
                    del self._data[raw]
                self.surface.space._removed(self.id, p, matching)
        else:
            count = len(objects)
            del self._data[raw]

        # TODO: only clear cache if last; and return -1 if so?
        if count > 0 and p in self._cache:
            del self._cache[p]

        return count

    def has_predicate(self, ref: Ref) -> bool:
        p = self._expand_term(ref)
        return p in self._data

    def is_described(self) -> bool:
        return len(self._data) > (1 if ID in self._data else 0)

    def find(self) -> Subject:
        return cast(Subject, self.surface.space.find(self.id))

    def load(self) -> Optional[Description]:
        if self.id is None:
            return None
        surface = self.surface.space.load(self.id)
        return surface.get(self.id)

    def to_jsonld(self) -> JsonObject:
        return self.surface.to_jsonld(self._data)

    def serialize(self, format: str = 'trig') -> str:
        return _serialize(self.to_jsonld(), format)

    def _get_active_context(self) -> ContextView:
        return self.surface._context

    def _expand_term(self, ref: Ref) -> str:
        if ref == TYPE:
            ref = RDF_TYPE
        p = cast(str, _opt_str(ref))
        return self._get_active_context().expand_term(p)

    def _make_object_view(self, idata: JsonMap) -> Object[Description]:
        return self.surface._make_object_view(idata)


class Surface:
    space: Space
    id: Optional[Id]
    # document: Description

    _index: Dict[str, Description]
    _context: ContextView
    _context_data: Optional[dict]
    _blank_count: int

    def __init__(self, space: Space, id: Optional[Id] = None):
        self.id = id
        self.space = space
        self._context_data = None
        self._index = {}
        self._blank_count = 0
        self._context = ContextView(Context(_opt_str(self.id)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r})"

    def __iter__(self) -> Iterator[Description]:
        return iter(self._index.values())

    @property
    def base(self):
        return str(self.id) if self.id else self.space.base

    def parse_data(self, s: str, format=None):
        self.parse(text_input(s, format))

    def parse(self, inp: object, format=None):
        data = parse_rdf(inp, format)
        self.add_data(data)

    def add_data(self, data: JsonObject):
        if isinstance(data, dict) and CONTEXT in data:
            self.set_context(data[CONTEXT])
        items = expand(data, self.base)
        items = cast(list, flatten(items))
        for item in items:
            self.add(Description(self, item))

    def update_context(self, ctx: JsonMap) -> None:
        ctx1 = self._context_data or {}
        ctx1.update(ctx)
        self.set_context(ctx1)

    def set_context(self, ctx: JsonMap) -> None:
        self._context_data = ctx
        self._context = ContextView(Context(_opt_str(self.id)).get_context(ctx))

    def add(self, desc: Description):
        key = str(desc.id)
        self._index[key] = desc
        self.space._added_desc(desc)

    def get(self, ref: Ref) -> Optional[Description]:
        iri = _opt_str(ref)
        if iri is not None:
            iri = self.space.context.expand_relative_iri(iri)
            return self._index.get(iri)
        return None

    def to_jsonld(self, data: Optional[JsonObject] = None) -> JsonObject:
        data = data or [
            desc._data for desc in self._index.values() if desc.is_described()
        ]
        return self.space.to_jsonld(data, self._context_data, _opt_str(self.id))

    def serialize(self, format: str = 'trig') -> str:
        return _serialize(self.to_jsonld(), format)

    def _genid(self) -> str:
        self._blank_count += 1
        return f"_:{self._blank_count}"

    def _make_object_view(self, idata: JsonMap) -> Object[Description]:
        if VALUE in idata:
            return Literal.from_jsonld(self, idata)
        elif LIST in idata:
            return OrderedList(self, cast(list, idata[LIST]))
        elif GRAPH in idata:
            # FIXME: Description with inner_surface? (And Subject with inner...space?)
            raise NotImplementedError
        else:
            # TODO: we lose ANNOTATION at this point ...
            return self._desc(_make_id(idata))

    def _desc(self, ref: Optional[Ref]) -> Description:
        desc = None
        if ref:
            descid = cast(str, _opt_str(ref))
            desc = self.get(descid)
        if desc is None:
            desc = Description(self, {ID: descid})
            self.add(desc)

        return desc


class Subject(About['Subject']):

    space: Space
    id: Id
    _union: Set[Description]
    _reverse: Dict[str, SubjectsByPredicate]

    def __init__(self, space: Space, id: Id):
        self.space = space
        self.id = id
        self._union = set()
        self._reverse = {}

    def __getattr__(self, key: str):
        return self.get(key)

    def get_descriptions(self) -> Set[Description]:
        return self._union

    def _get_active_context(self) -> ContextView:
        return self.space.context

    def _predicate_keys(self) -> Iterable[str]:
        return set(key for desc in self._union for key in desc._predicate_keys())

    def get_types(self) -> Iterable[Subject]:
        return set(
            self.space._term_subject(tdesc)
            for desc in self._union
            for tdesc in desc.get_types()
        )

    def get_objects_by_predicate(self, p: str) -> Optional[PredicateObjects[Subject]]:
        p = self._get_active_context().expand_term(p)
        for desc in self._union:
            pos = desc.get_objects_by_predicate(p)
            if pos is not None:
                spred = self.space._term_subject(pos.predicate)
                return PredicateObjects(
                    cast(Subject, spred),
                    set(
                        cast(Subject, self.space.find(o.id))
                        if isinstance(o, Description)
                        else o  # FIXME: Literal datatype from Description to Subject!
                        for o in pos.objects
                    ),
                )
        return None

    def get_subject(self, p: str) -> Optional[Subject]:
        for o in self.get_subjects(p):
            return o
        return None

    def get_subjects(self, p: str) -> Iterable[Subject]:
        sbp = self.get_subjects_by_predicate(p)
        if sbp is None:
            return iter(())
        return sbp.subjects

    def get_subjects_by_predicate(self, p: str) -> Optional[SubjectsByPredicate]:
        p = self._get_active_context().expand_term(p)
        if len(self._reverse) == 0:
            self.space._full_index()
        return self._reverse.get(p)


class SubjectsByPredicate(NamedTuple):
    subjects: Set[Subject]
    predicate: Subject


class Space:
    surfaces: Dict[str, Surface]
    context: ContextView

    _subjects: Dict[str, Subject]
    _cache: Optional[object]

    def __init__(self, base: Optional[str] = None, context: Optional[object] = None):
        self.surfaces = {}
        self.context = ContextView(Context(base))
        if context:
            self.context.use(context)
        self._subjects = {}

    @property
    def base(self) -> str:
        return self.context.context.base_iri

    @base.setter
    def base(self, base: str) -> None:
        self.context.use({BASE: base})

    def new_surface(self, r: Optional[Ref] = None) -> Surface:
        sid = _make_id(r) if r else None
        surface = Surface(self, sid)
        self.surfaces[str(sid) or f"_:{id(surface)}"] = surface
        return surface

    def find(self, ref: Optional[Ref]) -> Optional[Subject]:
        if ref is None:
            return None

        key = _opt_str(ref)
        assert key is not None
        sid = self.context.expand_relative_iri(key)

        return self._subjects.get(sid)

    def load(self, ref: Ref, format=None) -> Surface:
        if isinstance(ref, str) and self.base:
            ref = resolve_iri(self.base, ref)

        surface = self.new_surface(ref)
        surface.parse(str(surface.id), format)

        return surface

    def to_jsonld(
        self, data: JsonObject, ctx_data: Optional[dict], base: Optional[str]
    ):
        context = {CONTEXT: ctx_data} if ctx_data is not None else self.context.context
        result = compact(context, data, base or self.base)

        # NOTE: mutates; OK since compact is a deep copy...
        result = frameblanks(result)

        assert isinstance(result, Dict)
        if CONTEXT not in result:
            ctx = result[CONTEXT] = []
            if self.base:
                ctx.append({BASE: self.base})
            if ctx_data:
                ctx.append(ctx_data)

        return result

    def _added_desc(self, desc: Description):
        if not desc.is_described():
            # TODO: track vocab usage (predicates, types, datatypes)?
            return

        key = str(desc.id)
        subject = self._subjects.get(key)
        if subject is None:
            subject = Subject(self, cast(Id, desc.id))
            self._subjects[key] = subject

        subject._union.add(desc)

    def _added(self, s: Optional[Id], p: str, o: Id):
        # TODO: Ensure _added_desc is called for s and o?
        # TODO: Add to o._reverse (and/or mark index as dirty...)
        ...

    def _removed(self, s: Optional[Id], p: str, o: Union[JsonMap, Object]):
        # TODO: drop from o._reverse (and/or mark index as dirty...)
        ...

    def _term_subject(self, ref: Ref) -> Subject:
        s = self.find(ref)
        if s is None:
            s = Subject(self, cast(Id, _make_id(ref)))
        return s

    def _full_index(self):
        # TODO: log this and smoke-test that it isn't called "too much"...
        # print('FULL INDEX')
        for s in self._subjects.values():
            for pos in s.get_predicates_objects():
                key = str(pos.predicate.id)
                for o in pos.objects:
                    if not isinstance(o, Subject):
                        continue
                    subjs = o._reverse.get(key)
                    if subjs is None:
                        subjs = set()
                        o._reverse[key] = subjs
                    subjs.add(s)


class ContextView:
    context: Context

    def __init__(self, context: Context):
        self.context = context

    def __setitem__(self, key, value):
        self.use({key: value})

    def use(self, data: object):
        if isinstance(data, Context):
            self.context = data
        else:
            ctx = data._context_data if isinstance(data, Surface) else data
            self.context = self.context.get_context(ctx)

    def pop(self) -> Optional[Context]:
        if self.context.previous_context is None:
            return None
        popped = self.context
        self.context = self.context.previous_context
        return popped

    def expand_relative_iri(self, s: str) -> str:
        return cast(str, self.context.expand_doc_relative_iri(s))

    def expand_term(self, s: str):
        return self.context.expand_vocab_iri(s)

    def compact_iri(self, s: str):
        return shorten_iri(self.context, s)

    def vocab_term(self, s: str):
        return iri_compaction(self.context, s)


def _make_id(r: Union[Ref, JsonMap, None]) -> Optional[Id]:
    if r is None:
        return None
    if isinstance(r, Description):
        return r.id
    if isinstance(r, Id):
        return r
    s: Optional[str]
    if isinstance(r, Dict):
        s = cast(Optional[str], r.get(ID))
        if s is None:
            return None
    else:
        s = r
    assert isinstance(s, str)
    return Link(s) if not s.startswith('_:') else Blank(s)


def _opt_str(ref: Ref) -> Optional[str]:
    if isinstance(ref, str):
        return ref
    if isinstance(ref, Description):
        if ref.id is None:
            return None
        ref = ref.id
    return str(ref)


def _aslist(o):
    """
    >>> _aslist(None)
    []
    >>> _aslist(1)
    [1]
    >>> _aslist([1])
    [1]
    """
    return [] if o is None else o if isinstance(o, list) else [o]


def _serialize(data: JsonObject, format: str) -> str:
    out = Output()
    serialize_rdf(data, format, out)
    return out.get_value()


if __name__ == '__main__':
    import doctest

    doctest.testmod()
    doctest.testfile("../../docs/source/desc.md")
