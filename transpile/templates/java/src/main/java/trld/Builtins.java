package trld;

import java.util.*;
import java.util.function.Function;

public class Builtins {

    public static List sorted(Iterable items) {
        return sorted(items, false);
    }

    public static List sorted(Iterable items, boolean reversed) {
        return sorted(items, null, false);
    }

    public static List sorted(Iterable items, Function<Object, Comparable> getKey, boolean reversed) {
        List result;
        if (items instanceof Collection) {
          result = new ArrayList(((Collection) items).size());
          result.addAll((Collection) items);
        } else {
          result = new ArrayList();
          items.forEach(result::add);
        }
        Comparator cmp = makeComparator(getKey, reversed);
        try {
          Collections.sort(result, cmp);
        } catch (ClassCastException e) {
          return result;
        }
        return result;
    }

    public static Comparator makeComparator(Function<Object, Comparable> getKey, boolean reversed) {
        Comparator cmp = null;
        if (getKey != null) {
            cmp = (a, b) -> getKey.apply(a).compareTo(getKey.apply(b));
        }
        if (reversed) {
            cmp = Collections.reverseOrder(cmp);
        }
        return cmp;
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
