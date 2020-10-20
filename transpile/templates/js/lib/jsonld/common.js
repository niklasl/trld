'use(strict)'

import fs from 'fs'
import url from 'url'
import http from 'http'
import https from 'https'

export function sorted(array) {
  let copy = array.concat([]);
  copy.sort()
  return copy
}

export function loadJson(uri) {
  let buf
  // TODO: async/await (decorate to let transpile know which calls are I/O)
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

export function resolveIri(base, relative) {
  return url.resolve(base, relative)
}

export function warning(msg) {
  console.warn(msg)
}
