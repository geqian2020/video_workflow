import numpy as np
import pytest

from video_workflow.extract import crop_box, find_segments


def test_scene_candidates_preserve_revisited_slides():
    class Clip:
        duration = 6

        def get_frame(self, t):
            value = 0 if t < 2 or t >= 4 else 255
            return np.full((90, 160, 3), value, dtype=np.uint8)

    assert find_segments(Clip(), (0, 0, 160, 90)) == [(0, 2), (2, 4), (4, 6)]


def test_crop_rejects_out_of_bounds():
    with pytest.raises(ValueError):
        crop_box((0.5, 0, 0.7, 1), (1920, 1080))
    assert crop_box((0, 0, 0.75, 1), (1920, 1080)) == (0, 0, 1440, 1080)
