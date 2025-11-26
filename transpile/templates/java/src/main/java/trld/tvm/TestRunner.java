package trld.tvm;

import java.lang.reflect.Method;

public class TestRunner {

  public static void main(String[] args) throws Exception {
    for (Method method : Test.class.getMethods()) {
        String name = method.getName();
        if (name.matches("test[A-Z].*")) {
            System.out.print("TVM test " + name + ": ");
            method.invoke(null);
        }
    }
  }

}
