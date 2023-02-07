package trld.jsonld;

//import javax.annotation.Nullable;
import java.util.*;
import java.util.function.BiFunction;


public abstract class LoadDocumentCallback implements BiFunction<String, LoadDocumentOptions, RemoteDocument> {
  public RemoteDocument apply(String url) {
      return apply(url, null);
  }
  public abstract RemoteDocument apply(String url, /*@Nullable*/ LoadDocumentOptions options);
}
