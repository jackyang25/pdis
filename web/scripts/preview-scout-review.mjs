// Development-only: compile current components in a disposable app, never a production route.
import { cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const source = fileURLToPath(new URL("../", import.meta.url));

export async function createPreviewWorkspace() {
  const root = await mkdtemp(join(tmpdir(), "pdis-scout-review-"));
  const web = join(root, "web");
  const cleanup = () => rm(root, { recursive: true, force: true });
  try {
    await mkdir(join(web, "app/scout"), { recursive: true });
    for (const path of ["components", "lib", "test-support", "public", "package.json", "tsconfig.json", "tailwind.config.ts", "postcss.config.mjs", "app/globals.css"]) {
      await cp(join(source, path), join(web, path), { recursive: true });
    }
    await mkdir(join(root, "shared"));
    await cp(join(source, "../shared/product_knowledge.json"), join(root, "shared/product_knowledge.json"));
    await symlink(join(source, "node_modules"), join(web, "node_modules"), "dir");
    let page = await readFile(join(source, "app/scout/page.tsx"), "utf8");
    for (const name of ["DocumentTargetReviewCheckpoint", "QuantitativeReviewCheckpoint"]) {
      const declaration = `function ${name}(`;
      if (!page.includes(declaration)) throw new Error(`Preview export not found: ${name}`);
      page = page.replace(declaration, `export ${declaration}`);
    }
    await writeFile(join(web, "app/scout/page.tsx"), page);
    await cp(join(source, "test-support/scout-review-preview.tsx.template"), join(web, "app/page.tsx"));
    // Keep the real typography and styles, but omit the application shell/Assistant.
    // CSP also blocks accidental API calls to another localhost port or external host.
    const layout = (await readFile(join(source, "app/layout.tsx"), "utf8"))
      .replace('import { AppShell } from "@/components/app-shell";', "")
      .replace("<AppShell>{children}</AppShell>", "{children}")
      .replace("<head>", `<head><meta httpEquiv="Content-Security-Policy" content="connect-src 'self'; form-action 'none'" />`);
    await writeFile(join(web, "app/layout.tsx"), layout);
    return { root, web, cleanup };
  } catch (error) {
    await cleanup();
    throw error;
  }
}

async function main() {
  const port = process.argv[2] ?? "3106";
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535) throw new Error("Choose a port from 1024 to 65535.");
  const preview = await createPreviewWorkspace();
  const env = Object.fromEntries(["PATH", "HOME", "TMPDIR", "SYSTEMROOT"].filter(key => process.env[key]).map(key => [key, process.env[key]]));
  const child = spawn(process.execPath, [join(source, "node_modules/next/dist/bin/next"), "dev", "--webpack", "--hostname", "127.0.0.1", "--port", port], {
    cwd: preview.web, stdio: "inherit", env: { ...env, NEXT_TELEMETRY_DISABLED: "1" },
  });
  const stop = () => child.kill("SIGTERM");
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  console.log(`Scout review preview: http://127.0.0.1:${port}\nCtrl+C removes the temporary app. No keys, API routes, or saved results.`);
  try {
    await new Promise((resolveExit, reject) => {
      child.once("error", reject);
      child.once("exit", code => { process.exitCode = code ?? 0; resolveExit(); });
    });
  } finally {
    process.removeListener("SIGINT", stop);
    process.removeListener("SIGTERM", stop);
    await preview.cleanup();
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
