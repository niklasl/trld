import fs from 'fs'
import { loadJson, dumpJson } from '../common.js'
import { expand } from '../jsonld/expansion.js'
import { compact } from '../jsonld/compaction.js'
import { makeTargetMap } from './mapmaker.js'
import { mapTo } from './mapper.js'

export default async function main () {
  let args = process.argv.slice(2)

  let vocabFile = args.length > 0 ? args[0] : null
  let target = args.length > 1 ? args[1] : null
  let inFile = args.length > 2 ? args[2] : null

  let vocab = loadJson(vocabFile)
  vocab = expand(vocab, vocabFile)

  if (typeof target === 'string' && fs.existsSync(target)) {
      target = loadJson(target)
  }

  let targetMap = makeTargetMap(vocab, target)
  let data = targetMap

  if (inFile != null) {
      let indata = loadJson(inFile)
      indata = expand(indata, inFile)

      let outdata = mapTo(targetMap, indata)
      outdata = compact(target, outdata)
      data = outdata
  }

  console.log(dumpJson(data, true))
}

if (typeof require !== 'undefined' && require.main === module) main()
