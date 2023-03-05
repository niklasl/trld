from typing import Dict, List, Optional, cast

from .terms import RDFNS, RDFGNS, XMLNS, XMLNSNS, XSD_STRING
from ..jsonld.flattening import BNodes

from ..jsonld.base import (BASE, CONTAINER, CONTEXT, GRAPH, ID, INDEX,
                           LANGUAGE, LIST, REVERSE, SET, TYPE, VALUE, VOCAB)

from ..jsonld.star import ANNOTATION, ANNOTATED_TYPE_KEY


def serialize(data, outstream):
    ser = RDFXMLSerializer(XMLWriter(outstream, 2), data)
    ser.serialize()


class RDFXMLSerializer:

    context: Dict[str, object]

    # NOTE: RDF/XML has no full RDF-star annotation support, but allows
    # reification by using rdf:ID on arc (predicate) elements:
    # <https://www.w3.org/TR/rdf-syntax-grammar/#section-Syntax-reifying>
    use_arc_ids: bool

    # TODO: Define formal triple representation IRI or just use BNodes?
    triple_id_form: Optional[str]

    def __init__(self, builder, data, use_arc_ids=True, triple_id_form='sha1'):
        self.builder = builder
        self.bnodes = BNodes()
        self._deferreds = []
        self.context = data[CONTEXT]
        self.use_arc_ids = use_arc_ids
        self.triple_id_form = triple_id_form
        self.nodes = self._get_nodes(data)

    @staticmethod
    def _get_nodes(data) -> List[Dict]:
        nodes = data
        if not isinstance(nodes, List):
            nodes = data[GRAPH] or data
        if not isinstance(nodes, List):
            nodes = [nodes]
        return nodes

    def serialize(self):
        self.builder.openElement('rdf:RDF', self.contextAttrs(self.context))
        for node in self.nodes:
            self.handleNode(node)
        self._clear_deferred()
        self.builder.closeElement()

    def expand(self, qname: str) -> str:
        return self.resolve(qname, False)

    def resolve(self, qname: str, as_term=True) -> str:
        if qname == TYPE:
            return f"{RDFNS}type"

        # TODO [63a61bb3]: use jsonld context resolution!
        pfx, cln, lname = qname.partition(':')
        if not lname and as_term:
            lname = pfx
            pfx = VOCAB

        if pfx not in self.context:
            # TODO: [63a61bb3]!
            #if BASE in self.context:
            #    return resolve_iri(self.context[BASE] + qname)
            return qname

        return cast(str, self.context[pfx]) + lname

    def contextAttrs(self, context: Dict[str, object]) -> Dict[str, str]:
        if not isinstance(context, Dict):
            return {}

        attrs = {}

        rdfpfx = None
        gpfx = None

        for key in context.keys():
            value = context[key]
            if isinstance(value, str):
                if key == BASE:
                    attrs['xml:base'] = value
                else:
                    if key == VOCAB:
                        attrs['xmlns'] = value
                    else:
                        attrs[f"xmlns:{key}"] = value
                if value == RDFNS:
                    rdfpfx = key
                elif value == RDFGNS:
                    gpfx = key

        if rdfpfx != 'rdf':
            if rdfpfx is not None:
                pass  # TODO: switch to self.prefix...
            # elif rdfns != RDFNS {
            #    raise Error("Cannot handle rdf prefix for non-RDF namespace: .")
            attrs['xmlns:rdf'] = RDFNS
        if gpfx != 'rdfg':
            attrs['xmlns:rdfg'] = RDFGNS

        return attrs

    def handleNode(self, node: Dict, key: Optional[str] = None):
        graph = node.get(GRAPH)
        id = cast(str, node.get(ID))
        id = self.expand(id)

        types = node.get(TYPE)
        if not types:
            types = []
        if not isinstance(types, List):
            types = [types]

        assert isinstance(types, List)

        firstType = types[0] if len(types) > 0 else None
        annot_first_type = False
        if isinstance(firstType, Dict):
            annot_first_type = True
            firstType = None # firstType[ANNOTATED_TYPE_KEY]

        # FIXME: nested rdf:RDF with @rdf:about is non-standard!
        # RDF/XML doesn't support named graphs at all! Pre 1.0 RDF had
        # rdf:bagID which could sort of work as a stand-in though...
        # <https://www.w3.org/2000/03/rdf-tracking/#rdfms-nested-bagIDs>
        tag = firstType if firstType else 'rdfg:Graph' if graph else 'rdf:Description'

        if id is not None and isinstance(id, Dict):
            qid = self.handleQuotedTriple(id)
            id = f"_:{qid}"

        aboutattr = (
            ({'rdf:nodeID': id[2:]} if id.startswith('_:') else {'rdf:about': id})
            if id is not None
            else {}
        )

        revs = node.get(REVERSE)

        has_simple_type = len(types) < 2 and not annot_first_type
        if has_simple_type and not revs and not graph and not _nonspecial(node):
            self.builder.addElement(tag, aboutattr)
        else:
            self.builder.openElement(tag, aboutattr)
            self.handleType(id, types if annot_first_type else types[1:])

            self.handleContents(node)

            if graph:
                self.builder.openElement('rdfg:isGraph', {'rdf:parseType': 'GraphLiteral'})
                if isinstance(graph, List):
                    for it in graph:
                        self.handleNode(it)
                self.builder.closeElement()

            if revs:
                self.handleReverses(revs)

            self.builder.closeElement()

        self._clear_deferred()

    def _clear_deferred(self):
        if not self._deferreds:
            return

        for annot, triplenode, qid in self._deferreds:
            if self.use_arc_ids:
                self.builder.openElement('rdf:Description', {'rdf:ID': qid})
                self.handleContents(annot)
                self.builder.closeElement()
            else:
                self.handleQuotedTriple(triplenode, annot)

        self._deferreds = []

    def handleType(self, id: str, types: List):
        for type in types:
            v: str
            annot: Optional[Dict] = None
            if isinstance(type, Dict):
                v = type[ANNOTATED_TYPE_KEY]
                annot = type.get(ANNOTATION)
            else:
                v = type
            type_uri = self.resolve(v)
            attrs = {'rdf:resource': type_uri}
            self.handleAnnotation(id, TYPE, attrs, {ID: type_uri, ANNOTATION: annot})
            self.builder.addElement('rdf:type', attrs)

    def handleContents(self, node: Dict[str, object], _tag = None): # TODO: use _tag?
        id = cast(Optional[str], node.get(ID))

        for key in node.keys():
            if key.startswith('@'):
                continue

            value = node[key]

            if self.isLiteral(value):
                self.handleLiteral(id, key, value)
            elif isinstance(value, List):
                for part in value:
                    partnode = {ID: id, key: part}
                    self.handleContents(partnode)
            elif isinstance(value, Dict):
                if value.get(LIST):
                    attrs = {'rdf:parseType': "Collection"}
                    self.handleAnnotation(id, key, attrs, value)
                    self.builder.openElement(key, attrs)
                    for part in value[LIST]:
                        self.handleContents(part, 'rdf:Description')  # TODO: hack
                    self.builder.closeElement()
                elif ID in value and len(value) == 1 if ANNOTATION not in value else 2:
                    self.handleRef(key, value)
                else:
                    if key:
                        attrs = {}
                        self.handleAnnotation(id, key, attrs, value)
                        self.builder.openElement(key, attrs)
                    self.handleNode(value, key)
                    if key:
                        self.builder.closeElement()

    def isLiteral(self, value) -> bool:
        if isinstance(value, Dict) and VALUE in value:
            return True
        return (
            isinstance(value, str)
            or isinstance(value, (int, float))
            or isinstance(value, bool)
        )

    def handleLiteral(self, id, key, value):
        literal = None
        dt = None
        lang = None
        if isinstance(value, Dict) and VALUE in value:
            lang = value.get(LANGUAGE)
            dt = value.get(TYPE)
            literal = value[VALUE]
        else:
            literal = value

        attrs = {}
        if lang:
            attrs['xml:lang'] = lang
        if dt:
            attrs['rdf:datatype'] = self.resolve(dt)

        self.handleAnnotation(id, key, attrs, value)

        if key == 'rdf:Description':  # TODO: hack
            # TODO: actually:
            # throw new Error('Regular lists of literals are not representable in RDF/XML.')
            self.builder.openElement(key)
            self.builder.addElement('rdf:value', attrs, literal)
            self.builder.closeElement()
        else:
            self.builder.addElement(key, attrs, literal)

    def handleRef(self, key, node):
        id = self.expand(node[ID])

        if isinstance(id, Dict):
            self.builder.openElement(key)
            self.handleQuotedTriple(id)
            self.builder.closeElement()
        else:
            if key == 'rdf:Description':  # TODO: hack
                self.builder.addElement(key, {'rdf:about': id})
            else:
                attrs = {'rdf:resource': id}
                self.handleAnnotation(id, key, attrs, node)

                self.builder.addElement(key, attrs)

    def handleReverses(self, revs):
        # TODO: RDF/XML has no @reverse syntax; flatten input prior to serialization!
        # self.builder.writeln('<!-- @reverse:')
        # for link in revs:
        #    self.builder.writeln(f"<reverse-"{link}">")
        #    for part in revs[link]:
        #        self.handleContents(part, True)
        #    self.builder.writeln(f"</reverse-{link}>")
        # self.builder.writeln('-->')
        pass

    def handleAnnotation(self, s: Optional[str], p: str, arc_attrs: Dict, node: Dict):
        if ANNOTATION not in node:
            return

        annot = node[ANNOTATION]
        if annot:
            notannot: Dict = dict(node)
            del notannot[ANNOTATION]
            triplenode: Dict[str, object] = {ID: s, p: notannot}
            qid = make_qid(self, triplenode)

            if self.use_arc_ids:
                arc_attrs['rdf:ID'] = qid

            self._deferreds.append((annot, triplenode, qid))

    def handleQuotedTriple(self, triplenode, annot: Optional[Dict] = None):
        qid = make_qid(self, triplenode)
        self.builder.openElement('rdf:Statement', {'rdf:ID': qid})
        self.builder.addElement('rdf:subject', {'rdf:resource': triplenode[ID]})
        for k in triplenode:
            if k != ID:
                self.builder.addElement(
                    'rdf:predicate', {'rdf:resource': self.resolve(k)}
                )
                self.handleContents({'rdf:object': triplenode[k]})
                break

        if annot:
            self.handleContents(annot)

        self.builder.closeElement()

        return qid


