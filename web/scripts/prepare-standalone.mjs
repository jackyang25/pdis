import { cp, mkdir } from "node:fs/promises";

const standaloneRoot = new URL("../.next/standalone/", import.meta.url);
const standaloneNext = new URL(".next/", standaloneRoot);

await mkdir(standaloneNext, { recursive: true });
await cp(new URL("../public/", import.meta.url), new URL("public/", standaloneRoot), {
  recursive: true,
  force: true,
});
await cp(
  new URL("../.next/static/", import.meta.url),
  new URL("static/", standaloneNext),
  { recursive: true, force: true },
);
