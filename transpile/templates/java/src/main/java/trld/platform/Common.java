package trld.platform;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import java.util.function.IntPredicate;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.SerializationFeature;

public class Common {

    private static final ObjectMapper mapper = new ObjectMapper();

    public static String hashHexdigest(String algorithm, String data) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(data.getBytes(StandardCharsets.UTF_8));
            StringBuilder hexString = new StringBuilder(2 * hash.length);
            for (int i = 0; i < hash.length; i++) {
                String hex = Integer.toHexString(0xff & hash[i]);
                if(hex.length() == 1) {
                    hexString.append('0');
                }
                hexString.append(hex);
            }
            return hexString.toString();
        } catch (NoSuchAlgorithmException e) {
            return null;
        }
    }

    public static <A> List<List<A>> permutations(List<A> original) {
      List<List<A>> permutations = new ArrayList<>();
      if (original.isEmpty()) {
        permutations.add(original);
      } else {
          A first = original.get(0);
          List<List<A>> subpermutations = permutations(original.subList(1, original.size()));
          for (List<A> smaller : subpermutations) {
              for (int i=0; i <= smaller.size(); ++i) {
                  List<A> mut = new ArrayList<>(smaller);
                  mut.add(i, first);
                  permutations.add(mut);
              }
          }
      }
      return permutations;
    }

    public static String escapeCodepoints(String s, IntPredicate needsEsc) {
        StringBuilder sb = new  StringBuilder();
        s.codePoints().forEach(cp -> {
            if (needsEsc.test(cp)) {
                sb.append(String.format("\\u%04X", cp));
            } else {
                sb.appendCodePoint(cp);
            }
        });
        return sb.toString();
    }


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
