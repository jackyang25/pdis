"use client";

import { useEffect, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { CONTENT_ARRIVAL_MOTION } from "@/lib/motion";
import { displayLabel } from "@/lib/display-label";

/**
 * Which skills the assistant declares, read from the published reference.
 *
 * Listed rather than described in prose, and not restated in
 * `product_knowledge.json`, because the skills directory is the authority for what
 * exists: a hand-kept list here would be a second answer, and the one that goes stale is
 * always the one nobody runs. The generator publishes name, description and
 * requirements; the same drift test that guards the prompts guards this.
 *
 * Bodies are absent on purpose. A skill is a procedure the assistant follows in chat, and
 * several pages of instruction each would bury the reason a reader came here, which is
 * knowing that they exist and what each one needs.
 */

type SkillEntry = {
  name: string;
  description: string;
  requires: string[];
  requires_any: string[];
};

const REFERENCE_URL = "/prompt-reference.json";

/** What a workspace must hold, in the words the catalog uses in chat. */
function requirementText(skill: SkillEntry): string {
  const all = skill.requires.map((tool) => displayLabel(tool));
  const any = skill.requires_any.map((tool) => displayLabel(tool));
  if (all.length > 0 && any.length > 0) {
    return `Needs ${all.join(" and ")}, plus any of ${any.join(", ")}`;
  }
  if (all.length > 0) {
    return all.length === 1
      ? `Needs ${all[0]}`
      : `Needs ${all.join(" and ")} together`;
  }
  return `Needs any one of ${any.join(", ")}`;
}

export function AssistantSkills() {
  const [skills, setSkills] = useState<SkillEntry[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const response = await fetch(REFERENCE_URL);
        if (!response.ok) throw new Error(String(response.status));
        const data = (await response.json()) as { skills?: SkillEntry[] };
        if (live) setSkills(data.skills ?? []);
      } catch {
        // Silent by omission rather than an error banner: this is a list beside prose
        // that already explains what skills are, so a failed fetch costs a reader the
        // names and nothing they were relying on.
        if (live) setFailed(true);
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  if (failed) return null;

  return (
    <section aria-label="Declared skills" className="mt-6">
      <h3 className="text-sm font-semibold">
        Declared skills
      </h3>
      {skills === null ? (
        <div className="mt-3 space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : (
        <ul className={`mt-3 divide-y divide-border ${CONTENT_ARRIVAL_MOTION}`}>
          {skills.map((skill) => (
            <li
              key={skill.name}
              className="py-4"
            >
              <h4 className="text-sm font-semibold">{skill.name.charAt(0).toUpperCase() + skill.name.slice(1).replaceAll("-", " ")}</h4>
              <p className="mt-1 max-w-[75ch] text-sm leading-relaxed text-muted-foreground">
                {skill.description}
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                {requirementText(skill)}
              </p>
              <code className="mt-1 block break-all text-xs text-muted-foreground">{skill.name}</code>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
