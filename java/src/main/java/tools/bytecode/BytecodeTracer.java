package tools.bytecode;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import sootup.core.inputlocation.AnalysisInputLocation;
import sootup.core.model.SootMethod;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

/**
 * Thin facade — constructs and wires all bytecode-analysis collaborators. Public API is unchanged;
 * {@link CallGraphBuilder} and {@link ForwardTracer} receive this class as before.
 */
public class BytecodeTracer {

  private static final Logger log = LoggerFactory.getLogger(BytecodeTracer.class);

  private final JavaView view;
  private final String projectPrefix;
  private final Path callGraphCache;
  private final MethodResolver methodResolver;
  private final FrameBuilder frameBuilder;
  private final IntraproceduralSlicer slicer;
  private final LineMapReporter lineMapReporter;

  public BytecodeTracer(String classpath, String prefix, Path callGraphCache) {
    this.view = buildView(classpath);
    this.projectPrefix = prefix;
    this.callGraphCache = callGraphCache;
    this.methodResolver = new MethodResolver(view);
    this.frameBuilder = new FrameBuilder();
    this.slicer = new IntraproceduralSlicer(view, methodResolver);
    this.lineMapReporter = new LineMapReporter(view);
  }

  private static JavaView buildView(String classpath) {
    List<AnalysisInputLocation> locations = new ArrayList<>();
    for (String path : classpath.split(":")) {
      if (!path.isBlank()) {
        log.info("[init] Registering classpath entry: {}", path);
        locations.add(new JavaClassPathAnalysisInputLocation(path));
      }
    }
    log.info("[init] Building JavaView from {} location(s)...", locations.size());
    long t = System.currentTimeMillis();
    JavaView javaView = new JavaView(locations);
    log.info("[init] JavaView ready in {}ms", System.currentTimeMillis() - t);
    return javaView;
  }

  // ------------------------------------------------------------------
  // Configuration
  // ------------------------------------------------------------------

  public Path getCallGraphCache() {
    return callGraphCache;
  }

  public List<JavaSootClass> getProjectClasses() {
    log.info("[init] Enumerating classes (prefix={})...", projectPrefix);
    long t = System.currentTimeMillis();
    var stream = view.getClasses();
    if (projectPrefix != null && !projectPrefix.isBlank()) {
      stream = stream.filter(c -> c.getType().getFullyQualifiedName().startsWith(projectPrefix));
    }
    List<JavaSootClass> result = stream.collect(Collectors.toList());
    log.info("[init] Found {} classes in {}ms", result.size(), System.currentTimeMillis() - t);
    return result;
  }

  // ------------------------------------------------------------------
  // Delegating API for CallGraphBuilder and ForwardTracer
  // ------------------------------------------------------------------

  SootMethod resolveMethodByName(String className, String methodName) {
    return methodResolver.resolveByName(className, methodName);
  }

  SootMethod resolveMethod(String className, int line) {
    return methodResolver.resolveByLine(className, line);
  }

  SootMethod resolveMethod(String methodSignature) {
    return methodResolver.resolveBySignature(methodSignature);
  }

  CallFrame buildFrame(SootMethod method, String sig) {
    return frameBuilder.buildFrame(method, sig);
  }

  CallFrame buildFlatFrame(SootMethod method, String sig) {
    return frameBuilder.buildFlatFrame(method, sig);
  }

  // ------------------------------------------------------------------
  // Public feature methods
  // ------------------------------------------------------------------

  public Map<String, Object> trace(String className, int fromLine, int toLine) {
    return slicer.trace(className, fromLine, toLine);
  }

  public Map<String, Object> dumpLineMap(String className) {
    return lineMapReporter.dumpLineMap(className);
  }
}
