package trld.jsonld;

import java.util.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import static org.junit.jupiter.api.Assertions.*;

import static trld.jsonld.Base.CONTEXT;


public class TestSuite {

    static final String TESTSUITE_DIR = "file://" + System.getProperties().get("user.home") + "/repos/github/w3c/json-ld-api/tests/";
    static final String TESTSUITE_BASE_URL = "https://w3c.github.io/json-ld-api/tests/";

    static List<Arguments> testCaseProvider(String manifestFile) {
        List<Arguments> cases = new ArrayList<>();
        Map manifest = (Map) Common.loadJson(TESTSUITE_DIR + manifestFile);
        for (Map tc : (List<Map>) manifest.get("sequence")) {
            if (!((List) tc.get("@type")).contains("jld:PositiveEvaluationTest"))
                continue; // TODO: add handling of negative tests!

            cases.add(Arguments.of(((String) tc.get("@id")),
                                   ((String) tc.get("purpose")), tc));
        }
        return cases;
    }

    static List<Arguments> expandTestCases() {
        return testCaseProvider("expand-manifest.jsonld");
    }

    static List<Arguments> compactTestCases() {
        return testCaseProvider("compact-manifest.jsonld");
    }

    @ParameterizedTest(name = "Expand {0} - {1}")
    @MethodSource("expandTestCases")
    void expandTestSuite(String id, String purpose, Map tc) {
        String src = TESTSUITE_DIR + (String) tc.get("input");
        Map<String, Object> options = (Map) tc.getOrDefault("option", new HashMap<>());
        String baseUri = (String) options.getOrDefault("base", src);
        boolean ordered = true;

        String expandContext = (String) options.get("expandContext");
        if (expandContext != null) {
            expandContext = TESTSUITE_DIR + expandContext;
        }

        Object sourceData = Common.loadJson(src);

        String expectedSrc = TESTSUITE_DIR + (String) tc.get("expect");
        Object expectedData = Common.loadJson(expectedSrc);

        Object resultData = Expansion.expand(sourceData, baseUri, expandContext, ordered);

        assertEquals(expectedData, resultData);
    }

    @ParameterizedTest(name = "Compact {0} - {1}")
    @MethodSource("compactTestCases")
    void compactTestSuite(String id, String purpose, Map tc) {
        String src = TESTSUITE_DIR + (String) tc.get("input");
        String url = TESTSUITE_BASE_URL + (String) tc.get("input");
        Map<String, Object> options = (Map) tc.getOrDefault("option", new HashMap<>());
        String baseUri = (String) options.getOrDefault("base", url);
        boolean compactArrays = (Boolean) options.getOrDefault("compactArrays", true);
        boolean ordered = true;

        Object sourceData = Common.loadJson(src);
        sourceData = Expansion.expand(sourceData, baseUri, null, ordered);
        String contextSrc = TESTSUITE_DIR + (String) tc.get("context");
        Object contextData = Common.loadJson(contextSrc);

        String expectedSrc = TESTSUITE_DIR + (String) tc.get("expect");
        Object expectedData = Common.loadJson(expectedSrc);
        if (expectedData instanceof Map) {
            ((Map) expectedData).remove(CONTEXT);
        }

        Object resultData = Compaction.compact(contextData, sourceData, baseUri, compactArrays, ordered);

        assertNotNull(expectedData);
        assertEquals(expectedData, resultData);
    }
}
