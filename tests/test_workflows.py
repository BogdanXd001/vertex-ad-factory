from unittest import TestCase

from vertex_ad_factory.services.workflows import (
    BrollFirstFrameBindings,
    FirstFrameBindings,
    bind_broll_first_frame,
    bind_first_frame,
)


def workflow_fixture() -> dict:
    return {
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
        "7": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512},
        },
        "8": {"class_type": "KSampler", "inputs": {"seed": 1}},
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": "old"}},
        "11": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
    }


class WorkflowBindingTests(TestCase):
    def test_first_frame_values_are_bound_without_mutating_template(self) -> None:
        template = workflow_fixture()
        rendered, seed = bind_first_frame(
            template,
            FirstFrameBindings(
                prompt="New presenter prompt",
                reference_image="presenters/a1.png",
                output_prefix="jobs/demo/scene_01",
                width=832,
                height=1216,
                seed=42,
            ),
        )

        self.assertEqual(seed, 42)
        self.assertEqual(rendered["4"]["inputs"]["text"], "New presenter prompt")
        self.assertEqual(rendered["8"]["inputs"]["seed"], 42)
        self.assertEqual(rendered["10"]["inputs"]["filename_prefix"], "jobs/demo/scene_01")
        self.assertEqual(template["4"]["inputs"]["text"], "old")

    def test_unsafe_reference_path_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            bind_first_frame(
                workflow_fixture(),
                FirstFrameBindings(prompt="valid", reference_image="../secret.png"),
            )

    def test_broll_uses_base_flux_without_pulid_nodes(self) -> None:
        template = workflow_fixture()
        template["1"] = {"class_type": "UNETLoader", "inputs": {}}
        template["8"]["inputs"]["model"] = ["1", 0]
        template.pop("11")

        rendered, seed = bind_broll_first_frame(
            template,
            BrollFirstFrameBindings(
                prompt="Macro skin hydration animation",
                output_prefix="jobs/demo/scene_02",
                width=720,
                height=1280,
                seed=99,
            ),
        )

        self.assertEqual(seed, 99)
        self.assertEqual(rendered["8"]["inputs"]["model"], ["1", 0])
        self.assertEqual(rendered["4"]["inputs"]["text"], "Macro skin hydration animation")
        self.assertNotIn("11", rendered)

