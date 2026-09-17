import assert from "node:assert/strict";
import test from "node:test";
import { targetReviewFixture, evidenceReviewFixture, diagnosticTargetReviewFixture, diagnosticEvidenceReviewFixture } from "../test-support/scout-review-fixture.ts";
import { applyEvidenceReviewRecommendations } from "./quantitative-review.ts";
import { pendingQuantitativeReviewCount } from "./result-contracts.ts";

test("diagnostic seeds preserve usable proposals on unavailable reviews and retain qualifier context", () => {
  const target = diagnosticTargetReviewFixture();
  const unavailable = target.quantitative_ledger.targets.find(item => item.ai_recommendation === "unavailable")!;
  assert.equal(unavailable.review_status, "needs_review");
  assert.ok(unavailable.ai_review_failure_code);
  const failed = target.quantitative_ledger.reviews.find(item => item.classification === "mapping_failed")!;
  assert.equal(failed.target_ids.length, 0);
  assert.ok(failed.failure_code);
  const evidence = diagnosticEvidenceReviewFixture();
  const measurement = evidence.conformity[0].excluded_measurements[0];
  assert.ok(measurement.source_passage?.includes(measurement.source_quote));
  assert.ok(measurement.source_passage?.includes("first 6 months"));
  const result = applyEvidenceReviewRecommendations(evidence.conformity)[0];
  assert.equal(result.measurements.length, 0);
  assert.equal(result.excluded_measurements[0].admission_status, "needs_review");
});

test("both seeded checkpoints have pending, partial and completed snapshots with real lineage", () => {
  for (const factory of [targetReviewFixture, evidenceReviewFixture]) {
    const snapshots = [factory("pending"), factory("partial"), factory("completed")];
    const counts = snapshots.map(pendingQuantitativeReviewCount);
    assert.ok(counts[0] > counts[1]);
    assert.ok(counts[1] > 0);
    assert.equal(counts[2], 0);
    for (const result of snapshots) {
      const blocks = new Set(result.blocks.map(block => block.id));
      const fields = new Set(result.variables.map(field => field.name));
      for (const target of result.quantitative_ledger.targets) {
        assert.ok(target.doc_block_ids.length > 0);
        assert.ok(target.doc_block_ids.every(id => blocks.has(id)));
        assert.ok(target.field_links.every(link => fields.has(link.attribute_ref)));
      }
      for (const review of result.quantitative_ledger.reviews) {
        assert.ok(blocks.has(review.block_id));
        assert.ok(review.attribute_refs.every(ref => fields.has(ref)));
      }
      if (result.phase === "target_review") {
        for (const items of [result.matches, result.conformity, result.search_plan, result.assessments]) assert.equal(items?.length, 0);
      } else {
        assert.ok(result.quantitative_ledger.targets.every(target => target.review_status !== "needs_review"));
        for (const score of result.conformity) {
          const units = score.measurements.map(item => item.evidence_unit_id);
          assert.equal(new Set(units).size, units.length, "alternatives cannot both be admitted");
          assert.equal(score.benchmark_count, score.measurements.length);
          for (const measurement of [...score.measurements, ...score.excluded_measurements]) {
            const match = result.matches.find(match => match.insight.id === measurement.insight_id);
            assert.ok(match?.insight.supporting_findings.some(finding => finding.url === measurement.url && finding.excerpt === measurement.source_quote));
          }
        }
      }
    }
  }
});

test("seed covers recommendations, unresolved statements and manual versus recommended alternatives", () => {
  const target = targetReviewFixture();
  assert.deepEqual(new Set(target.quantitative_ledger.targets.map(item => item.ai_recommendation)), new Set(["confirm", "exclude", "flag"]));
  assert.ok(target.quantitative_ledger.reviews.some(item => item.classification === "partial_target"));
  assert.ok(target.quantitative_ledger.reviews.some(item => item.classification === "uncertain"));
  const evidence = evidenceReviewFixture();
  const candidates = evidence.conformity[0].excluded_measurements;
  assert.deepEqual(new Set(candidates.map(item => item.ai_recommendation)), new Set(["admit", "reject", "flag"]));
  const groups = Map.groupBy(candidates, item => item.evidence_unit_id);
  assert.equal([...groups.values()].filter(items => items.length === 1).length, 3);
  assert.equal([...groups.values()].filter(items => items.length === 2).length, 3);
});
