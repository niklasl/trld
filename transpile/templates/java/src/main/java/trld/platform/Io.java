package trld.platform;

import java.util.*;

import static trld.jsonld.Docloader.loadAnyDocument;
import trld.jsonld.LoadDocumentCallback;
import trld.jsonld.LoadDocumentOptions;
import trld.jsonld.RemoteDocument;

public class Io {

    private static /*@Nullable*/ LoadDocumentCallback customDocumentLoader = null;

    public static /*@Nullable*/ LoadDocumentCallback getDocumentLoader() {
        return getDocumentLoader(null);
    }

    public static /*@Nullable*/ LoadDocumentCallback getDocumentLoader(String startUrl) {
        if (customDocumentLoader != null) {
            return customDocumentLoader;
        }
        return new LoadDocumentCallback() {
            public RemoteDocument apply(String url, LoadDocumentOptions options) { return loadAnyDocument(url); }
        };
    }

    public static synchronized void setDocumentLoader(LoadDocumentCallback loader) {
        customDocumentLoader = loader;
    }

    public static boolean isHttpUrl(String url) {
        return url.startsWith("http:") || url.startsWith("https:");
    }

}
