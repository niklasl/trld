package trld.jsonld;

import java.util.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import static org.junit.jupiter.api.Assertions.*;

import static trld.jsonld.Base.CONTEXT;


public class TestSuite {

    static final String TESTSUITE_DIR = "file://" + System.getProperties().get("user.home") + "/repos/github/w3c/json-ld-api/tests";

    static List<Arguments> testCaseProvider(String manifestFile) {
        List<Arguments> cases = new ArrayList<>();
        Map manifest = (Map) Common.loadJson(TESTSUITE_DIR + "/" + manifestFile);
        for (Map tc : (List<Map>) manifest.get("sequence")) {
            cases.add(Arguments.of(((String) ((Map) tc).get("@id")), tc));
        }
        return cases;
    }

    static List<Arguments> expandTestCases() {
        return testCaseProvider("expand-manifest.jsonld");
    }

    static List<Arguments> compactTestCases() {
        return testCaseProvider("compact-manifest.jsonld");
    }

    @ParameterizedTest(name = "Expand {0}")
    @MethodSource("expandTestCases")
    void expandTestSuite(String id, Map tc) {
        if (!((List) tc.get("@type")).contains("jld:PositiveEvaluationTest"))
            return;

        String name = id.replace("#t", "");
        String src = TESTSUITE_DIR + "/expand/" + name + "-in.jsonld";
        Object sourceData = Common.loadJson(src);
        Object resultData = Expansion.expand(sourceData, src);

        String expectedSrc = TESTSUITE_DIR + "/expand/" + name + "-out.jsonld";
        Object expectedData = Common.loadJson(expectedSrc);

        assertEquals(expectedData, resultData);
    }

    @ParameterizedTest(name = "Compact {0}")
    @MethodSource("compactTestCases")
    void compactTestSuite(String id, Map tc) {
        if (!((List) tc.get("@type")).contains("jld:PositiveEvaluationTest"))
            return;

        String name = id.replace("#t", "");
        String src = TESTSUITE_DIR + "/compact/" + name + "-in.jsonld";
        Object sourceData = Common.loadJson(src);
        Object resultData = Expansion.expand(sourceData, src);

        String contextSrc = TESTSUITE_DIR + "/compact/" + name + "-context.jsonld";
        Object contextData = Common.loadJson(contextSrc);
        resultData = Compaction.compact(contextData, resultData, src);

        String expectedSrc = TESTSUITE_DIR + "/compact/" + name + "-out.jsonld";
        Object expectedData = Common.loadJson(expectedSrc);
        if (expectedData instanceof Map) {
            ((Map) expectedData).remove(CONTEXT);
        }

        assertNotNull(expectedData);
        assertEquals(expectedData, resultData);
    }
}
