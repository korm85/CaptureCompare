import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from depthcapture.pipeline import Config, prepare, remove_reflections  # noqa: E402
from depthcapture.specular import intra_frame_mask  # noqa: E402
from depthcapture.synth import make_sequence  # noqa: E402


@pytest.fixture(scope="module")
def seq():
    return make_sequence(n=4, seed=3)


@pytest.fixture(scope="module")
def loftr():
    from depthcapture.align import EfficientLoFTRMatcher

    return EfficientLoFTRMatcher()


def test_efficientloftr_decoding_on_known_warp(seq, loftr):
    """Regression for the transformers post-processing bug (keypoints paired by
    position instead of by match index): matches must follow a known warp."""
    img = seq[0][1]
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 6, 1.05)
    warped = cv2.warpAffine(img, M, (w, h))
    k0, k1, _ = loftr(img, warped)
    err = np.linalg.norm(k0 @ M[:, :2].T + M[:, 2] - k1, axis=1)
    assert len(k0) > 500
    assert np.median(err) < 6.0


def test_detector_ignores_clean_enamel(seq):
    frames, gt, spec_gt, mouth, ri = seq
    ref = prepare(frames)[ri]
    p = intra_frame_mask(ref) > 0.5
    precision = (p & spec_gt & mouth).sum() / max((p & mouth).sum(), 1)
    recall = (p & spec_gt & mouth).sum() / (spec_gt & mouth).sum()
    assert precision > 0.5 and recall > 0.4
    assert p[mouth & ~spec_gt].mean() < 0.05


def test_pipeline_reduces_glare(seq, loftr):
    frames, gt, spec_gt, mouth, ri = seq
    imgs = prepare(frames)
    r = remove_reflections(imgs, Config(reference=ri, use_roi=False), matcher=loftr)
    hl = spec_gt & mouth
    err_in = np.abs(imgs[ri] - gt)[hl].mean()
    err_out = np.abs(r.output - gt)[hl].mean()
    assert err_out < 0.85 * err_in
    clean = mouth & ~cv2.dilate(spec_gt.astype(np.uint8), np.ones((7, 7))).astype(bool)
    assert np.abs(r.output - imgs[ri])[clean].mean() < 0.02  # clean pixels mostly untouched
