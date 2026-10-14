package trld.nq;

import java.util.Map;

import trld.platform.Input;
import trld.platform.Output;

import trld.jsonld.Rdf;
import static trld.jsonld.Cmd.loadJson;

public class serialize {

    public static void main(String[] args) {
        for (String arg : args) {
            var inp = new Input(arg);
            var data = Parser.parse(inp);
            var dataset = Rdf.toRdfDataset(data);
            var out = new Output(System.out);
            Serializer.serialize(dataset, out);
        }
    }
}
