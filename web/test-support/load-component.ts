import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../", import.meta.url));
const nativeRequire = createRequire(import.meta.url);

/** Render real TSX with Node's test runner, resolving the app's aliases in memory. */
export function loadComponent(path: string, overrides: Record<string, unknown> = {}, expose: string[] = []): any {
  const cache = new Map<string, { exports: any }>();
  function load(file: string): any {
    if (cache.has(file)) return cache.get(file)!.exports;
    const { outputText } = ts.transpileModule(readFileSync(file, "utf8"), {
      compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    });
    const module = { exports: {} };
    cache.set(file, module);
    const localRequire = (name: string): any => {
      if (Object.hasOwn(overrides, name)) return overrides[name];
      if (!name.startsWith(".") && !name.startsWith("@/")) return nativeRequire(name);
      const base = name.startsWith("@/") ? resolve(root, name.slice(2)) : resolve(dirname(file), name);
      const resolved = [base, `${base}.tsx`, `${base}.ts`].find(existsSync);
      if (!resolved) throw new Error(`Cannot resolve ${name}`);
      return load(resolved);
    };
    // Test private page components without adding unsupported Next.js page exports.
    const testExports = file === path ? expose.map((name) => {
      if (!/^[A-Za-z_$][\w$]*$/.test(name)) throw new Error("Invalid test export");
      return `exports.${name} = ${name};`;
    }).join("\n") : "";
    new Function("require", "module", "exports", outputText + "\n" + testExports)(localRequire, module, module.exports);
    return module.exports;
  }
  return load(path);
}
