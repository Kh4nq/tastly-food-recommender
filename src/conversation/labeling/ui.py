"""Optional local Streamlit UI. Importing the package does not import Streamlit."""
import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from conversation.labeling.cli import load_models
from conversation.labeling.leakage import LeakageIndex
from conversation.labeling.models import ReviewItem, ReviewRecord
from conversation.labeling.review import counts, review_item, save_review
from conversation.labeling.storage import DEFAULT_DIRECTORY, digest


def main(argv=None):
    import streamlit as st

    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args(argv)
    st.set_page_config(page_title="AI2 label review", layout="wide")
    st.title("AI2 candidate label review")
    st.caption("Teacher predictions are candidates. Each saved acceptance or correction is an explicit human decision.")
    path = args.directory / "reviewed.jsonl"
    try:
        queue = load_models(args.directory / "review_queue.jsonl", ReviewItem)
        reviews = load_models(path, ReviewRecord) if path.exists() else []
        index = LeakageIndex.from_benchmark()
    except (ValidationError, ValueError, OSError):
        st.error("Cannot read valid review artifacts. Run preparation first and check the directory.")
        return
    st.json(counts(queue), expanded=False)
    latest = {r.sample_id: r for r in reviews}
    show_reviewed = st.checkbox("Include previously reviewed samples", value=False)
    show_skipped = st.checkbox("Revisit skipped samples", value=False)
    pending = [i for i in queue if show_reviewed or i.sample.sample_id not in latest
               or latest[i.sample.sample_id].item_hash != digest(i)
               or show_skipped and latest[i.sample.sample_id].action == "skipped"]
    if not pending:
        st.info("No pending samples. Export reviewed labels using the export script.")
        return
    selected = st.selectbox("Sample", range(len(pending)), format_func=lambda n:
        f"{pending[n].priority} | {pending[n].sample.category} | {pending[n].sample.sample_id}")
    item = pending[selected]
    st.subheader(item.sample.message)
    st.write(f"Priority: {item.priority}; rule resolved: {item.teacher.rule_resolved}")
    if item.sample.history:
        st.write("Synthetic prior turns", item.sample.history)
    st.json({"current_state": item.sample.current_state.model_dump(mode="json") if item.sample.current_state else None,
             "previous_results": [r.model_dump(mode="json") for r in item.sample.previous_results]})
    left, right = st.columns(2)
    with left:
        st.write("Rule output")
        st.json(item.teacher.rule_result.model_dump(mode="json"))
    with right:
        st.write("Original teacher prediction")
        st.json(item.teacher.teacher_prediction)
        st.write("Candidate after existing AI2 normalization")
        st.json(item.teacher.candidate)
    st.json({"validation": item.validation.model_dump(mode="json"),
             "routing": item.teacher.routing.model_dump(mode="json"), "provider_error": item.teacher.error})
    existing = latest.get(item.sample.sample_id)
    initial = existing.final_label if existing and existing.final_label is not None else item.teacher.candidate
    correction = st.text_area("Corrected PreferenceUpdate JSON", json.dumps(initial or {}, ensure_ascii=False, indent=2),
                              height=280, key="json-" + item.sample.sample_id)
    note = st.text_input("Optional review note", key="note-" + item.sample.sample_id)
    for column, label, action in zip(st.columns(4), ("Accept", "Correct", "Reject", "Skip"),
                                    ("accepted", "corrected", "rejected", "skipped")):
        if column.button(label, key=action + item.sample.sample_id):
            try:
                payload = json.loads(correction) if action == "corrected" else None
                record = review_item(item, action, index, correction=payload, note=note)
                save_review(path, record)
            except (ValidationError, ValueError, TypeError, OSError):
                st.error("Decision not saved. Check JSON/schema and deterministic validation; labels with errors cannot be accepted. Check writer locks if saving fails.")
            else:
                st.success("Decision saved; original prediction retained.")
                st.rerun()
