"""
# RDF Dataset Canonicalization

Implements the W3C RDF Canonicalization algorithm version 1.0 (RDFC-1.0).
See: <https://www.w3.org/TR/rdf-canon/>.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, Iterable, List, NamedTuple, Optional, Set, Tuple, cast

from .jsonld.rdf import RdfDataset, RdfGraph, RdfLiteral, RdfObject, RdfTriple
from .nq.serializer import repr_quad
from .platform.common import hash_hexdigest, permutations


def canonicalize(input_ds: RdfDataset) -> RdfDataset:
    c14n_state = CanonicalizationState()
    c14n_state.canonicalize(input_ds)
    mapper = c14n_state.get_mapper()

    canon_ds = RdfDataset()

    for name, graph in input_ds:
        canon_graph: RdfGraph
        if name is not None:
            canon_name = mapper.remap_id(name)
            canon_graph = RdfGraph()
            canon_ds.add(canon_name, canon_graph)
        else:
            canon_graph = canon_ds.default_graph

        for triple in graph:
            canon_graph.add(
                RdfTriple(
                    mapper.remap_id(triple.subject),
                    mapper.remap_id(triple.predicate),
                    mapper.remap(triple.object),
                )
            )

    return canon_ds


class CanonicalizationState:
    blank_node_to_quads_map: Dict[str, List[Quad]]
    hash_to_blank_nodes_map: Dict[str, List[str]]
    canonical_issuer: BNodeIdentifierIssuer
    hash_algorithm: str

    def __init__(self, hash_algorithm='sha256'):
        self.blank_node_to_quads_map = {}
        self.hash_to_blank_nodes_map = {}
        self.canonical_issuer = BNodeIdentifierIssuer()
        self.hash_algorithm = hash_algorithm

    def canonicalize(self, input_ds: RdfDataset) -> None:
        # 1) Create the canonicalization state.
        # If the input dataset is an N-Quads document,
        # parse that document into a dataset in the canonicalized dataset,
        # retaining any blank node identifiers used within that document in the input blank node identifier map;
        # otherwise arbitrary identifiers are assigned for each blank node.

        # 2) For every quad Q in input dataset:
        for name, graph in input_ds:
            for triple in graph:
                q = Quad(triple.subject, triple.predicate, triple.object, name)

                # 2.1) For each blank node that is a component of Q, add a reference to Q from the map entry for the blank node identifier identifier in the blank node to quads map, creating a new entry if necessary, using the identifier for the blank node found in the input blank node identifier map.
                self._add_component_ref(q.s, q)
                self._add_component_ref(q.p, q)
                self._add_component_ref(q.o, q)
                self._add_component_ref(q.g, q)

        # 3) For each key n in the blank node to quads map:
        for n in self.blank_node_to_quads_map.keys():
            # 3.1) Create a hash, hf(n), for n according to the Hash First Degree Quads algorithm.
            hf_n = self.hash_first_degree_quads(n)
            # 3.2) Append n to the value associated to hf(n) in hash to blank nodes map, creating a new entry if necessary.
            if hf_n not in self.hash_to_blank_nodes_map:
                self.hash_to_blank_nodes_map[hf_n] = []
            self.hash_to_blank_nodes_map[hf_n].append(n)

        # 4) For each hash to identifier list map entry in hash to blank nodes map, code point ordered by hash:
        for hash in sorted(self.hash_to_blank_nodes_map.keys()):
            id_list = self.hash_to_blank_nodes_map[hash]
            # 4.1) If identifier list has more than one entry, continue to the next mapping.
            if len(id_list) > 1:
                continue
            # 4.2) Use the Issue Identifier algorithm, passing canonical issuer and the single blank node identifier, identifier in identifier list to issue a canonical replacement identifier for identifier.
            self.canonical_issuer.issue_identifier(id_list[0])
            # 4.3) Remove the map entry for hash from the hash to blank nodes map.
            del self.hash_to_blank_nodes_map[hash]

        # 5) For each hash to identifier list map entry in hash to blank nodes map, code point ordered by hash:
        for hash, id_list in self.hash_to_blank_nodes_map.items():
            # 5.1) Create hash path list where each item will be a result of running the Hash N-Degree Quads algorithm.
            hash_path_list: List[Tuple[BNodeIdentifierIssuer, str]] = []
            # 5.2) For each blank node identifier n in identifier list:
            for n in id_list:
                # 5.2.1) If a canonical identifier has already been issued for n, continue to the next blank node identifier.
                if n in self.canonical_issuer.issued_identifiers_map:
                    continue
                # 5.2.2) Create temporary issuer, an identifier issuer initialized with the prefix b.
                temp_issuer = BNodeIdentifierIssuer("b")
                # 5.2.3) Use the Issue Identifier algorithm, passing temporary issuer and n, to issue a new temporary blank node identifier bn to n.
                bn = temp_issuer.issue_identifier(n)
                # 5.2.4) Run the Hash N-Degree Quads algorithm, passing the canonicalization state, n for identifier, and temporary issuer, appending the result to the hash path list.
                hash_path_list.append(self.hash_n_degree_quads(n, temp_issuer))
            # 5.3) For each result in the hash path list, code point ordered by the hash in result:
            hash_path_list.sort(key=lambda item: cast(str, cast(Tuple, item)[1]))
            for result_issuer, result_hash in hash_path_list:
                # 5.3.1) For each blank node identifier, existing identifier, that was issued a temporary identifier by identifier issuer in result, issue a canonical identifier, in the same order, using the Issue Identifier algorithm, passing canonical issuer and existing identifier.
                for existing_id in result_issuer.issued_identifiers_map.keys():
                    self.canonical_issuer.issue_identifier(existing_id)

        # 6) Add the issued identifiers map from the canonical issuer to the canonicalized dataset.

        # 7) Return the serialized canonical form of the canonicalized dataset.
        # Upon request, alternatively (or additionally) return the canonicalized dataset itself,
        # which includes the input blank node identifier map, and issued identifiers map from the canonical issuer.

    def _add_component_ref(self, component: Optional[RdfObject], q: Quad) -> None:
        if isinstance(component, str):
            bnode_id = _get_bnode_id(component)
            if bnode_id is not None:
                if bnode_id not in self.blank_node_to_quads_map:
                    self.blank_node_to_quads_map[bnode_id] = []
                self.blank_node_to_quads_map[bnode_id].append(q)

    def get_mapper(self) -> CanonicalIdMapper:
        return CanonicalIdMapper(self.canonical_issuer.issued_identifiers_map)

    def make_hash(self, data: str) -> str:
        return hash_hexdigest(self.hash_algorithm, data)

    def hash_first_degree_quads(self, ref_blank_node_id: str) -> str:
        # 1. Initialize nquads to an empty list. It will be used to store quads in canonical n-quads form.
        nquads: List[str] = []
        # 2. Get the list of quads quads from the map entry for reference blank node identifier in the blank node to quads map.
        quads = self.blank_node_to_quads_map[ref_blank_node_id]
        # 3. For each quad quad in quads:
        for quad in quads:
            # 3.1 Serialize the quad in canonical n-quads form with the following special rule:
            nquad = _to_special_quad(quad, ref_blank_node_id)
            nquads.append(nquad)
        # 4. Sort nquads in Unicode code point order.
        nquads.sort()
        # 5. Return the hash that results from passing the sorted and concatenated nquads through the hash algorithm.
        return self.make_hash(''.join(nquads))

    def hash_related_blank_node(
        self, related: str, quad: Quad, issuer: BNodeIdentifierIssuer, pos: str
    ) -> str:
        # 1. Initialize a string input to the value of position.
        input_chunks = [pos]
        # 2. If position is not g, append <, the value of the predicate in quad, and > to input.
        if pos != 'g':
            input_chunks.append(f"<{quad.p}>")
        # 3. If there is a canonical identifier for related, or an identifier issued by issuer, append the string _:, followed by that identifier (using the canonical identifier if present, otherwise the one issued by issuer) to input.
        identifier: Optional[str] = self.canonical_issuer.issued_identifiers_map.get(
            related, issuer.issued_identifiers_map.get(related)
        )
        if identifier is not None:
            input_chunks.append(f"_:{identifier}")
        # 4. Otherwise, append the result of the Hash First Degree Quads algorithm, passing related to input.
        else:
            input_chunks.append(self.hash_first_degree_quads(related))
        # 5. Return the hash that results from passing input through the hash algorithm.
        return self.make_hash(''.join(input_chunks))

    def hash_n_degree_quads(
        self, identifier: str, issuer: BNodeIdentifierIssuer
    ) -> Tuple[BNodeIdentifierIssuer, str]:
        # 1. Create a new map Hn for relating hashes to related blank nodes.
        hn: Dict[str, List[str]] = {}
        # 2. Get a reference, quads, to the list of quads from the map entry for identifier in the blank node to quads map.
        quads: List[Quad] = self.blank_node_to_quads_map.get(identifier, [])
        # 3. For each quad in quads:
        for quad in quads:
            # 3.1 For each component in quad, where component is the subject, object, or graph name, and it is a blank node that is not identified by identifier:
            self._add_related_bnode_hash_to_hn(
                quad.s, identifier, quad, issuer, hn, 's'
            )
            if isinstance(quad.o, str):
                self._add_related_bnode_hash_to_hn(
                    quad.o, identifier, quad, issuer, hn, 'o'
                )
            if isinstance(quad.g, str):
                self._add_related_bnode_hash_to_hn(
                    quad.g, identifier, quad, issuer, hn, 'g'
                )

        # 4. Create an empty string, data to hash.
        data: List[str] = []
        # 5. For each related hash to blank node list mapping in Hn, code point ordered by related hash:
        for related_hash in cast(Iterable[str], sorted(hn.keys())):
            bnode_list = hn[related_hash]
            # 5.1 Append the related hash to the data to hash.
            data.append(related_hash)
            # 5.2 Create a string chosen path.
            chosen_path = ""
            # 5.3 Create an unset chosen issuer variable.
            chosen_issuer: Optional[BNodeIdentifierIssuer] = None
            # 5.4 For each permutation p of blank node list:
            for p in cast(List[List[str]], permutations(bnode_list)):
                skip_to_next_p = False

                # 5.4.1 Create a copy of issuer, issuer copy.
                issuer_copy = issuer.copy()
                # 5.4.2 Create a string path.
                path_chunks: List[str] = []
                # 5.4.3 Create a recursion list, to store blank node identifiers that must be recursively processed by this algorithm.
                recursion_list: List[str] = []
                # 5.4.4 For each related in p:
                for related in p:
                    # 5.4.4.1 If a canonical identifier has been issued for related by canonical issuer, append the string _:, followed by the canonical identifier for related, to path.
                    canonical_identifier: Optional[str] = (
                        self.canonical_issuer.issued_identifiers_map.get(related)
                    )
                    if canonical_identifier is not None:
                        path_chunks.append(f"_:{canonical_identifier}")
                    # 5.4.4.2 Otherwise:
                    else:
                        # 5.4.4.2.1 If issuer copy has not issued an identifier for related, append related to recursion list.
                        if related not in issuer_copy.issued_identifiers_map:
                            recursion_list.append(related)
                        # 5.4.4.2.2 Use the Issue Identifier algorithm, passing issuer copy and the related, and append the string _:, followed by the result, to path.
                        path_chunks.append(f"_:{issuer_copy.issue_identifier(related)}")
                    # 5.4.4.3 If chosen path is not empty and the length of path is greater than or equal to the length of chosen path and path is greater than chosen path when considering code point order, then skip to the next permutation p.
                    path = ''.join(path_chunks)
                    if (
                        chosen_path
                        and len(path) >= len(chosen_path)
                        and path > chosen_path
                    ):
                        skip_to_next_p = True
                        break

                if skip_to_next_p:
                    continue

                # 5.4.5 For each related in recursion list:
                for related in recursion_list:
                    # 5.4.5.1 Set result to the result of recursively executing the Hash N-Degree Quads algorithm, passing the canonicalization state, related for identifier, and issuer copy for path identifier issuer.
                    result_issuer, result = self.hash_n_degree_quads(
                        related, issuer_copy
                    )
                    # 5.4.5.2 Use the Issue Identifier algorithm, passing issuer copy and related; append the string _:, followed by the result, to path.
                    path_chunks.append(f"_:{issuer_copy.issue_identifier(related)}")
                    # 5.4.5.3 Append <, the hash in result, and > to path.
                    path_chunks.append(f"<{result}>")
                    # 5.4.5.4 Set issuer copy to the identifier issuer in result.
                    issuer_copy = result_issuer
                    # 5.4.5.5 If chosen path is not empty and the length of path is greater than or equal to the length of chosen path and path is greater than chosen path when considering code point order, then skip to the next p.
                    path = ''.join(path_chunks)
                    if (
                        chosen_path
                        and len(path) >= len(chosen_path)
                        and path > chosen_path
                    ):
                        skip_to_next_p = True
                        break

                if skip_to_next_p:
                    continue

                path = ''.join(path_chunks)
                # 5.4.6 If chosen path is empty or path is less than chosen path when considering code point order, set chosen path to path and chosen issuer to issuer copy.
                if not chosen_path or path < chosen_path:
                    chosen_path = path
                    chosen_issuer = issuer_copy

            # 5.5 Append chosen path to data to hash.
            data.append(chosen_path)
            # 5.6 Replace issuer, by reference, with chosen issuer.
            assert chosen_issuer is not None  # TODO: if?!
            issuer = chosen_issuer

        # 6. Return issuer and the hash that results from passing data to hash through the hash algorithm.
        return issuer, self.make_hash(''.join(data))

    def _add_related_bnode_hash_to_hn(
        self,
        ref: str,
        identifier: str,
        quad: Quad,
        issuer: BNodeIdentifierIssuer,
        hn: Dict[str, List[str]],
        pos: str,
    ) -> None:
        bnode_id = _get_bnode_id(ref)
        if bnode_id is not None and bnode_id != identifier:
            # 3.1.1 Set hash to the result of the Hash Related Blank Node algorithm, passing the blank node identifier for component as related, quad, issuer, and position as either s, o, or g based on whether component is a subject, object, graph name, respectively.
            hash: str = self.hash_related_blank_node(bnode_id, quad, issuer, pos)
            # 3.1.2 Add a mapping of hash to the blank node identifier for component to Hn, adding an entry as necessary.
            if hash not in hn:
                hn[hash] = []
            hn[hash].append(bnode_id)


class BNodeIdentifierIssuer:
    identifier_prefix: str
    identifier_counter: int
    issued_identifiers_map: OrderedDict[str, str]

    def __init__(self, identifier_prefix: str = "c14n"):
        self.identifier_prefix = identifier_prefix
        self.identifier_counter = 0
        self.issued_identifiers_map = OrderedDict()

    def copy(self) -> BNodeIdentifierIssuer:
        copy = BNodeIdentifierIssuer(self.identifier_prefix)
        copy.identifier_counter = self.identifier_counter
        copy.issued_identifiers_map = self.issued_identifiers_map.copy()
        return copy

    # 4.5
    def issue_identifier(self, existing_id: str) -> str:
        assert not existing_id.startswith('_:')
        # assert len(existing_id) > 1

        if existing_id in self.issued_identifiers_map:
            return self.issued_identifiers_map[existing_id]

        issued_id = f"{self.identifier_prefix}{self.identifier_counter}"
        self.issued_identifiers_map[existing_id] = issued_id
        self.identifier_counter += 1

        return issued_id


class Quad(NamedTuple):
    s: str
    p: str
    o: RdfObject
    g: Optional[str]

    def __str__(self) -> str:
        triple = RdfTriple(self.s, self.p, self.o)
        return repr_quad(triple, self.g) + '\n'


class CanonicalIdMapper:

    _canonical_id_map: OrderedDict[str, str]

    def __init__(self, canonical_id_map: OrderedDict[str, str]):
        self._canonical_id_map = canonical_id_map

    def remap_id(self, term_id: str) -> str:
        bnode_id = _get_bnode_id(term_id)
        if bnode_id is None or bnode_id not in self._canonical_id_map:
            return term_id

        return f"_:{self._canonical_id_map[bnode_id]}"

    def remap(self, node: RdfObject) -> RdfObject:
        if isinstance(node, str):
            return self.remap_id(node)
        return node


def _get_bnode_id(component: str) -> Optional[str]:
    return component[2:] if component.startswith("_:") else None


def _to_special_quad(quad: Quad, ref_blank_node_id: str) -> str:
    s = cast(str, _remap_quad_component(quad.s, ref_blank_node_id))
    p = cast(str, _remap_quad_component(quad.p, ref_blank_node_id))
    o = _remap_quad_component(quad.o, ref_blank_node_id)
    g = quad.g
    if quad.g is not None:
        g = cast(str, _remap_quad_component(quad.g, ref_blank_node_id))

    return str(Quad(s, p, o, g))


def _remap_quad_component(component: RdfObject, ref_blank_node_id: str) -> RdfObject:
    # 3.1.1 If any component in quad is an blank node, then serialize it using a special identifier as follows:
    if isinstance(component, str):
        bnode_id = _get_bnode_id(component)
        if bnode_id is not None:
            return "a" if bnode_id == ref_blank_node_id else "z"
    return component
    # 3.1.1.1 If the blank node's existing blank node identifier matches the reference blank node identifier then use the blank node identifier a, otherwise, use the blank node identifier z.


if __name__ == '__main__':
    import json
    import sys

    from .jsonld.rdf import to_jsonld, to_rdf_dataset

    data = json.load(sys.stdin)
    ds = to_rdf_dataset(data)

    out_ds = canonicalize(ds)

    result = to_jsonld(out_ds)
    print(json.dumps(result, indent=2))
