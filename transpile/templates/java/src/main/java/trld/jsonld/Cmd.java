package trld.jsonld;

import java.util.*;

public class Cmd {
    public static void main(String[] args) {
        boolean nextIsContext = false;
        Object contextData = null;
        int configs = 0;
        for (String src : args) {
            if (src.equals("-c")) {
                nextIsContext = true;
                configs++;
                continue;
            }
            if (nextIsContext) {
                contextData = Common.loadJson(src);
                nextIsContext = false;
                configs++;
                continue;
            }
            if (args.length - configs > 1)
                System.err.println("// File: " + src);
            Object source = Common.loadJson(src);
            try {
                Object result = Expansion.expand(source, src);
                if (contextData != null) {
                    result = Compaction.compact(contextData, result, src);
                }
                System.out.println(Common.dumpJson(result, true));
            } catch (StackOverflowError e) {
                System.err.println("// ERROR: " + e.getClass());
            } catch (Exception e) {
                if (args.length > 1) {
                    System.err.println("// ERROR: " + e);
                    e.printStackTrace(System.err);
                }
                else throw e;
            }
        }
    }
}
