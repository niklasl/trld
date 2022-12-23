from typing import Dict, List, Optional, cast

from ..rdfterms import RDF as RDFNS

XMLNS = 'http://www.w3.org/XML/1998/namespace'
XMLNSNS = 'http://www.w3.org/2000/xmlns/'

from ..platform.common import json_encode
from ..jsonld.base import (BASE, CONTAINER, CONTEXT, GRAPH, ID, INDEX,
                           LANGUAGE, LIST, REVERSE, SET, TYPE, VALUE, VOCAB)

from ..jsonld.star import ANNOTATION


def serialize(data, outstream):
    ser = RDFXMLSerializer(XMLWriter(outstream, True))
    ser.serialize(data)


class RDFXMLSerializer:
    def __init__(self, builder):
        self.builder = builder

    def serialize(self, data):
        self.context = data[CONTEXT]
        self.builder.openElement('rdf:RDF', self.contextAttrs(self.context))

        nodes = data
        if not isinstance(data, List):
            nodes = data[GRAPH] or data
        if not isinstance(nodes, List):
            nodes = [nodes]

        for node in nodes:
            self.handleNode(node)
        self.builder.closeElement()

    def resolve(self, qname):
        if qname == TYPE:
            return f"{RDFNS}type"

        pfx, cln, lname = qname.partition(':')
        if not lname:
            lname = pfx
            pfx = VOCAB

        return self.context[pfx] + lname

    def contextAttrs(self, context):
        if not isinstance(context, Dict):
            return {}

        attrs = {}

        rdfpfx = None

        for key in context:
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

        if rdfpfx != 'rdf':
            if rdfpfx is not None:
                pass  # TODO: switch to self.prefix...
            # elif rdfns != RDFNS {
            #    raise Error("Cannot handle rdf prefix for non-RDF namespace: .")
            attrs['xmlns:rdf'] = RDFNS

        return attrs

    def handleNode(self, node, kind=None):
        graph = node.get(GRAPH)
        id = node.get(ID)

        types = node.get(TYPE)
        if not types:
            types = []
        if not isinstance(types, List):
            types = [types]

        firstType = types[0] if len(types) > 0 else None
        typeannot = None
        if isinstance(firstType, Dict):
            typeannot = firstType
            firstType = firstType[TYPE]  # TODO: non-std

        # FIXME: nested RDF with about is non-standard!
        # RDF/XML doesn't support named graphs at all!
        tag = firstType if firstType else 'rdf:RDF' if graph else 'rdf:Description'

        if id is not None and isinstance(id, Dict):
            id = self.handleQuotedTriple(id)

        aboutattr = (
            ({'rdf:ID': id[2:]} if id.startswith('_:') else {'rdf:about': id})
            if id is not None
            else {}
        )

        self.builder.openElement(tag, aboutattr)
        if typeannot:
            self.handleAnnotation(typeannot)

        self.handleType(types[1:])

        self.handleContents(node)

        if graph:
            if isinstance(graph, List):
                for it in graph:
                    self.handleNode(it)

        self.handleAnnotation(node)

        revs = node.get(REVERSE)
        if revs:
            self.handleReverses(revs)

        self.builder.closeElement()

    def handleType(self, types):
        for type in types:
            v = type[TYPE] if isinstance(type, Dict) else type
            self.builder.addElement('rdf:type', {'rdf:resource': self.resolve(v)})
            self.handleAnnotation(type)

    def handleContents(self, node, inArray=False):
        if inArray:
            node = {inArray: node}

        for key in node:
            if key.startswith('@'):
                continue

            value = node[key]

            if self.isLiteral(value):
                self.handleLiteral(key, value)
            elif isinstance(value, List):
                for part in value:
                    self.handleContents(part, key)
            elif isinstance(value, Dict):
                if value.get(LIST):
                    self.builder.openElement(key, {'rdf:parseType': "Collection"})
                    for part in value[LIST]:
                        self.handleContents(part, 'rdf:Description')  # TODO: hack
                    self.handleAnnotation(value)
                    self.builder.closeElement()
                elif ID in value:
                    self.handleRef(key, value)
                else:
                    if key:
                        self.builder.openElement(key)
                    self.handleNode(value, 'embedded')
                    if key:
                        self.builder.closeElement()

    def isLiteral(self, value):
        if isinstance(value, Dict) and VALUE in value:
            return True
        return (
            isinstance(value, str)
            or isinstance(value, (int, float))
            or isinstance(value, bool)
        )

    def handleLiteral(self, key, value):
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
            attrs['xml:datatype'] = self.resolve(dt)

        if key == 'rdf:Description':  # TODO: hack
            # TODO: actually:
            # throw new Error('Regular lists of literals are not representable in RDF/XML.')
            self.builder.openElement(key)
            self.builder.addElement('rdf:value', attrs, literal)
            self.builder.closeElement()
        else:
            self.builder.addElement(key, attrs, literal)

        self.handleAnnotation(value)

    def handleRef(self, key, node):
        id = node[ID]

        if isinstance(id, Dict):
            self.builder.openElement(key)
            genid = self.handleQuotedTriple(id)
            self.builder.closeElement()
            id = genid
        else:
            if key == 'rdf:Description':  # TODO: hack
                self.builder.addElement(key, {'rdf:about': id})
            else:
                self.builder.addElement(key, {'rdf:resource': id})

        self.handleAnnotation(node)

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

    def handleAnnotation(self, node):
        # TODO: RDF/XML has no RDF-star annotation support!
        # annot = node[ANNOTATION]
        # if annot: # TODO: defer an rdf:Statement rdf:ID="arc_id"
        #    self.builder.writeln('<!--@annotation:')
        #    self.handleContents(annot)
        #    self.builder.writeln('-->')
        pass

    def handleQuotedTriple(self, idNode):
        genid = f"triple-{urlescape(json_encode(idNode))}"
        self.builder.openElement('rdf:Statement', {'rdf:ID': genid})
        self.builder.addElement('rdf:subject', {'rdf:resource': idNode[ID]})
        for k in idNode:
            if k != ID:
                self.builder.addElement(
                    'rdf:predicate', {'rdf:resource': self.resolve(k)}
                )
                self.handleContents({'rdf:object': idNode[k]})
                break

        self.builder.closeElement()
        return f"_:{genid}"


class XMLWriter:
    def __init__(self, outstream, indent=False):
        self.outstream = outstream
        self.indent = indent
        self.stack = []

    def addElement(self, tag, attrs={}, literal=None):
        self.iwrite(f"<{tag}")
        self.addAttrs(attrs, tag)
        if literal is not None:
            self.write('>')
            self.write(esc(literal))
            self.write(f"</{tag}>\n")
        else:
            self.write('/>\n')

    def openElement(self, tag, attrs={}):
        self.iwrite(f"<{tag}")
        self.addAttrs(attrs, tag)
        self.write('>\n')
        self.stack.append(tag)

    def addAttrs(self, attrs, tag=None):
        first = True
        for name in attrs:
            entquoted = esc(attrs[name]).replace('"', '&quot;')
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

    def iwrite(self, s):
        if self.indent:
            for i in range(len(self.stack)):
                self.write('    ')
        self.write(s)

    def write(self, s):
        self.outstream.write(s)


def urlescape(s):
    return s  # FIXME: from common ...


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;')


if __name__ == '__main__':
    import json
    import sys

    data = json.load(sys.stdin)
    serialize(data, sys.stdout)
