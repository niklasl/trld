package trld.platform;

import java.util.*;
import java.io.*;

import trld.Mimetypes;

public class Input implements Closeable {

    public /*@Nullable*/ String documentUrl;
    public /*@Nullable*/ String contentType;
    public /*@Nullable*/ String profile;
    public /*@Nullable*/ String contextUrl;

    private BufferedReader reader;
    private InputStream ins;

    public Input() {
        this(System.in);
    }

    public Input(String path) {
        this(path, null);
    }

    public Input(String path, /*@Nullable*/ Map<String, String> headers) {
        this(sneakyFileInputStream(path));
        this.documentUrl = path;
        this.contentType = Mimetypes.guessMimeType(path);
    }

    public Input(InputStream ins) {
        this.ins = ins;
        try {
            reader = new BufferedReader(new InputStreamReader(ins, "utf-8"));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    public String read() {
        StringBuilder sb = new StringBuilder();
        Iterator<String> liter = iterlines();
        while (liter.hasNext()) {
            sb.append(liter.next()).append("\n");
        }
        return sb.toString();
    }

    public Iterable<String> lines() {
        return () -> iterlines();
    }

    Iterator<String> iterlines() {
        return new Iterator<String>() {
            String line = null;
            public boolean hasNext() {
                try {
                    line = reader.readLine();
                } catch (IOException e) {
                    throw new RuntimeException(e);
                }
                return line != null;
            }
            public String next() {
                return line;
            }
        };
    }

    public Iterable<String> characters() {
        return () -> iterchars();
    }

    Iterator<String> iterchars() {
        return new Iterator<String>() {
            Character c = null;
            public boolean hasNext() {
                try {
                    int i = reader.read();
                    c = i != -1 ? Character.valueOf((char) i) : null;
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

    public void close() {
        if (ins == System.in) {
            return;
        }
        try {
            reader.close();
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    static FileInputStream sneakyFileInputStream(String path) {
        try {
            path = removeFileProtocol(path);
            return new FileInputStream(path);
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    private static String removeFileProtocol(String ref) {
        if (ref.startsWith("file:///")) {
            return ref.substring(7);
        } else if (ref.startsWith("file:/")) {
            return ref.substring(5);
        }
        return ref;
    }

    public Object loadJson() {
        return Common.jsonDecode(read());
    }
}
