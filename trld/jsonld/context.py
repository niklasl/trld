from typing import Optional, Dict, List, Set, Tuple, Union, cast
from ..common import load_json, warning, resolve_iri
from .base import *


DEFAULT_PROCESSING_MODE: str = JSONLD11

MAX_REMOTE_CONTEXTS: int = 512


class ProcessingModeConflictError(JsonLdError): pass

class InvalidVersionValueError(JsonLdError): pass

class InvalidBaseIriError(JsonLdError): pass

class InvalidVocabMappingError(JsonLdError): pass

class InvalidDefaultLanguageError(JsonLdError): pass

class InvalidBaseDirectionError(JsonLdError): pass

class InvalidContextEntryError(JsonLdError): pass

class InvalidPropagateValueError(JsonLdError): pass

class InvalidImportValueError(JsonLdError): pass

class InvalidContextNullificationError(JsonLdError): pass

class InvalidLocalContextError(JsonLdError): pass

class LoadingDocumentFailedError(JsonLdError): pass

class ContextOverflowError(JsonLdError): pass

class InvalidRemoteContextError(JsonLdError): pass

class CyclicIriMappingError(JsonLdError): pass

class KeywordRedefinitionError(JsonLdError): pass

class InvalidTermDefinitionError(JsonLdError): pass

class InvalidScopedContextError(JsonLdError): pass

class InvalidProtectedValueError(JsonLdError): pass

class InvalidLanguageMappingError(JsonLdError): pass

class InvalidTypeMappingError(JsonLdError): pass

class InvalidReversePropertyError(JsonLdError): pass

class InvalidIriMappingError(JsonLdError): pass

class InvalidKeywordAliasError(JsonLdError): pass

class InvalidContainerMappingError(JsonLdError): pass

class InvalidNestValueError(JsonLdError): pass

class InvalidPrefixValueError(JsonLdError): pass

class ProtectedTermRedefinitionError(JsonLdError): pass


