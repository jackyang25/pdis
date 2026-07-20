import { HeaderPicker } from "./header-picker";
import { Label } from "./ui/label";

export function ConfigurationFields() {
  return (
    <div aria-labelledby="configuration-title">
      <Label id="configuration-title" asChild>
        <h2 className="mb-5">Configuration</h2>
      </Label>
      <HeaderPicker />
    </div>
  );
}