class XMLWriter:
    indent: str
    def __init__(self, outstream, indent=0):
        self.outstream = outstream
        if isinstance(indent, int):
            self.indent = ' ' * indent
        elif isinstance(indent, str):
            self.indent = indent
        else:
            self.indent = ''
        self.stack = []

    def addElement(
        self,
        tag: str,
        attrs: Optional[Dict[str, str]] = None,
        literal: Optional[str] = None
    ):
        self.iwrite(f"<{tag}")
        self._add_attrs(attrs, tag)
        if literal is not None:
            self.write('>')
            self.write(xmlescape(literal))
            self.write(f"</{tag}>\n")
        else:
            self.write('/>\n')

    def openElement(self, tag: str, attrs: Optional[Dict[str, str]] = None):
        self.iwrite(f"<{tag}")
        self._add_attrs(attrs, tag)
        self.write('>\n')
        self.stack.append(tag)

    def _add_attrs(self, attrs: Optional[Dict[str, str]], tag: str):
        if attrs is None:
            return
        first = True
        for name in attrs.keys():
            entquoted = xmlescape(attrs[name]).replace('"', '&quot;')
            attrval = f' {name}="{entquoted}"'
            if first:
                self.write(attrval) #, 0)
            else:
                self.write('\n')
                padd = ''
                for i in range(len(tag) + 1):
                    padd += ' '
                self.iwrite(f"{padd}{attrval}")

            first = False

    def closeElement(
        self,
    ):
        tag = self.stack.pop()
        self.iwrite(f"</{tag}>\n")

    def iwrite(self, s: str):
        if self.indent:
            for i in range(len(self.stack)):
                self.write(self.indent)
        self.write(s)

    def write(self, s: str):
        self.outstream.write(s)


