from typing import NamedTuple, Optional, Union, Dict, List


#from ..jsonld.base import ID, TYPE, GRAPH, LIST, REVERSE, VOCAB, CONTEXT
ID: str = '@id'
TYPE: str = '@type'
GRAPH: str = '@graph'
LIST: str = '@list'
REVERSE: str = '@reverse'
VOCAB: str = '@vocab'
CONTEXT: str = '@context'


class TargetMap(NamedTuple):
    target: Union[str, Dict[str, object]]
    target_map: Dict
    #base_map: Dict


class RuleFrom(NamedTuple):
    property: Optional[str]
    property_from: Optional[str]
    value_from: Optional[str]
    match: Optional[Dict[str, str]]

    # NOTE: same as _asdict which isn't handled by transpile
    def repr(self) -> Dict:
        return {
            'property': self.property,
            'property_from': self.property_from,
            'value_from': self.value_from,
            'match': self.match
        }


def as_array(o) -> List:
  if not isinstance(o, List):
    return [] if o is None else [o]
  return o
