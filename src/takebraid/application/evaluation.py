"""Score frozen candidate policies against explicit rights-declared temporal labels."""

import platform
from pathlib import Path

from takebraid import __version__
from takebraid.adapters.artifacts import to_json_value, write_new_json
from takebraid.adapters.evaluation import load_manifest, local_path
from takebraid.adapters.identity import file_digest
from takebraid.adapters.records import read_json
from takebraid.adapters.stages import StageAttempt, cached_output
from takebraid.application.decisions import _interpretation, load_decisions
from takebraid.domain.evaluation import LabelInterval, duration_ratios, score_labels

RECIPE = "quality-evaluation/1"
METRIC_DEFECTS = {
    "laplacian_variance": "focus_failure",
    "dark_fraction": "exposure_failure",
    "bright_fraction": "exposure_failure",
    "path_residual_squared": "unwanted_camera_motion",
}


def _aggregate(rows):
    totals = {
        key: sum(row["score"]["durations"][key] for row in rows)
        for key in rows[0]["score"]["durations"]
    }
    return {
        "entries": len(rows),
        "projects": len({row["project_id"] for row in rows}),
        "shoots": len({row["shoot_id"] for row in rows}),
        "decision_entries": sum(row["score"]["decision_evaluated"] for row in rows),
        "durations": totals,
        "ratios": duration_ratios(totals),
    }


def evaluate_manifest(
    manifest_path: Path, output: Path, *, split: str = "test", force: bool = False
) -> Path:
    if split not in {"calibration", "test"}:
        raise ValueError("Evaluation split must be calibration or test")
    manifest_path = manifest_path.expanduser().resolve(strict=True)
    manifest_digest = file_digest(manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest = load_manifest(manifest_path)
    selected = [entry for entry in manifest["entries"] if entry["split"] == split]
    if not selected:
        raise ValueError("Requested evaluation split has no entries")
    rows, evidence, checks = [], [], []
    total_frames = 0
    for entry in selected:
        asset = local_path(manifest_path, entry["asset"])
        observation = local_path(manifest_path, entry["observation"])
        interpretation = local_path(manifest_path, entry["interpretation"])
        context, document, ih, oh, stable = _interpretation(asset, observation, interpretation)
        total_frames += len(context.frame_map.frames)
        if total_frames > 250000:
            raise ValueError("Selected evaluation exceeds the 250000 source-frame budget")
        checks.append(stable)
        policy = document["inputs"]["policy"]
        if (
            document["inputs"]["policy_sha256"] != manifest["policy_registry"][entry["defect"]]
            or METRIC_DEFECTS[policy["metric"]] != entry["defect"]
        ):
            raise ValueError("Entry policy differs from the frozen defect protocol")
        labels = tuple(
            LabelInterval(
                label["first_frame"],
                label["end_frame"],
                tuple(label["votes"][rater] for rater in entry["annotators"]),
            )
            for label in entry["labels"]
        )
        decisions = None
        decision_digest = None
        if entry.get("decision") is not None:
            decision_path = local_path(manifest_path, entry["decision"])
            decision_digest = file_digest(decision_path)
            record, decision_context, decision_stable = load_decisions(asset, decision_path)
            if (
                record["interpretation"]["sha256"] != ih
                or decision_context.frame_map != context.frame_map
            ):
                raise ValueError("Evaluated decision must derive from the selected interpretation")
            checks.append(decision_stable)
            decisions = record["intervals"]
        rows.append(
            {
                key: entry[key]
                for key in (
                    "id",
                    "kind",
                    "defect",
                    "project_id",
                    "shoot_id",
                    "scene",
                    "annotators",
                    "annotation_protocol",
                    "label_method",
                    "rights",
                )
            }
            | {
                "_frame_map": context.frame_map,
                "_labels": labels,
                "_interpretation": document["interpretation"],
                "_decisions": decisions,
            }
        )
        evidence.append(
            {
                "id": entry["id"],
                "observation_sha256": oh,
                "interpretation_sha256": ih,
                "decision_sha256": decision_digest,
                "observation_inputs": context.inputs,
                "policy": policy,
                "policy_sha256": document["inputs"]["policy_sha256"],
            }
        )
    inputs = {
        "recipe": RECIPE,
        "takebraid_version": __version__,
        "manifest_sha256": manifest_digest,
        "dataset_id": manifest["dataset_id"],
        "label_version": manifest["label_version"],
        "split": split,
        "policy_registry": manifest["policy_registry"],
        "declared_inventory": {
            name: sum(e["split"] == name for e in manifest["entries"])
            for name in ("calibration", "test")
        },
        "evidence": evidence,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
    }

    def stable_all():
        for check in checks:
            check()
        if file_digest(manifest_path) != manifest_digest:
            raise ValueError("Evaluation manifest/labels changed during scoring")

    prepared_rows = rows

    def compute_report():
        rows = [
            {key: value for key, value in row.items() if not key.startswith("_")}
            | {
                "score": score_labels(
                    row["_frame_map"], row["_labels"], row["_interpretation"], row["_decisions"]
                )
            }
            for row in prepared_rows
        ]
        cohorts = []
        for kind, defect in sorted({(row["kind"], row["defect"]) for row in rows}):
            group = [row for row in rows if (row["kind"], row["defect"]) == (kind, defect)]
            scenes = {
                scene: _aggregate([row for row in group if row["scene"] == scene])
                for scene in sorted({r["scene"] for r in group})
            }
            projects = {
                project: _aggregate([row for row in group if row["project_id"] == project])
                for project in sorted({r["project_id"] for r in group})
            }
            cohorts.append(
                {
                    "kind": kind,
                    "defect": defect,
                    **_aggregate(group),
                    "scenes": scenes,
                    "projects": projects,
                }
            )
        kinds = {row["kind"] for row in rows}
        report = to_json_value(
            {
                "schema_version": "0.1",
                "inputs": inputs,
                "prediction_scope": "candidate_core",
                "aggregation": "source_duration_micro",
                "exclusion_source": "explicit_user_decisions",
                "evidence_scope": "synthetic_only"
                if kinds == {"synthetic"}
                else "camera_only"
                if kinds == {"camera"}
                else "mixed_separated",
                "automatic_exclusion_validated": False,
                "entries": rows,
                "cohorts": cohorts,
            }
        )
        return report

    output = output.expanduser().resolve()
    stable_all()
    cached = None if force else cached_output(output, inputs)
    if cached is not None:
        report = compute_report()
        if (
            read_json(cached) != report
            or file_digest(cached.parent / "manifest.json") != manifest_digest
        ):
            raise ValueError("Cached evaluation differs from recomputed evidence")
        stable_all()
        return cached
    with StageAttempt(output, inputs) as attempt:
        report = compute_report()
        target = attempt.directory / "evaluation.json"
        with (attempt.directory / "manifest.json").open("xb") as handle:
            handle.write(manifest_bytes)
        if file_digest(attempt.directory / "manifest.json") != manifest_digest:
            raise ValueError("Manifest snapshot differs from its recorded digest")
        write_new_json(
            attempt.directory / "manifest-origin.json",
            {
                "schema_version": "0.1",
                "base_directory": str(manifest_path.parent),
                "manifest_filename": manifest_path.name,
            },
        )
        write_new_json(target, report)
        stable_all()
        attempt.complete(target)
        return target
