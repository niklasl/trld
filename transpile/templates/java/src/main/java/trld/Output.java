package trld;

import java.util.*;
import java.io.*;

public class Output {

    private PrintStream out = System.out;

    public void write(String s) {
        out.print(s);
    }

    public void writeln(String s) {
        out.println(s);
    }
}
