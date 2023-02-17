import { parse, ParserError } from './parser.js'
import { dumpJson } from '../platform/common.js'
import { Input } from '../platform/io.js'

export default async function main () {
  let args = process.argv.slice(2)
  let debug = true
  let inp = new Input(args[0])
  try {
    let result = await parse(inp)
    console.log(dumpJson(result, true))
  } catch (e) {
    if (e instanceof ParserError) {
      console.error(debug ? e : e.toString())
      process.exit(1)
    } else {
      throw e
    }
  }
}

if (typeof require !== 'undefined' && require.main === module) main()
