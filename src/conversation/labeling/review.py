"""Explicit human decisions and audited exports; no automatic acceptance."""
from collections import Counter
from pathlib import Path

from common.schemas import PreferenceUpdate
from conversation.labeling.leakage import pool_issues
from conversation.labeling.models import ReviewItem, ReviewRecord, TrainingRecord
from conversation.labeling.storage import digest, exclusive_writer, read_rows, write_rows
from conversation.labeling.teacher import rule_parse
from conversation.labeling.validation import validate_batch, validate_label


def build_queue(samples, labels, index):
    validations = validate_batch(samples, labels, index)
    by_id = {label.sample_id: label for label in labels}
    queue = []
    for sample, validation in zip(samples, validations):
        teacher = by_id.get(sample.sample_id)
        if teacher is None:
            # A missing journal entry is a pipeline error, never a fabricated teacher label.
            raise ValueError("Missing teacher label; run teacher labeling first")
        disagreement = (teacher.candidate != teacher.rule_candidate.model_dump(mode="json") or
                        teacher.teacher_prediction is not None and
                        teacher.teacher_prediction != teacher.rule_result.update.model_dump(mode="json"))
        if teacher.teacher_prediction is not None:
            raw = validate_label(sample, teacher.teacher_prediction, index)
            if not raw.passed:
                validation.risk_flags.append("teacher_prediction_failed_validation")
                validation.warnings.append("Original teacher prediction required normalization or correction")
        priority = "high" if not validation.passed or disagreement or validation.risk_flags else (
            "medium" if validation.warnings or not teacher.rule_resolved else "low")
        queue.append(ReviewItem(sample=sample, teacher=teacher, validation=validation,
                                disagreement=disagreement, priority=priority))
    return sorted(queue, key=lambda item: {"high": 0, "medium": 1, "low": 2}[item.priority])


def review_item(item, action, index, *, correction=None, note=""):
    if action not in {"accepted", "corrected", "rejected", "skipped"}:
        raise ValueError("Invalid review action")
    final = None
    if action in {"accepted", "corrected"}:
        if action == "accepted" and (item.teacher.status != "completed" or item.teacher.error):
            raise ValueError("A failed teacher attempt cannot be accepted; enter a correction")
        payload = correction if action == "corrected" else item.teacher.candidate
        # Schema validation is intentionally before any disk mutation.
        final = PreferenceUpdate.model_validate(payload).model_dump(mode="json")
        validation = validate_label(item.sample, final, index)
        if not validation.passed:
            raise ValueError("Label failed deterministic validation: " + ", ".join(validation.errors))
        if item.teacher.sample_hash != digest(item.sample):
            raise ValueError("Review item has stale sample provenance")
    return ReviewRecord(sample_id=item.sample.sample_id, item_hash=digest(item),
        original_teacher_prediction=item.teacher.teacher_prediction,
        original_candidate=item.teacher.candidate, final_label=final, action=action, note=note)


def save_review(path: Path, record: ReviewRecord):
    with exclusive_writer(path):
        history = [ReviewRecord.model_validate(r) for r in read_rows(path)] if path.exists() else []
        # Preserve every prior decision and prediction. Latest explicit decision wins.
        write_rows(path, [*history, record], replace=True)


def export_records(queue, reviews, index, *, only_unresolved=False):
    latest = {record.sample_id: record for record in reviews}
    training, excluded = [], []
    samples = [item.sample for item in queue]
    for item, issues in zip(queue, pool_issues(samples, index)):
        sample, teacher = item.sample, item.teacher
        record = latest.get(sample.sample_id)
        reason = None
        if record is None or record.action not in {"accepted", "corrected"}:
            reason = "unreviewed" if record is None else record.action
        elif (record.item_hash != digest(item) or teacher.sample_hash != digest(sample) or
              record.original_teacher_prediction != teacher.teacher_prediction or
              record.original_candidate != teacher.candidate):
            reason = "stale_review"
        elif record.action == "accepted" and (record.final_label != teacher.candidate or teacher.error or teacher.status != "completed"):
            reason = "invalid_acceptance"
        else:
            validation = validate_label(sample, record.final_label, index, extra_errors=issues)
            if not validation.passed:
                reason = "invalid_label:" + ",".join(validation.errors)
        # Recompute routing offline to prevent a stale/edited flag changing the subset.
        _, baseline = rule_parse(sample)
        resolved = not (baseline.metadata.requires_llm or baseline.metadata.clarification_required)
        if reason is None and only_unresolved and resolved:
            reason = "rule_resolved"
        if reason:
            excluded.append({"sample_id": sample.sample_id, "reason": reason})
            continue
        training.append(TrainingRecord(input={
            "message": sample.message,
            "current_state": sample.current_state.model_dump(mode="json") if sample.current_state else None,
            "rule_result": baseline.rule_result.model_dump(mode="json"),
            "previous_results": [r.model_dump(mode="json") for r in sample.previous_results]},
            target=PreferenceUpdate.model_validate(record.final_label),
            metadata={"sample_id": sample.sample_id, "category": sample.category,
                      "source": sample.source, "review_status": record.action,
                      "rule_resolved": resolved, "review_timestamp": record.timestamp.isoformat()}))
    return training, excluded


def counts(queue):
    return {"total": len(queue), "categories": dict(Counter(i.sample.category for i in queue)),
            "priority": dict(Counter(i.priority for i in queue)),
            "valid": sum(i.validation.passed for i in queue),
            "rule_resolved": sum(i.teacher.rule_resolved for i in queue)}
