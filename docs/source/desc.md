# Desc

Descriptions on Surfaces, about Subjects in a Space, viewed in Context.

Create a Space, a Surface and add descriptions to that.
```python
>>> from trld.extras.desc import Space

>>> space = Space(base='https://example.org/')
>>> surface = space.new_surface()
>>> surface.parse_data("""
... prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
... prefix dc: <http://purl.org/dc/terms/>
... prefix : <http://purl.org/ontology/bibo/>
...
... <x> a :Book ;
...   dc:title "X"@en ;
...   :isbn "00-0000-0000-00-0" ;
...   dc:creator <y> ;
...   :contributorList ( <y> [ rdfs:label "Z" ]) ;
...   :issuer [ a dc:Agent ; rdfs:label "O" ] .
...
... <y> a :Agent ;
...     rdfs:label "Y" .
... """, "ttl")
>>>

>>> surface.id is None
True
>>>
```

Inspect the Description of `<x>`:
```python
>>> x = surface.get('x')
>>> x.id
Link('https://example.org/x')
>>>

>>> x.surface is surface
True

>>> x.get_type()
Description(id=Link('http://purl.org/ontology/bibo/Book'))
>>>

>>> x.get('http://purl.org/dc/terms/title')
Literal(value='X', datatype=Description(id=Link('http://www.w3.org/1999/02/22-rdf-syntax-ns#langString')), language='en')
>>>
```

## Use Contexts for Compact Term Access

The surface context is automatically used when accessing descriptions.
```python
>>> x.get('dc:title')
Literal(value='X', datatype=Description(id=Link('http://www.w3.org/1999/02/22-rdf-syntax-ns#langString')), language='en')

>>> x.get('isbn').value
'00-0000-0000-00-0'

>>> x.get('isbn').datatype
Description(id=Link('http://www.w3.org/2001/XMLSchema#string'))
>>> x.get('isbn').datatype.id
Link('http://www.w3.org/2001/XMLSchema#string')

>>> x.get('contributorList')
OrderedList(items=2)
>>> for item in x.get('contributorList'):
...     print(item.id, item.get('rdfs:label'))
https://example.org/y Y
_:b0 Z
>>>
```

## Modifying a Surface

Add a title. Due to the set nature of triples in RDF, it will only be added
once.
```python
>>> x.add('dc:title', {"@value": "Other"})
True
>>> x.add('dc:title', {"@value": "Other"})
False
>>>
```

Simple access behaves like compact JSON-LD in that it gets one or more objects
depending on container:
```python
>>> isinstance(x.get('dc:title'), set)
True

>>> for title in sorted(x.get('dc:title')):
...     print(repr(title))
Literal(value='Other', datatype=Description(id=Link('http://www.w3.org/2001/XMLSchema#string')), language=None)
Literal(value='X', datatype=Description(id=Link('http://www.w3.org/1999/02/22-rdf-syntax-ns#langString')), language='en')

>>> x.remove('dc:title', {"@value": "Other"})
1

>>> x.remove('dc:title', {"@value": "Other"})
0

>>> x.get('dc:title')
Literal(value='X', datatype=Description(id=Link('http://www.w3.org/1999/02/22-rdf-syntax-ns#langString')), language='en')

>>> x.surface.update_context({'title': {"@id": "dc:title", "@container": "@set"}})
>>> x.get('title')
{Literal(value='X', datatype=Description(id=Link('http://www.w3.org/1999/02/22-rdf-syntax-ns#langString')), language='en')}
>>>
>>> x.surface.update_context({'title': None})
>>> x.get('title') is None
True
>>>
```
Serialize any description or the entire surface:
```python
>>> print(x.surface.serialize())  # doctest: +ELLIPSIS
base <https://example.org/>
prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
prefix dc: <http://purl.org/dc/terms/>
prefix : <http://purl.org/ontology/bibo/>
...
<https://example.org/x> a :Book ;
  dc:creator <https://example.org/y> ;
  dc:title "X"@en ;
  :contributorList ( <https://example.org/y> [ rdfs:label "Z" ] )  ;
  :isbn "00-0000-0000-00-0" ;
  :issuer [ a dc:Agent ;
      rdfs:label "O" ] .
...
<https://example.org/y> a :Agent ;
  rdfs:label "Y" .
...
>>>
```

## A Space is a Union of Surfaces

And a Subject (from Space) is the union of its descriptions on surfaces.
```python
>>> xs = space.find('https://example.org/x')
>>> xs
Subject(id=Link('https://example.org/x'))

>>> xs is x.find()
True

>>> x in xs.get_descriptions()
True
>>>
```
As seen above, you can manipulate the context in a Surface. This actually edits
the data.

In a Space, you only *view* the descriptions (as subjects), and you *use*
contexts for convenient access within this view. This *does not* affect any
data.

Use a surface context for convenient data access:
```python
>>> space.context.use(surface)
>>>
```
Spaces provide a more advanced view of the data. This includes bare attribute
access to terms (for platforms that support such "expando" dynamism).
```python
>>> xs.isbn.value
'00-0000-0000-00-0'
>>>
```
Push a context term to ease access further:
```python
>>> xs.title is None
True
>>> space.context['title'] = 'dc:title'
>>> xs.title == x.get('dc:title')
True
>>>

>>> xs.creator is None
True
>>> space.context['@vocab'] = 'dc'
>>> xs.creator
Subject(id=Link('https://example.org/y'))
>>>
```
Subjects have full indexing for incoming (reverse) links:
```python
>>> creator = xs.get('dc:creator')
>>> xs in creator.get_subjects('dc:creator')
True
>>>
```

