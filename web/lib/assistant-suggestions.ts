/**
 * The two questions the empty chat offers, for what the workspace holds right now.
 *
 * Asked as questions, never as a list of skills: the agent answers from the catalog in
 * its own prompt, so adding a skill changes no text here.
 */
export function openers(state: { reviewPhase?: string; attachments: number; results: number }): [string, string] {
  if (state.reviewPhase) return ["Explain the selected review item.", "What evidence should I check before deciding?"];
  if (state.attachments > 0 && state.results > 0) return ["Summarize the attached context.", "Compare the attachment with my results."];
  if (state.attachments > 0) return ["Summarize the attached context.", "What important details does it contain?"];
  if (state.results > 1) return ["What skills can you use here?", "Where do the results agree or differ?"];
  if (state.results === 1) return ["Summarize the available result.", "What skills can you use here?"];
  return ["Which tool should I use?", "What skills can you use here?"];
}
