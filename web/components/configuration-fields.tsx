import { HeaderPicker } from "./header-picker";
import { ConfigurationShell } from "./ui/config-field";

/**
 * The configuration rail for tools that select one document context.
 *
 * Aligner selects a source type per document, so it composes the primitives in
 * `ui/config-field.tsx` directly rather than using this.
 */
export function ConfigurationFields() {
  return (
    <ConfigurationShell>
      <HeaderPicker />
    </ConfigurationShell>
  );
}
