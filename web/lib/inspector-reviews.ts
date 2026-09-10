import type { InspectionResult, InspectionReviewView } from "./api.ts";

/** Select an authored review, without copying blocks or changing saved provenance. */
export function projectInspectionReview(run: InspectionResult, rubricId: string): InspectionReviewView {
  const review = run.reviews.find(item => item.rubric.id === rubricId);
  if (!review) throw new Error(`Unknown Inspector rubric: ${rubricId}`);
  const { reviews, rubric_resolutions, ...document } = run;
  return { ...document, ...review };
}
