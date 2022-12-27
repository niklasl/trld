package trld.jsonld;

import java.util.*;
import java.io.*;

import trld.Builtins;

import static trld.Mimetypes.JSON_MIME_TYPES;
import static trld.Mimetypes.JSONLD_MIME_TYPE;
import trld.platform.Input;

public class Docloader {
  public static final Map<String, String> REQUEST_HEADERS = Builtins.mapOf("Accept", JSONLD_MIME_TYPE + ", application/json;q=0.9");
  static /*@Nullable*/ LoadDocumentCallback customDocumentLoader = null;

  public static void setDocumentLoader(LoadDocumentCallback loader) {
    customDocumentLoader = loader;
  }

  public static LoadDocumentCallback getDocumentLoader() {
    return getDocumentLoader(null);
  }
  public static LoadDocumentCallback getDocumentLoader(/*@Nullable*/ String startUrl) {
    if (customDocumentLoader != null) {
      return customDocumentLoader;
    }
    if (startUrl != null) {
      if (startUrl.startsWith("https:")) {
        return httpsDocumentLoader;
      } else if (startUrl.startsWith("http:")) {
        return httpDocumentLoader;
      }
    }
    return anyDocumentLoader;
  }

  public static LoadDocumentCallback anyDocumentLoader = new LoadDocumentCallback() {
    public RemoteDocument apply(String url, LoadDocumentOptions options) {
        return loadAnyDocument(url);
    }
  };

  public static LoadDocumentCallback httpDocumentLoader = new LoadDocumentCallback() {
    public RemoteDocument apply(String url, LoadDocumentOptions options) {
        if ((!(url.startsWith("https:")) || !(url.startsWith("http:")))) {
            throw new LoadingDocumentNotAllowedError("Not allowed to load non-HTTP URL: " + url);
        }
        return loadAnyDocument(url);
    }
  };

  public static LoadDocumentCallback httpsDocumentLoader = new LoadDocumentCallback() {
    public RemoteDocument apply(String url, LoadDocumentOptions options) {
        if (!(url.startsWith("https:"))) {
            throw new LoadingDocumentNotAllowedError("Not allowed to load non-HTTPS URL: " + url);
        }
        return loadAnyDocument(url);
    }
  };

  protected static RemoteDocument loadAnyDocument(String url) {
    Object document;
    Input inp = new Input(url, REQUEST_HEADERS);
    try {
      if (JSON_MIME_TYPES.contains(inp.contentType)) {
        document = (Object) inp.loadJson();
      } else {
        document = (Object) inp.read();
      }
    }  finally {
      inp.close();
    }
    return new RemoteDocument(inp.documentUrl, inp.contentType, inp.contextUrl, inp.profile, document);
  }
}
