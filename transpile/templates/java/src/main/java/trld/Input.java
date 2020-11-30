package trld;

import java.util.*;
import java.io.*;

public class Input {

    public Iterator<String> characters() {
        Reader r;
        try {
            r = new BufferedReader(new InputStreamReader(System.in, "utf-8"));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        return new Iterator<String>() {
            Character c = null;
            public boolean hasNext() {
                try {
                    c = Character.valueOf((char) r.read());
                } catch (IOException e) {
                    throw new RuntimeException(e);
                }
                return c != null;
            }
            public String next() {
                return c.toString();
            }
        };
    }
}