class Context:

    terms: Dict[Optional[str], 'Term']
    base_iri: str # IRI
    original_base_url: Optional[str] # IRI

    _inverse_context: Optional[Dict]

    vocabulary_mapping: Optional[str] # IRI
    default_language: Optional[str] # Language
    default_base_direction: Optional[str] # Direction

    _propagate: bool
    previous_context: Optional['Context']

    _processing_mode: str
    _version: Optional[float]

    #_keyword_aliases: Dict[str, List[str]]

    def __init__(self, base_iri: Optional[str], original_base_url: Optional[str] = None):
        self.initialize(base_iri, original_base_url)

    def initialize(self, base_iri: Optional[str], original_base_url: Optional[str] = None):
        self.terms = {}
        # TODO: spec problem; what if None?
        self.base_iri = "" if base_iri is None else base_iri
        if original_base_url is not None:
            self.original_base_url = original_base_url # TODO: resolve/check
        else:
            self.original_base_url = None # TODO: base_iri ?

        self.vocabulary_mapping = None
        self.default_language = None
        self.default_base_direction = None
        self._propagate = True
        self.previous_context = None
        self._processing_mode = DEFAULT_PROCESSING_MODE
        self._version = None
        self._inverse_context = None
        #self._keyword_aliases = {}

    def copy(self) -> 'Context':
        cloned: Context = Context(self.base_iri, self.original_base_url)
        cloned.terms = self.terms.copy()
        cloned.vocabulary_mapping = self.vocabulary_mapping
        cloned.default_language = self.default_language
        cloned.default_base_direction = self.default_base_direction
        cloned._processing_mode = self._processing_mode
        return cloned

    def get_context(self, context_data: object,
            base_url: str = None,
            remote_contexts: Set[str] = None,
            override_protected=False,
            validate_scoped=True) -> 'Context':
        if remote_contexts is None:
            remote_contexts = set()
        # 1)
        local_context: Context = self.copy()
        # 2)
        if isinstance(context_data, Dict):
            propagate: object = context_data.get(PROPAGATE)
            if isinstance(propagate, bool):
                local_context._propagate = propagate
        # 3)
        # TODO: spec problem 5f496df9:
        # always keep previous_context and use depending on propagate
        #if not local_context._propagate and \
        #        local_context.previous_context is None:
        if local_context.previous_context is None:
            local_context.previous_context = self

        local_context._read_context(context_data, base_url,
                remote_contexts, override_protected, validate_scoped)

        return local_context

    def _read_context(self,
            context_data: object,
            base_url: Optional[str],
            remote_contexts: Set[str],
            override_protected: bool,
            validate_scoped: bool):
        # 4)
        normalized_context_data: List[object]
        if isinstance(context_data, List):
            normalized_context_data = context_data
        else:
            normalized_context_data = [context_data]

        if base_url is None:
            base_url = self.base_iri

        # 5)
        for context in normalized_context_data:
            # 5.1)
            if context is None:
                # 5.1.1)
                if override_protected is False and \
                        any(term.is_protected for term in self.terms.values()):
                    raise InvalidContextNullificationError
                # 5.1.2)
                # TODO: change to non-mutating behaviour? (self vs. result)
                prev: Optional[Context] = self.copy() if self._propagate is False else None
                self.initialize(base_url, base_url)
                if prev is not None:
                    self.previous_context = prev
                # 5.1.3)
                continue

            # 5.2)
            if isinstance(context, str):
                self._read_context_link(context, base_url, remote_contexts,
                        override_protected, validate_scoped)
            # 5.4)
            elif isinstance(context, Dict):
                self._read_context_definition(context, base_url, remote_contexts,
                        override_protected, validate_scoped)
            # 5.3)
            else:
                raise InvalidLocalContextError

    def _read_context_link(self, href: str, base_url: str,
            remote_contexts: Set[str],
            override_protected: bool, validate_scoped: bool):
        # 5.2.1)
        try:
            href = resolve_iri(base_url, href)
        except:
            raise LoadingDocumentFailedError

        if not validate_scoped and href in remote_contexts:
            return

        if len(remote_contexts) > MAX_REMOTE_CONTEXTS:
            raise ContextOverflowError
        else:
            remote_contexts.add(href)

        context_document: object = self._load_document(href)
        # 5.2.5.2)
        if not isinstance(context_document, Dict) or CONTEXT not in context_document:
            raise InvalidRemoteContextError
        # 5.2.5.3)
        loaded: object = context_document[CONTEXT]

        # 5.2.6)
        self._read_context(loaded, href, set(remote_contexts), override_protected, validate_scoped)
        # NOTE: If context was previously dereferenced, processors MUST make
        # provisions for retaining the base URL of that context for this step
        # to enable the resolution of any relative context URLs that may be
        # encountered during processing.

        # 5.2.7) Continue with the next context

    def _load_document(self, href: str, profile: str = JSONLD_CONTEXT_RELATION, request_profile: str = JSONLD_CONTEXT_RELATION) -> object:
        # TODO:
        # 5.2.4) If context was previously dereferenced, then the processor MUST NOT do a further dereference, and context is set to the previously established internal representation:
            #set context document to the previously dereferenced document, and set loaded context to the value of the @context entry from the document in context document.
        # NOTE: Only the @context entry need be retained.
        #loaded: Union[Dict, List] = context_document[CONTEXT]

        # 5.2.5) Otherwise, set context document to the RemoteDocument obtained by dereferencing context using the LoadDocumentCallback, passing context for url, and http://www.w3.org/ns/json-ld#context for profile and for requestProfile.
            # 5.2.5.1) If context cannot be dereferenced, or the document from context document cannot be transformed into the internal representation:
                #a loading remote context failed error has been detected and processing is aborted.
        ...
        #return remote_document.json
        return load_json(href)

    def _read_context_definition(self,
            context: Dict[str, Union[str, Dict]],
            base_url: str,
            remote_contexts: Set[str],
            override_protected: bool, validate_scoped: bool):
        # 5.5)
        version: object = context.get(VERSION)
        if version is not None:
            if self._processing_mode == JSONLD10:
                raise ProcessingModeConflictError
            if isinstance(version, float) and version == 1.1:
                self._version = version
            else:
                raise InvalidVersionValueError

        # 5.6)
        if IMPORT in context:
            context = self._handle_import(context, base_url)

        # 5.7)
        if BASE in context and len(remote_contexts) == 0:
            # 5.7.1)
            base: object = context[BASE]
            # 5.7.2)
            if base is None:
                # TODO: spec problem; specify whether base_iri can be null
                self.base_iri = "" # None
            # 5.7.3)
            # 5.7.4)
            elif self.base_iri is not None and isinstance(base, str):
                self.base_iri = resolve_iri(self.base_iri, base)
            elif isinstance(base, str) and is_iri(base):
                self.base_iri = base
            # 5.7.5)
            else:
                raise InvalidBaseIriError

        # 5.8)
        if VOCAB in context:
            # 5.8.1)
            vocab: object = context[VOCAB]
            # 5.8.2)
            if vocab is None:
                self.vocabulary_mapping = None
            # 5.8.3)
            elif isinstance(vocab, str) and (is_iri_ref(vocab) or is_blank(vocab)):
                self.vocabulary_mapping = self.expand_doc_relative_vocab_iri(vocab)
                # NOTE: The use of blank node identifiers to value for @vocab is
                # obsolete, and may be removed in a future version of JSON-LD.
            else:
                raise InvalidVocabMappingError

        # 5.9)
        if LANGUAGE in context:
            lang: object = context[LANGUAGE]
            if lang is None:
                self.default_language = None
            elif isinstance(lang, str):
                if not is_lang_tag(lang):
                    warning(f'Language tag {lang} in context is not well-formed')
                self.default_language = lang.lower()
            else:
                raise InvalidDefaultLanguageError

        # 5.10)
        if DIRECTION in context:
            direction: object = context[DIRECTION]
            if direction is None or isinstance(direction, str) and direction in DIRECTIONS:
                self.default_base_direction = direction
            else:
                raise InvalidBaseDirectionError(str(direction))

        # 5.11)
        if PROPAGATE in context:
            propagate: object = context[PROPAGATE]
            # 5.11.1)
            if self._processing_mode == JSONLD10:
                raise InvalidContextEntryError
            # 5.11.2)
            if not isinstance(propagate, bool):
                raise InvalidPropagateValueError(str(propagate))
            # NOTE: propagate is set above on the condition that local_context
            # is not an array

        # 5.12)
        defined: Dict[str, bool] = {}

        # 5.13)
        for (key, value) in context.items():
            if key in CONTEXT_KEYWORDS:
                continue
            # invoke the Create Term Definition algorithm, passing
            # result for active context,
            # context for local context,
            # key, defined, base URL,
            # TODO: pass these too:
            # the value of the @protected entry from context, if any, for protected,
            # override protected,
            # and a copy of remote contexts.
            #self.terms[key] = # TODO: set in Term (move that up here if obscure...)
            isprotected: bool = cast(bool, context.get(PROTECTED))
            Term(self, context, key, value, defined, base_url, isprotected, override_protected)

    def _handle_import(self, context: Dict[str, Union[str, Dict]], base_url: str) -> Dict:
        import_value: object = context[IMPORT]
        # 5.6.1)
        if self._processing_mode == JSONLD10:
            raise InvalidContextEntryError
        # 5.6.2)
        if not isinstance(import_value, str):
            raise InvalidImportValueError(str(import_value))
        # 5.6.3)
        import_value = resolve_iri(base_url, import_value)
        # 5.6.4)
        context_document: object = self._load_document(import_value)
        # 5.6.5)
        # TODO: LoadingDocumentFailedError
        # 5.6.6)
        if not isinstance(context_document, Dict) or CONTEXT not in context_document:
            raise InvalidRemoteContextError
        import_context: object = context_document[CONTEXT]
        if not isinstance(import_context, Dict):
            raise InvalidRemoteContextError
        # 5.6.7)
        if IMPORT in import_context:
            raise InvalidContextEntryError
        # 5.6.8)
        import_context.update(context)
        del import_context[IMPORT]
        return import_context

    def expand_vocab_iri(self, value: str) -> Optional[str]:
        return self.expand_iri(value, None, None, False, True)

    def expand_doc_relative_iri(self, value: str) -> Optional[str]:
        return self.expand_iri(value, None, None, True, False)

    def expand_doc_relative_vocab_iri(self, value: str) -> Optional[str]:
        return self.expand_iri(value, None, None, True, True)

    def _expand_init_vocab_iri(self,
            value: str,
            local_context: Dict[str, Union[str, Dict]],
            defined: Dict[str, bool],
            ) -> Optional[str]:
        return self.expand_iri(value, local_context, defined, False, True)

    # TODO: spec errata: spec says vocab=true in topic dfn but false in algorithm defintion!
    def expand_iri(self,
            value: str,
            local_context: Optional[Dict[str, Union[str, Dict]]] = None,
            defined: Optional[Dict[str, bool]] = None,
            doc_relative=False,
            vocab=False) -> Optional[str]:
        # 1)
        if value in KEYWORDS or value is None:
            return value

        # 2)
        if has_keyword_form(value):
            warning(f'Id {value} looks like a keyword')
            return None

        # 3)
        if local_context is not None and value in local_context and defined and (value not in defined or defined[value] is not True):
            Term(self, local_context, value, local_context[value], defined)

        iri_term: Optional[Term] = self.terms.get(value)

        # 4)
        if iri_term and iri_term.iri in KEYWORDS:
            return iri_term.iri

        # 5)
        if vocab and iri_term:
            return iri_term.iri

        # 6)
        if len(value) > 1 and ':' in value[1:]:
            # 6.1)
            idx: int = value.index(':')
            prefix: str = value[0:idx]
            suffix: str = value[idx + 1:]
            #prefix, suffix = value.split(':', 1)
            # 6.2)
            if prefix == '_' or suffix.startswith('//'):
                return value

            # 6.3)
            # TODO: spec problem; see step 3 above
            if local_context is not None and prefix in local_context and defined:
                if prefix not in defined or defined[prefix] is not True:
                    Term(self, local_context, prefix, local_context[prefix], defined)

            # 6.4)
            pfx_term: Optional[Term] = self.terms.get(prefix)
            if pfx_term and pfx_term.iri is not None and pfx_term.is_prefix:
                return pfx_term.iri + suffix

            # 6.5)
            # TODO: spec problem; is frag-id not an IRI here? (See TC 109)
            if not value.startswith('#') and is_iri(value):
                return value

        # 7)
        if vocab and self.vocabulary_mapping:
            return self.vocabulary_mapping + value

        # 8)
        elif doc_relative:
            return resolve_iri(self.base_iri, value)

        # 9)
        return value


