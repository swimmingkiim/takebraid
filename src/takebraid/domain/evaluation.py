"""Exact duration-weighted detection and exclusion accounting on source frames."""

from dataclasses import dataclass
from fractions import Fraction

from takebraid.domain.frames import FrameMap
from takebraid.domain.time import _require_int

DEFECTS = {"focus_failure", "exposure_failure", "unwanted_camera_motion"}
TRUTHS = {"defect", "normal", "unknown"}


@dataclass(frozen=True)
class LabelInterval:
    first_frame: int
    end_frame: int
    votes: tuple[str, ...]

    def __post_init__(self):
        _require_int(self.first_frame, "label first")
        _require_int(self.end_frame, "label end")
        if not 0 <= self.first_frame < self.end_frame:
            raise ValueError("Labels require 0 <= FIRST < END")
        if (
            not isinstance(self.votes, tuple)
            or len(self.votes) < 2
            or any(v not in TRUTHS for v in self.votes)
        ):
            raise ValueError("At least two explicit defect/normal/unknown votes are required")

    @property
    def consensus(self):
        return self.votes[0] if len(set(self.votes)) == 1 else "unknown"


def score_labels(
    frame_map: FrameMap,
    labels: tuple[LabelInterval, ...],
    interpretation: dict,
    decisions: list[dict] | None = None,
) -> dict:
    bounds = frame_map.boundaries()
    truth = []
    disagreements = 0
    disagreement_mask = []
    cursor = 0
    for label in labels:
        if (
            not isinstance(label, LabelInterval)
            or label.first_frame != cursor
            or label.end_frame > len(frame_map.frames)
        ):
            raise ValueError("Labels must partition the complete source frame range")
        disagreement_mask.extend(
            [len(set(label.votes)) > 1] * (label.end_frame - label.first_frame)
        )
        truth.extend([label.consensus] * (label.end_frame - label.first_frame))
        if len(set(label.votes)) > 1:
            disagreements += label.end_frame - label.first_frame
        cursor = label.end_frame
    if cursor != len(frame_map.frames):
        raise ValueError("Labels must cover final source frame")
    cells = interpretation["cells"]
    if len(cells) != len(truth):
        raise ValueError("Evaluation requires a complete interpretation cell partition")
    prediction = []
    for i, cell in enumerate(cells):
        if (cell["in_pts"], cell["out_pts"]) != (bounds[i], bounds[i + 1]):
            raise ValueError("Prediction cells differ from source boundaries")
        if cell["state"] not in {"enter", "hold", "no_trigger", "unknown"}:
            raise ValueError("Invalid prediction coverage state")
        prediction.append("unknown" if cell["state"] == "unknown" else "clear")
    indices = {p: i for i, p in enumerate(bounds)}
    for candidate in interpretation["candidates"]:
        first, end = indices[candidate["core_in_pts"]], indices[candidate["core_out_pts"]]
        if first >= end or any(prediction[i] == "unknown" for i in range(first, end)):
            raise ValueError("Candidate core must have nonempty observed coverage")
        prediction[first:end] = ["candidate"] * (end - first)
    exclusion = None
    if decisions is not None:
        exclusion = []
        cursor = 0
        for row in decisions:
            first, end = row["first_frame"], row["end_frame"]
            if (
                first != cursor
                or not first < end <= len(truth)
                or row["state"] not in {"keep", "exclude", "review", "unknown"}
            ):
                raise ValueError("Decision intervals must partition evaluated source")
            exclusion.extend([row["state"] == "exclude"] * (end - first))
            cursor = end
        if cursor != len(truth):
            raise ValueError("Decision coverage incomplete")
    totals = {
        key: Fraction(0)
        for key in (
            "source_seconds",
            "candidate_seconds",
            "candidate_label_unknown_seconds",
            "decision_coverage_seconds",
            "decision_labeled_normal_seconds",
            "label_defect_seconds",
            "label_normal_seconds",
            "label_unknown_seconds",
            "disagreement_seconds",
            "prediction_unknown_seconds",
            "unknown_on_defect_seconds",
            "unknown_on_normal_seconds",
            "true_positive_seconds",
            "false_positive_seconds",
            "false_negative_observed_seconds",
            "true_negative_seconds",
            "excluded_normal_seconds",
            "excluded_defect_seconds",
            "excluded_label_unknown_seconds",
        )
    }
    for index, (gold, predicted) in enumerate(zip(truth, prediction, strict=True)):
        duration = frame_map.time_base.seconds(bounds[index + 1] - bounds[index])
        totals["source_seconds"] += duration
        if disagreement_mask[index]:
            totals["disagreement_seconds"] += duration
        totals[f"label_{gold}_seconds"] += duration
        if predicted == "candidate":
            totals["candidate_seconds"] += duration
            if gold == "unknown":
                totals["candidate_label_unknown_seconds"] += duration
        if exclusion is not None:
            totals["decision_coverage_seconds"] += duration
            if gold == "normal":
                totals["decision_labeled_normal_seconds"] += duration
        if predicted == "unknown":
            totals["prediction_unknown_seconds"] += duration
            if gold != "unknown":
                totals[f"unknown_on_{gold}_seconds"] += duration
        elif gold == "defect":
            totals[
                "true_positive_seconds"
                if predicted == "candidate"
                else "false_negative_observed_seconds"
            ] += duration
        elif gold == "normal":
            totals[
                "false_positive_seconds" if predicted == "candidate" else "true_negative_seconds"
            ] += duration
        if exclusion is not None and exclusion[index]:
            totals[f"excluded_{gold if gold != 'unknown' else 'label_unknown'}_seconds"] += duration
    return {
        "durations": totals,
        "ratios": duration_ratios(totals),
        "frames": len(truth),
        "disagreement_frames": disagreements,
        "decision_evaluated": exclusion is not None,
    }


def duration_ratios(t):
    def ratio(a, b):
        return a / b if b else None

    tp, fp, fn = (
        t["true_positive_seconds"],
        t["false_positive_seconds"],
        t["false_negative_observed_seconds"],
    )
    return {
        "precision": ratio(tp, tp + fp),
        "recall_all_labeled_defect": ratio(tp, t["label_defect_seconds"]),
        "recall_observed_defect": ratio(tp, tp + fn),
        "observed_normal_false_positive_rate": ratio(fp, fp + t["true_negative_seconds"]),
        "prediction_unknown_rate": ratio(t["prediction_unknown_seconds"], t["source_seconds"]),
        "label_unknown_rate": ratio(t["label_unknown_seconds"], t["source_seconds"]),
        "normal_exclusion_rate": ratio(
            t["excluded_normal_seconds"], t["decision_labeled_normal_seconds"]
        ),
    }
