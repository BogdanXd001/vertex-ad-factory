from unittest import TestCase

from vertex_ad_factory.stages.voiceover import (
    build_master_script,
    scene_timings_from_alignment,
)


class VoiceoverTests(TestCase):
    def test_master_script_preserves_scene_ranges_and_alignment(self) -> None:
        scenes = [
            {"scene_id": "s1", "position": 1, "narration": "Prima frază."},
            {"scene_id": "s2", "position": 2, "narration": "A doua frază."},
        ]
        text, ranges = build_master_script(scenes)
        characters = list(text)
        starts = [index * 0.05 for index in range(len(characters))]
        ends = [(index + 1) * 0.05 for index in range(len(characters))]

        timings = scene_timings_from_alignment(
            ranges,
            {
                "characters": characters,
                "character_start_times_seconds": starts,
                "character_end_times_seconds": ends,
            },
        )

        self.assertEqual(text, "Prima frază.\n\nA doua frază.")
        self.assertEqual(timings[0].start_seconds, 0.0)
        self.assertAlmostEqual(timings[0].end_seconds, 0.6)
        self.assertAlmostEqual(timings[1].start_seconds, 0.7)
        self.assertGreater(timings[1].duration_seconds, 0)

    def test_missing_narration_in_alignment_is_rejected(self) -> None:
        _, ranges = build_master_script(
            [{"scene_id": "s1", "position": 1, "narration": "Text exact."}]
        )
        with self.assertRaisesRegex(ValueError, "could not locate"):
            scene_timings_from_alignment(
                ranges,
                {
                    "characters": list("Alt text."),
                    "character_start_times_seconds": [0.0] * 9,
                    "character_end_times_seconds": [0.1] * 9,
                },
            )

