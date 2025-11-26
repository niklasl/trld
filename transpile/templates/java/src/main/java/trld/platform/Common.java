package trld.platform;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.SerializationFeature;

public class Common {

    private static final ObjectMapper mapper = new ObjectMapper();

    public static String resolveIri(String base, String relative) {
        try {
            return new URI(base).resolve(relative).toString();
        } catch (URISyntaxException e) {
            return null;
        }
    }

    public static String uuid4() {
        return java.util.UUID.randomUUID().toString();
    }

    public static void warning(String msg) {
        System.err.println(msg);
    }

    public static Object jsonDecode(String s) {
        try {
            return mapper.readValue(s, Object.class);
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    public static String jsonEncode(Object o) {
        return jsonEncode(o, false);
    }

    public static String jsonEncode(Object o, boolean pretty) {
        return jsonEncode(o, pretty, false);
    }

    public static String jsonEncode(Object o, boolean pretty, boolean sortKeys) {
        ObjectWriter writer = pretty ? mapper.writerWithDefaultPrettyPrinter() : mapper.writer();
        if (sortKeys) {
            writer = writer.with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
        }
        try {
            return writer.writeValueAsString(o);
        } catch (IOException e) {
            return null;
        }
    }

    public static String jsonEncodeCanonical(Object o) {
        return jsonEncode(o, false, true); // TODO: ensure no space for separators
    }

}
