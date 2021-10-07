'use(strict)'

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
