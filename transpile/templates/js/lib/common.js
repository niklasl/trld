'use(strict)'

import fs from 'fs'
import url from 'url'
import http from 'http'
import https from 'https'

export function sorted(array, key = null, reversed = false) {
  let copy = array.concat([]);
  if (key) {
    let cmp = reversed ? (a, b) => key(b) - key(a) : (a, b) => key(a) - key(b)
    copy.sort(cmp)
  } else {
    copy.sort()
    if (reversed) copy.reverse()
  }
  return copy
}

export class Input {

  constructor(source = null) {
    if (typeof source === 'string') {
      this._source = open(removeFileProtocol(source)) // TODO
    } else {
      this._source = (source != null || sys.stdin) // TODO
    }
  }

  getHeader(header) {
    throw new Error("NotImplemented")
  }

  read() {
    return this._source.read() // TODO
  }

  *[Symbol.iterator]() { // LINE: 29
    return this._source // LINE: 30
  }

  *[Symbol.iterator]() { // LINE: 32
    return GeneratorExp(elt=Name(id='c', ctx=Load()), generators=[comprehension(target=Name(id='l', ctx=Store()), iter=Attribute(value=Name(id='self', ctx=Load()), attr='_source', ctx=Load()), ifs=[], is_async=0), comprehension(target=Name(id='c', ctx=Store()), iter=Name(id='l', ctx=Load()), ifs=[], is_async=0)]) // LINE: 33
  }

  close() { // LINE: 35
    if (this._source !== sys.stdin) { // LINE: 36
      this._source.close() // LINE: 37
    }
  }
}

export class Output {

  constructor(dest = null) {
    if (dest === true) {
      dest = new StringIO() // TODO
    }
    this._dest = (dest != null || sys.stdout) // TODO
  }

  write(s) {
    console.log(s) // TODO
  }

  writeln(s) {
    console.log(s) // TODO
  }

  getValue() { // LINE: 58
    // this._dest instanceof StringIO
    return this._dest.join('\n') // TODO
  }

  close() { // LINE: 62
    if (this._dest !== sys.stdout) { // TODO
      this._dest.close() // TODO
    }
  }
}

var sourceLocator = null // LINE: 70

export function setSourceLocator(locator) {
  sourceLocator = locator
}

export function removeFileProtocol(ref) {
  if (ref.startsWith("file://")) {
    return ref.substring(7)
  } else if (ref.startsWith("file:")) {
    return ref.substring(5)
  }
  return ref
}

export function loadJson(uri) {
  let buf
  // TODO: async/await (decorate to let transpile know which calls are I/O)
  uri = (sourceLocator != null ? sourceLocator(uri) : uri)
  if (uri.startsWith('https')) {
    // TODO
  } else if (uri.startsWith('http')) {
    // TODO
  } else {
    let location = uri
    if (uri.startsWith('file://')) {
      location = uri.substring(7)
    }
    buf = fs.readFileSync(location)
  }
  return JSON.parse(buf.toString('utf-8'))
}

export function dumpJson(o, pretty=false) {
  return JSON.stringify(o, null, pretty ? 2 : undefined);
}

export function dumpCanonicalJson(o) {
  // TODO: sort keys, no space after ',' nor ':'
  return JSON.stringify(o, null);
}

export function resolveIri(base, relative) {
  return url.resolve(base, relative)
}

export function warning(msg) {
  console.warn(msg)
}
