'use(strict)'
import url from 'url'

export function jsonDecode(s) {
  return JSON.parse(s)
}

export function jsonEncode(o, pretty=false) {
  return JSON.stringify(o, null, pretty ? 2 : undefined);
}

export function jsonEncodeCanonical(o) {
  // TODO: sort keys, no space after ',' nor ':'
  return JSON.stringify(o, null);
}

export function resolveIri(base, relative) {
  return url.resolve(base, relative)
}

export function warning(msg) {
  console.warn(msg)
}
