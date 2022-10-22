package trld.jsonld;

import java.util.*;
import java.io.*;

import static trld.Mimetypes.JSON_MIME_TYPES;
import trld.platform.Input;
import static trld.platform.Io.isHttpUrl;

public class Docloader {
  static LoadDocumentCallback customDocumentLoader = null;

  public static void setDocumentLoader(LoadDocumentCallback loader) {
    customDocumentLoader = loader;
  }

  public static LoadDocumentCallback getDocumentLoader() {
    return getDocumentLoader(null);
  }
  public static LoadDocumentCallback getDocumentLoader(String startUrl) {
    if (customDocumentLoader != null) {
      return customDocumentLoader;
    }
    if ((startUrl != null && isHttpUrl(startUrl))) {
      if (startUrl.startsWith("https:")) {
        return httpsDocumentLoader;
      }
      return httpDocumentLoader;
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
        if (!(isHttpUrl(url))) {
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

  public static RemoteDocument loadAnyDocument(String url) {
    Input inp = new Input(url);
    Object document;
    if (JSON_MIME_TYPES.contains(inp.contentType)) {
      document = (Object) inp.loadJson();
    } else {
      document = (Object) inp.read();
    }
    return new RemoteDocument(inp.documentUrl, inp.contentType, inp.contextUrl, inp.profile, document);
  }
}