def xmlescape(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;')


def _nonspecial(node: Dict[str, object]) -> bool:
    return any(key for key in node if not key.startswith('@'))


def make_qid(ctx, triplenode: Dict[str, object]) -> str:
    s: Optional[str] = None
    p: Optional[str] = None
    o: Optional[object] = None
    for k, v in triplenode.items():
        if k == ID:
            s = cast(str, v)
        else:
            p, o = k, v
            assert isinstance(o, Dict)
            o = dict(o)
            if ID in o:
                o[ID] = ctx.resolve(o[ID])
            if TYPE in o:
                o[TYPE] = ctx.resolve(o[TYPE])
    if s is None:
        s = ctx.bnodes.make_bnode_id()

    orepr: str
    if isinstance(o, str):
        orepr = o
    elif isinstance(o, Dict):
        if ID in o:
            orepr = o[ID]
        else:
            orepr = o[VALUE] + ' '
            lang: Optional[str] = o.get(LANGUAGE)
            dt: Optional[str] = o.get(TYPE)
            if lang is not None:
                orepr += lang
            elif dt is not None and dt != XSD_STRING:
                orepr += dt

    triplerepr = f"{s} {p} {orepr}"

    if ctx.triple_id_form == '_':
        return ctx.bnodes.make_bnode_id(triplerepr)
    elif ctx.triple_id_form is not None:
        import hashlib
        hashhex = hashlib.new(
            ctx.triple_id_form, triplerepr.encode('utf-8')
        ).hexdigest()
        return f"triple-{hashhex}"
    else:
        return f"triple:{urlescape(triplerepr)}"


def urlescape(s: str) -> str:
    # FIXME: from common ...
    from urllib.parse import quote_plus
    return quote_plus(s)


if __name__ == '__main__':
    import json
    import sys

    data = json.load(sys.stdin)
    serialize(data, sys.stdout)
