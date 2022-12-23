from typing import Dict, List, NamedTuple, Optional
from io import StringIO

from xml.dom import minidom


class XmlReader:
    def get_root(self, source: object) -> 'XmlElement':
        if isinstance(source, str):
            doc = minidom.parseString(source)
        elif isinstance(source, StringIO):
            doc = minidom.parse(source)
        else:
            doc = source
        return XmlElement(self, doc.documentElement)


class XmlAttribute(NamedTuple):
    name: str
    namespaceURI: str
    localName: str
    value: str


class XmlElement:
    namespaceURI: str
    localName: str
    tagName: str

    def __init__(self, reader: XmlReader, elem):
        self._reader = reader
        self._elem = elem
        self.namespaceURI = elem.namespaceURI
        self.localName = elem.localName
        self.tagName = elem.tagName

    def get_attributes(self) -> List[XmlAttribute]:
        attrs =  []
        for i in range(self._elem.attributes.length):
            attr = self._elem.attributes.item(i)
            attrs.append(
                XmlAttribute(attr.name, attr.namespaceURI, attr.localName, attr.value)
            )
        return attrs

    def get_child_elements(self) -> List['XmlElement']:
        return [
            XmlElement(self._reader, elem)
            for elem in self._elem.childNodes
            if elem.nodeType == elem.ELEMENT_NODE
        ]

    def get_text(self):
        return ''.join(part.nodeValue for part in self._elem.childNodes)

    def get_inner_xml(self):
        return ''.join(part.toxml() for part in self._elem.childNodes)