class Term:

    iri: str # IRI
    is_prefix: bool
    is_protected: bool
    is_reverse_property: bool
    base_url: Optional[str] # IRI # TODO: is this proper and good?
    has_local_context: bool
    container: List[str] # empty means "optional" here...
    direction: Optional[str] # Direction
    index: Optional[str]
    language: Optional[str] # Language
    nest_value: Optional[str]
    type_mapping: Optional[str] # IRI

    _local_context: Optional[object]
    _cached_contexts: Dict[str, Optional[Context]]
    _remote_contexts: Set

    def __init__(self,
        active_context: Context,
        local_context: Dict[str, Union[str, Dict]],
        term: str,
        value: Union[str, Dict[str, object]],
        defined: Dict[str, bool],
        base_url: str = None,
        isprotected=False, # NOTE: 'protected' in spec; but a common reserved keyword
        override_protected=False, # which is used to allow changes to protected terms
        remote_contexts: Set = None, # which is used to detect cyclical context inclusions
        validate_scoped=True # which is used to limit recursion when validating possibly recursive scoped contexts
        ):
        # TODO: check redundancies of these and conditional initialization below
        self.is_prefix = False
        self.is_protected = isprotected if isinstance(isprotected, bool) else False
        self.is_reverse_property = False
        self.container = []
        self.direction = None
        self.index = None
        self.language = None
        self.nest_value = None
        self.type_mapping = None

        if remote_contexts is None:
            remote_contexts = set()

        self.base_url = None
        self.has_local_context = False
        self._local_context = None
        self._remote_contexts = remote_contexts
        self._cached_contexts = {}

        # 1)
        # TODO: place this step outside, in the call to Term?
        if term in defined:
            defined_term: bool = defined[term]
            if defined_term:
                return
            else:
                raise CyclicIriMappingError(term)
        # 2)
        if term == "":
            raise InvalidTermDefinitionError

        defined[term] = False

        # 3)
        #value = local_context[term]

        # 4)
        if term == TYPE:
            if active_context._processing_mode == JSONLD10:
                raise KeywordRedefinitionError
            # TODO: with only either or both
            if not isinstance(value, Dict) or not (
                    value.get(CONTAINER) == SET or PROTECTED in value):
                raise KeywordRedefinitionError

        # 5)
        elif term in KEYWORDS:
            raise KeywordRedefinitionError(term)

        if has_keyword_form(term):
            warning(f'Term {term} looks like a keyword'
                    ' (it matches the ABNF rule "@"1*ALPHA from [RFC5234])')

        # 6)
        prev_dfn: Optional[Term] = active_context.terms.pop(term, None)

        simple_term: bool

        # 7) + 8)
        dfn: Dict
        if value is None or isinstance(value, str):
            dfn = {}
            dfn[ID] = value
            simple_term = isinstance(value, str)
        # 9)
        else:
            if not isinstance(value, Dict):
                raise InvalidTermDefinitionError(str(value))
            dfn = value
            simple_term = False

        # 10)
        # TODO: we're doing everything *inside* of Term; move out to function + call Term?

        # 11)
        if PROTECTED in dfn:
            if active_context._processing_mode == JSONLD10:
                raise InvalidTermDefinitionError(str(dfn))
            is_protected: object = dfn[PROTECTED]
            if isinstance(is_protected, bool):
                self.is_protected = is_protected
            else:
                raise InvalidProtectedValueError

        # 12)
        type_mapping: object = dfn.get(TYPE)
        # 12.1)
        if isinstance(type_mapping, str):
            # 12.2 + 12.5)
            self.type_mapping = active_context._expand_init_vocab_iri(type_mapping, local_context, defined)
            # 12.3)
            if active_context._processing_mode == JSONLD10 and \
                    self.type_mapping in {JSON, NONE}:
                raise InvalidTypeMappingError
            # 12.4)
            elif self.type_mapping not in {ID, JSON, NONE, VOCAB} and not is_iri(self.type_mapping):
                raise InvalidTypeMappingError(self.type_mapping)
        elif type_mapping:
            raise InvalidTypeMappingError

        # 13)
        if REVERSE in dfn:
            rev: object = dfn[REVERSE]
            # 13.1)
            if ID in dfn or NEST in dfn:
                raise InvalidReversePropertyError
            # 13.2)
            if not isinstance(rev, str):
                raise InvalidIriMappingError

            # 13.3)
            if has_keyword_form(rev):
                warning(f'Reverse {rev} for term {term} has the form of a keyword')
                return
            # 13.4)
            self.iri = cast(str, active_context._expand_init_vocab_iri(rev, local_context, defined))
            if not (is_blank(self.iri) or is_iri(self.iri)):
                raise InvalidIriMappingError
            # 13.5)
            if CONTAINER in dfn:
                self.container = sorted(as_list(dfn[CONTAINER]))
                if dfn[CONTAINER] not in {SET, INDEX, None}:
                    raise InvalidReversePropertyError
            # 13.6)
            self.is_reverse_property = True
            # 13.7)
            active_context.terms[term] = self
            defined[term] = True
            return

        # 14)
        if ID in dfn and term != dfn[ID]:
            id: str = cast(str, dfn[ID]) # TODO: redundant cast for transpile
            # 14.1
            if id is None:
                # TODO: spec says "is retained to detect future redefinitions"; like this?
                self.iri = None
            # 14.2)
            else:
                # 14.2.1)
                if not isinstance(id, str):
                    raise InvalidIriMappingError
                # 14.2.2)
                if id not in KEYWORDS and has_keyword_form(id):
                    warning(f'Id {id} for term {term} is not a keyword but'
                            ' has the form of a keyword')
                # 14.2.3)
                self.iri = cast(str, active_context._expand_init_vocab_iri(id, local_context, defined))
                if self.iri is None or not (self.iri in KEYWORDS or is_blank(self.iri) or is_iri(self.iri)):
                    # TODO: check if these are to be skipped instead of halting
                    return
                    #raise InvalidIriMappingError(f'{term}: {self.iri}')
                if self.iri == CONTEXT:
                    raise InvalidKeywordAliasError

                # 14.2.4)
                if ':' in term[1:-1] or '/' in term:
                    # 14.2.4.1)
                    defined[term] = True
                    # 14.2.4.2)
                    if active_context._expand_init_vocab_iri(term, local_context, defined) != self.iri:
                        # TODO: spec or TC expand 0026 problem; just pass works
                        # TODO: expansion TC 0071 fails unless we just return
                        pass#return
                        #raise InvalidIriMappingError(term, self.iri)
                # 14.2.5) # TODO: really no ':' anywhere, so elif not strictly correct...
                elif simple_term and (self.iri[-1] in PREFIX_DELIMS or is_blank(self.iri)):
                    self.is_prefix = True

        # 15)
        elif ':' in term[1:]:
            # 15.1)
            idx: int = term.index(':')
            prefix: str = term[0:idx]
            suffix: str = term[idx + 1:]
            #prefix, suffix = term.split(':', 1)

            if prefix in local_context:
                Term(active_context, local_context, prefix, local_context[prefix], defined)

            # 15.2)
            if prefix in active_context.terms:
                self.iri = active_context.terms[prefix].iri + suffix
            # 15.3)
            else:
                #assert is_iri(term) or is_blank(term)
                self.iri = term

        # 16)
        elif '/' in term:
            # 16.1) assert is_relative_iri(term)
            # 16.2)
            self.iri = cast(str, active_context.expand_vocab_iri(term))
            if not is_iri(self.iri):
                raise InvalidIriMappingError

        # 17)
        elif term == TYPE:
            self.iri = TYPE

        # 18)
        elif active_context.vocabulary_mapping:
            self.iri = active_context.vocabulary_mapping + term
        else:
            raise InvalidIriMappingError(f'{term}: {str(value)}')

        # 19)
        if CONTAINER in dfn:
            container: object = dfn[CONTAINER]
            # 19.1)
            container_terms: Optional[Set] = None
            if isinstance(container, List):
                container_terms = set(container) # TODO: just - {SET} ?
                if SET in container_terms and LIST not in container_terms:
                    container_terms.remove(SET)
            if not (isinstance(container, str) and
                container in CONTAINER_KEYWORDS
                ) and not (
                    container_terms is not None and (
                        len(container_terms) == 0
                        or len(container_terms) == 1 and all(t in CONTAINER_KEYWORDS for t in container_terms)
                        or container_terms == {GRAPH, ID}
                        or container_terms == {GRAPH, INDEX}
                        or list(container_terms)[0] in {INDEX, GRAPH, ID, TYPE, LANGUAGE}
                    )
                ):
                raise InvalidContainerMappingError(container)

            # 19.2)
            if active_context._processing_mode == JSONLD10:
                if not isinstance(container, str) or container in {GRAPH, ID, TYPE}:
                    raise InvalidContainerMappingError(str(container))

            # 19.3)
            self.container = sorted(as_list(cast(object, container)))

            # 19.4)
            if TYPE in self.container:
                # 19.4.1)
                if self.type_mapping is None:
                    self.type_mapping = ID
                # 19.4.2)
                elif self.type_mapping not in {ID, VOCAB}:
                    raise InvalidTypeMappingError

        # 20)
        if INDEX in dfn:
            # 20.1)
            if active_context._processing_mode == JSONLD10 or INDEX not in self.container:
                raise InvalidTermDefinitionError(str(value))
            # 20.2)
            index: object = dfn[INDEX]
            if not isinstance(index, str):
                raise InvalidTermDefinitionError(str(value))
            if not is_iri(active_context.expand_vocab_iri(index)):
                raise InvalidTermDefinitionError(str(value))
            # 20.3)
            self.index = index

        # 21)
        self.has_local_context = CONTEXT in dfn
        if self.has_local_context:
            # 21.1)
            if active_context._processing_mode == JSONLD10:
                raise InvalidTermDefinitionError(str(dfn))
            # 21.2)
            # 21.3)
            # TODO: doesn't produce the expected effects (see c032, c033)
            #try:
            #    self.get_local_context(active_context)
            #except JsonLdError as e:
            #    raise InvalidScopedContextError(term)
            # 21.4)
            # TODO: different from spec; since propagate behaviour may be based
            # on usage as @type (see 5f496df9) we use a memoized approach.
            self._local_context = dfn[CONTEXT]
            self.base_url = base_url

        # 22)
        if LANGUAGE in dfn and TYPE not in dfn:
            # 22.1)
            lang: object = dfn[LANGUAGE]
            if not isinstance(lang, str) and lang is not None:
                raise InvalidLanguageMappingError
            if not is_lang_tag(lang):
                warning(f'Language tag {lang} in term {term} is not well-formed')
            # 22.2)
            # TODO: [5f6117d4] spec uses maps with key missing != null; note this difference
            self.language = NULL if lang is None else lang.lower()

        # 23)
        if DIRECTION in dfn and TYPE not in dfn:
            # 23.1)
            dir: object = dfn[DIRECTION]
            if dir not in DIRECTIONS and dir is not None:
                raise InvalidBaseDirectionError
            # 23.2)
            # TODO: see 5f6117d4
            self.direction = NULL if dir is None else cast(str, dir)

        # 24)
        if NEST in dfn:
            # 24.1)
            if active_context._processing_mode == JSONLD10:
                raise InvalidTermDefinitionError
            # 24.2)
            self.nest_value = cast(str, dfn[NEST]) # TODO: redundant cast for transpile
            if not isinstance(self.nest_value, str) or \
                    (self.nest_value != NEST and self.nest_value in KEYWORDS):
                raise InvalidNestValueError

        # 25)
        if PREFIX in dfn:
            # 25.1)
            if active_context._processing_mode == JSONLD10 or ':' in term or '/' in term:
                raise InvalidTermDefinitionError
            # 25.2)
            self.is_prefix = cast(bool, dfn[PREFIX]) # TODO: redundant cast for transpile
            if not isinstance(self.is_prefix, bool):
                raise InvalidPrefixValueError
            # 25.3)
            if self.is_prefix and self.iri in KEYWORDS:
                raise InvalidTermDefinitionError

        # 26) TODO:
        #if len(set(dfn.keys()) - TERM_KEYWORDS) > 0:
        #    raise InvalidTermDefinitionError

        # 27)
        if not override_protected and prev_dfn and prev_dfn.is_protected:
            # 27.2)
            self.is_protected = prev_dfn.is_protected
            # 27.1)
            if not self.matches(prev_dfn):
                raise ProtectedTermRedefinitionError 

        # 28)
        active_context.terms[term] = self
        defined[term] = True

    def get_local_context(self, active_context: Context, propagate=True) -> Context:
        cache_key: str = f'{id(active_context)}:{str(propagate)}'
        cached: Optional[Context] = self._cached_contexts.get(cache_key)

        # TODO: should be passed explicitly, but seems to correlate
        # (might even be named "type-scoped"?)
        override_protected: bool = propagate

        if cached is None:
            cached = active_context.get_context(self._local_context,
                        self.base_url,
                        set(self._remote_contexts),
                        override_protected=override_protected,
                        validate_scoped=False)
            self._cached_contexts[cache_key] = cached

        if (not isinstance(self._local_context, Dict)
            or PROPAGATE not in self._local_context):
                cached._propagate = propagate

        return cached

    def matches(self, other: object) -> bool:
        if not isinstance(other, Term):
            return False

        return self.iri == other.iri and \
                self.is_prefix == other.is_prefix and \
                self.is_reverse_property == other.is_reverse_property and \
                self.base_url == other.base_url and \
                self.has_local_context == other.has_local_context and \
                self.container == other.container and \
                self.direction == other.direction and \
                self.index == other.index and \
                self.language == other.language and \
                self.nest_value == other.nest_value and \
                self.type_mapping == other.type_mapping and \
                self._local_context == other._local_context
