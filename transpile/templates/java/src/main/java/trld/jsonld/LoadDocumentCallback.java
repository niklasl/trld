package trld.jsonld;

//import javax.annotation.Nullable;
import java.util.*;
import java.util.function.Function;


public abstract class LoadDocumentCallback implements Function<String, RemoteDocument> {
  public RemoteDocument apply(String url) {
    return this.apply(url, null);
  }
  public abstract RemoteDocument apply(String url, /*@Nullable*/ LoadDocumentOptions options);
}
