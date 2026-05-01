package tools.bytecode;

import java.util.List;
import java.util.Map;

record CallFrame(
    String className,
    String methodName,
    String methodSignature,
    int entryLine,
    int exitLine,
    List<Map<String, Object>> sourceTrace,
    List<Map<String, Object>> stmtDetails) {}
