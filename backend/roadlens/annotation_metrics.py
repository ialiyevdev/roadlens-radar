"""Frame-IoU tracking checks against reviewed manual identities, without an IDF1 claim."""

from .annotation_models import AnnotationDocument
from .assignment import maximum_score_matching
from .tracker import intersection_over_union


def annotation_metrics(document: AnnotationDocument) -> dict:
    limits = ["Only reviewed frames and visible ground-truth boxes are scored; full occlusions without boxes are excluded.",
              "Global category-consistent box assignment uses IoU > 0.5; it cannot resolve visually indistinguishable overlapping boxes.",
              "An ID switch is a changed matched prediction ID for the same manual identity. A fragment is matched, visibly missed, then matched again.",
              "These are annotation-conditioned counts, not IDF1 or evidence of speed accuracy."]
    proposal = document.proposal_metadata
    reviewed = [frame for frame in document.frames if frame.reviewed]
    scored = [frame for frame in reviewed if not proposal or proposal.start_index <= frame.index <= proposal.end_index]
    if proposal:
        limits.append("Only reviewed frames inside the retained single proposal run are scored; IDs are not stitched across separate runs.")
    else:
        limits.append("No recorded proposal configuration: imported prediction completeness and tracker settings require manual verification.")
    result = {"annotated_vehicles": len({item.identity for frame in document.frames for item in frame.objects}),
              "reviewed_frames": len(reviewed), "scored_frames": len(scored),
              "predicted_frames": sum(bool(frame.predictions) for frame in scored),
              "matched_observations": 0, "missed_observations": 0, "false_positive_observations": 0,
              "id_switches": 0, "fragments": 0, "limitations": limits}
    last_match = {}
    visible_gap = set()
    for frame in scored:
        truth = [item for item in frame.objects if item.bbox is not None]
        predictions = frame.predictions
        scores = {(i, j): intersection_over_union(item.bbox, predicted.bbox)
                  for i, item in enumerate(truth) for j, predicted in enumerate(predictions)
                  if item.category == predicted.category and intersection_over_union(item.bbox, predicted.bbox) > .5}
        pairs = maximum_score_matching(len(truth), len(predictions), scores)
        result["matched_observations"] += len(pairs)
        result["missed_observations"] += len(truth)-len(pairs)
        result["false_positive_observations"] += len(predictions)-len(pairs)
        matched_indices = set()
        for i, j in pairs:
            identity, predicted_id = truth[i].identity, predictions[j].predicted_track_id
            matched_indices.add(i)
            if identity in last_match:
                result["id_switches"] += predicted_id != last_match[identity]
                result["fragments"] += identity in visible_gap
            last_match[identity] = predicted_id
            visible_gap.discard(identity)
        for i, item in enumerate(truth):
            if i not in matched_indices and item.identity in last_match:
                visible_gap.add(item.identity)
    return result
