from typing import Dict, List, Optional, cast

from ..jsonld.base import (BASE, CONTEXT, GRAPH, ID, INDEX,
                           LANGUAGE, LIST, TYPE, VALUE, VOCAB)

from ..jsonld.star import ANNOTATION

from .xmlcompat import XmlAttribute, XmlElement, XmlReader

NodeObject = Dict[str, object]

RDFNS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
XMLNS = 'http://www.w3.org/XML/1998/namespace'
XMLNSNS = 'http://www.w3.org/2000/xmlns/'


class RdfAttrs:
    ns: Dict
    values: Dict
    base: Optional[str]
    lang: Optional[str]
    about: Optional[str]
    rdf_id: Optional[str]
    nodeID: Optional[str]
    resource: Optional[str]
    datatype: Optional[str]
    parseType: Optional[str]

    def __init__(self, attributes: List[XmlAttribute]):
        self.ns = {}
        self.values = {}
        self.base = None
        self.lang = None
        self.about = None
        self.rdf_id = None
        self.nodeID = None
        self.resource = None
        self.datatype = None
        self.parseType = None

        for attr in attributes:
            nsUri = attr.namespaceURI
            lname = attr.localName
            value = attr.value
            if nsUri == XMLNSNS:
                pfx = lname
                if pfx == 'xmlns':
                    pfx = VOCAB
                self.ns[pfx] = value
            elif nsUri == XMLNS:
                if lname == 'lang':
                    self.lang = value
                elif lname == 'base':
                    self.base = value
            elif nsUri == RDFNS:
                if lname == 'about':
                    self.about = value
                elif lname == 'ID':
                    self.rdf_id = '#' + value
                elif lname == 'nodeID':
                    self.nodeID = value
                elif lname == 'resource':
                    self.resource = value
                elif lname == 'datatype':
                    self.datatype = value
                elif lname == 'parseType':
                    self.parseType = value
                else:
                    raise Exception(f'Unknown RDF attribute: {attr.name}="{value}"')
            else:
                self.values[attr.name] = value


def parse(source: object) -> NodeObject:
    reader = XmlReader()
    root: XmlElement = reader.get_root(source)
    context: NodeObject = {}
    graph: List[NodeObject] = []
    result: NodeObject = {CONTEXT: context, GRAPH: graph}
    annots: List[NodeObject] = []
    walk(root, result, None, annots)

    # inline_annotations
    if len(annots) > 0:
        index = {o[ID]: o for o in cast(list, result[GRAPH]) if ID in o}
        for annot in annots:
            desc = index.pop(annot[ID], None)
            if desc is not None:
                annot.update(desc)
                del annot[ID]
        result[GRAPH] = list(index.values())

    return result


def walk(
    elem: XmlElement,
    result: NodeObject,
    node: Optional[NodeObject],
    annots: List[NodeObject],
):
    attrs = RdfAttrs(elem.get_attributes())

    ctx = cast(Dict, result[CONTEXT])
    if attrs.ns:
        # TODO: if node add local context
        ctx.update(attrs.ns)

    if attrs.base:
        ctx[BASE] = attrs.base

    # TODO: if node add local context
    if node is None:
        if attrs.lang:
            ctx[LANGUAGE] = attrs.lang

    childNode = None
    consumed = False

    value: Optional[object] = None
    props: Optional[object] = None

    if elem.namespaceURI == RDFNS and elem.localName == 'RDF':
        childNode = node
    else:
        if node is None:
            node = {}
            cast(List, result[GRAPH]).append(node)
            if elem.namespaceURI != RDFNS or elem.localName != 'Description':
                node[TYPE] = elem.tagName

            if attrs.about is not None:
                node[ID] = attrs.about
            elif attrs.rdf_id is not None:
                node[ID] = attrs.rdf_id
            elif attrs.nodeID:
                node[ID] = '_:' + attrs.nodeID
            childNode = node

            node.update(attrs.values)
        else:
            if attrs.parseType == 'Resource':
                childNode = {}
                value = childNode
            elif attrs.parseType == 'Collection':
                coll: List[object] = []
                value = {LIST: coll}
                result = {CONTEXT: {}, GRAPH: coll}
            elif attrs.parseType == 'Literal':
                xml = elem.get_inner_xml()
                value = {TYPE: 'rdf:XMLLiteral', VALUE: xml}
                consumed = True
            elif attrs.resource:
                value = {ID: attrs.resource}
            elif attrs.nodeID:
                value = {ID: '_:' + attrs.nodeID}
            elif len(elem.get_child_elements()):
                value = []
                result = {CONTEXT: {}, GRAPH: value}
            else:
                value = elem.get_text()
                if attrs.lang:
                    value = {VALUE: value, LANGUAGE: attrs.lang}
                elif attrs.datatype:
                    value = {VALUE: value, TYPE: attrs.datatype}

            if attrs.rdf_id:
                if not isinstance(value, dict):
                    value = {VALUE: value}
                annot: NodeObject = {ID: attrs.rdf_id}
                value[ANNOTATION] = annot
                annots.append(annot)

            props = node.get(elem.tagName)
            if props is None:
                node[elem.tagName] = value
            else:
                if not isinstance(props, List):
                    node[elem.tagName] = props = [props]
                if not isinstance(value, List):
                    props.append(value)
                else:
                    # defer consuming array until it has been filled
                    pass
    if consumed:
        return

    for child in elem.get_child_elements():
        walk(child, result, childNode, annots)

    if isinstance(props, List) and isinstance(value, List):
        props += value


if __name__ == '__main__':
    import sys
    xml = sys.stdin.read()
    result = parse(xml)
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
