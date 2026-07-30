// Publish generated shared artifacts the browser fetches at runtime.
//
// `shared/prompt_reference.json` is the committed source, generated from Scout's
// prompt catalog. The web layer cannot import a service, and the file is large
// enough that we fetch it rather than bundle it, so it has to sit under public/.
// Copied on dev and build so both environments serve the same bytes.
import { cp, mkdir } from "node:fs/promises";

// Paths resolve against this file, which lives in web/scripts/.
const ARTIFACTS = [["../../shared/prompt_reference.json", "../public/prompt-reference.json"]];

await mkdir(new URL("../public/", import.meta.url), { recursive: true });
for (const [from, to] of ARTIFACTS) {
  await cp(new URL(from, import.meta.url), new URL(to, import.meta.url), { force: true });
  console.log(`copied ${from} -> ${to}`);
}
