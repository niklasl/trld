package trld.jsonld;

import java.util.*;
import java.io.IOException;
import java.net.URL;
import java.net.MalformedURLException;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import com.fasterxml.jackson.jr.ob.JSON;

public class Common {

    public static Object loadJson(String ref) {
        String src = null;

        if (ref.startsWith("http://") || ref.startsWith("https://")) {
            try {
                src = new Scanner(new URL(ref).openStream()).useDelimiter("\\A").next();
            } catch (MalformedURLException e) {
                throw new RuntimeException(e);
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        } else {
            if (ref.startsWith("file:///")) {
                ref = ref.substring(7);
            } else if (ref.startsWith("file:/")) {
                ref = ref.substring(5);
            }
            Path srcpath = Paths.get(ref); // NOTE: Path.of is preferred in Java 11+
            try {
                src = new String(Files.readAllBytes(srcpath), "utf-8");
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        }

        return parseJson(src);
    }

    public static Object parseJson(String s) {
        try {
            return JSON.std.anyFrom(s);
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    public static String dumpJson(Object o) {
        return dumpJson(o, false);
    }

    public static String dumpJson(Object o, boolean pretty) {
        try {
            if (pretty) {
                return JSON.std.with(JSON.Feature.PRETTY_PRINT_OUTPUT).asString(o);
            } else {
                return JSON.std.asString(o);
            }
        } catch (IOException e) {
            return null;
        }
    }

    public static String dumpCanonicalJson(Object o) {
        return dumpJson(o); // FIXME: no space separators, do sort keys
    }

    public static String resolveIri(String base, String relative) {
        try {
            return new URI(base).resolve(relative).toString();
        } catch (URISyntaxException e) {
            return null;
        }
    }

    public static void warning(String msg) {
        System.err.println(msg);
    }

    public static List sorted(Collection items) {
        List result = new ArrayList(items.size());
        result.addAll(items);
        Collections.sort(result);
        return result;
    }

    public static Map mapOf(Object ...pairs) {
        Map result = new HashMap<>(pairs.length);
        int i = 0;
        Object key = null;
        for (Object item : pairs) {
            if (++i % 2 == 0) {
                result.put(key, item);
            } else {
                key = item;
            }
        }
        return result;
    }
}
