'use(strict)'

import fs from 'fs'
import url from 'url'
import http from 'http'
import https from 'https'
import process from 'process'

export class Input {

  constructor(source = null) {
    if (typeof source === 'string') {
      this._source = fs.createReadStream(removeFileProtocol(source))
    } else {
      this._source = (source != null || process.stdin)
    }
  }

  getHeader(header) {
    throw new Error("NotImplemented")
  }

  read() {
    return this._source.read() // TODO
  }

  async *characters() {
    for await (const chunk of this._source) {
      for (let c of chunk.toString()) {
        yield c
      }
    }
  }

  *[Symbol.iterator]() {
    return this._source
  }

  close() {
    if (this._source !== process.stdin) {
      this._source.close()
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

export function parseJson(s) {
  return JSON.parse(s)
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
