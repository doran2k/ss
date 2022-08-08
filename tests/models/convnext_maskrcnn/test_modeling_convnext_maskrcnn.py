# coding=utf-8
# Copyright 2022 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Testing suite for the PyTorch ConvNextMaskRCNN model. """


import inspect
import unittest

import numpy as np

from huggingface_hub import hf_hub_download
from transformers import ConvNextMaskRCNNConfig
from transformers.testing_utils import require_torch, require_vision, slow, torch_device
from transformers.utils import is_torch_available, is_vision_available

from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin, floats_tensor, ids_tensor


if is_torch_available():
    import torch
    import torchvision.transforms as T

    from transformers import ConvNextMaskRCNNForObjectDetection, ConvNextMaskRCNNModel
    from transformers.models.convnext_maskrcnn.modeling_convnext_maskrcnn import (
        CONVNEXTMASKRCNN_PRETRAINED_MODEL_ARCHIVE_LIST,
    )


if is_vision_available():
    from PIL import Image


class ConvNextMaskRCNNModelTester:
    def __init__(
        self,
        parent,
        batch_size=13,
        image_size=32,
        num_channels=3,
        num_stages=4,
        hidden_sizes=[10, 20, 30, 40],
        depths=[2, 2, 3, 2],
        is_training=True,
        use_labels=True,
        intermediate_size=37,
        hidden_act="gelu",
        type_sequence_label_size=10,
        initializer_range=0.02,
        num_labels=3,
        scope=None,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.image_size = image_size
        self.num_channels = num_channels
        self.num_stages = num_stages
        self.hidden_sizes = hidden_sizes
        self.depths = depths
        self.is_training = is_training
        self.use_labels = use_labels
        self.intermediate_size = intermediate_size
        self.hidden_act = hidden_act
        self.type_sequence_label_size = type_sequence_label_size
        self.initializer_range = initializer_range
        self.scope = scope

    def prepare_config_and_inputs(self):
        pixel_values = floats_tensor([self.batch_size, self.num_channels, self.image_size, self.image_size])

        labels = None
        if self.use_labels:
            labels = ids_tensor([self.batch_size], self.type_sequence_label_size)

        config = self.get_config()

        return config, pixel_values, labels

    def get_config(self):
        return ConvNextMaskRCNNConfig(
            num_channels=self.num_channels,
            hidden_sizes=self.hidden_sizes,
            depths=self.depths,
            num_stages=self.num_stages,
            hidden_act=self.hidden_act,
            is_decoder=False,
            initializer_range=self.initializer_range,
        )

    def create_and_check_model(self, config, pixel_values, labels):
        model = ConvNextMaskRCNNModel(config=config)
        model.to(torch_device)
        model.eval()
        result = model(pixel_values)
        # expected last hidden states: B, C, H // 32, W // 32
        self.parent.assertEqual(
            result.last_hidden_state.shape,
            (self.batch_size, self.hidden_sizes[-1], self.image_size // 32, self.image_size // 32),
        )

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, pixel_values, labels = config_and_inputs
        inputs_dict = {"pixel_values": pixel_values}
        return config, inputs_dict


@require_torch
class ConvNextMaskRCNNModelTest(ModelTesterMixin, unittest.TestCase):
    """
    Here we also overwrite some of the tests of test_modeling_common.py, as ConvNextMaskRCNN does not use input_ids, inputs_embeds,
    attention_mask and seq_length.
    """

    all_model_classes = (
        (
            ConvNextMaskRCNNModel,
            ConvNextMaskRCNNForObjectDetection,
        )
        if is_torch_available()
        else ()
    )

    test_pruning = False
    test_resize_embeddings = False
    test_head_masking = False
    has_attentions = False

    def setUp(self):
        self.model_tester = ConvNextMaskRCNNModelTester(self)
        self.config_tester = ConfigTester(
            self, config_class=ConvNextMaskRCNNConfig, has_text_modality=False, hidden_size=37
        )

    def test_config(self):
        self.create_and_test_config_common_properties()
        self.config_tester.create_and_test_config_to_json_string()
        self.config_tester.create_and_test_config_to_json_file()
        self.config_tester.create_and_test_config_from_and_save_pretrained()
        self.config_tester.create_and_test_config_with_num_labels()
        self.config_tester.check_config_can_be_init_without_params()
        self.config_tester.check_config_arguments_init()

    def create_and_test_config_common_properties(self):
        return

    @unittest.skip(reason="ConvNextMaskRCNN does not output attentions")
    def test_attention_outputs(self):
        pass

    @unittest.skip(reason="ConvNextMaskRCNN does not use inputs_embeds")
    def test_inputs_embeds(self):
        pass

    @unittest.skip(reason="ConvNextMaskRCNN does not support input and output embeddings")
    def test_model_common_attributes(self):
        pass

    def test_forward_signature(self):
        config, _ = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            signature = inspect.signature(model.forward)
            # signature.parameters is an OrderedDict => so arg_names order is deterministic
            arg_names = [*signature.parameters.keys()]

            expected_arg_names = ["pixel_values"]
            self.assertListEqual(arg_names[:1], expected_arg_names)

    def test_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model(*config_and_inputs)

    def test_hidden_states_output(self):
        def check_hidden_states_output(inputs_dict, config, model_class):
            model = model_class(config)
            model.to(torch_device)
            model.eval()

            with torch.no_grad():
                outputs = model(**self._prepare_for_class(inputs_dict, model_class))

            hidden_states = outputs.encoder_hidden_states if config.is_encoder_decoder else outputs.hidden_states

            expected_num_stages = self.model_tester.num_stages
            self.assertEqual(len(hidden_states), expected_num_stages + 1)

            # ConvNextMaskRCNN's feature maps are of shape (batch_size, num_channels, height, width)
            self.assertListEqual(
                list(hidden_states[0].shape[-2:]),
                [self.model_tester.image_size // 4, self.model_tester.image_size // 4],
            )

        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            inputs_dict["output_hidden_states"] = True
            check_hidden_states_output(inputs_dict, config, model_class)

            # check that output_hidden_states also work using config
            del inputs_dict["output_hidden_states"]
            config.output_hidden_states = True

            check_hidden_states_output(inputs_dict, config, model_class)

    def test_for_image_classification(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_for_image_classification(*config_and_inputs)

    @slow
    def test_model_from_pretrained(self):
        for model_name in CONVNEXTMASKRCNN_PRETRAINED_MODEL_ARCHIVE_LIST[:1]:
            model = ConvNextMaskRCNNModel.from_pretrained(model_name)
            self.assertIsNotNone(model)


# We will verify our results on an image of cute cats
def prepare_img():
    image = Image.open("./tests/fixtures/tests_samples/COCO/000000039769.png")
    return image


@require_torch
@require_vision
class ConvNextMaskRCNNModelIntegrationTest(unittest.TestCase):
    @slow
    def test_inference_object_detection_head(self):
        # TODO update to appropriate organization
        model = ConvNextMaskRCNNForObjectDetection.from_pretrained("nielsr/convnext-tiny-maskrcnn").to(torch_device)

        # TODO use feature extractor instead?
        transforms = T.Compose(
            [T.Resize(800), T.ToTensor(), T.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225))]
        )

        image = prepare_img()
        pixel_values = transforms(image).unsqueeze(0).to(torch_device)
        img_metas = [
            dict(
                img_shape=(800, 1067, 3),
                scale_factor=np.array([1.6671875, 1.6666666, 1.6671875, 1.6666666], dtype=np.float32),
                ori_shape=(480, 640, 3),
            )
        ]

        # forward pass
        with torch.no_grad():
            outputs = model(pixel_values, img_metas=img_metas)
            bbox_results = outputs.results[0][0]

        # verify the results
        self.assertEqual(len(bbox_results), 80)

        expected_slice = np.array(
            [
                [17.905682, 55.41647, 318.95575, 470.2593, 0.9981325],
                [336.97797, 18.415943, 632.41956, 381.94666, 0.99591476],
            ],
            dtype=np.float32,
        )
        self.assertTrue(np.allclose(bbox_results[15], expected_slice, atol=1e-4))

    @slow
    def test_training_object_detection_head(self):
        # TODO update to appropriate organization
        model = ConvNextMaskRCNNForObjectDetection.from_pretrained("nielsr/convnext-tiny-maskrcnn").to(torch_device)

        # TODO use feature extractor instead?
        local_path = hf_hub_download(repo_id="nielsr/init-files", filename="pixel_values.pt")
        img = torch.load(local_path).unsqueeze(0)
        img_metas = [
            {
                "filename": "./drive/MyDrive/ConvNeXT MaskRCNN/COCO/val2017/000000039769.jpg",
                "ori_filename": "000000039769.jpg",
                "ori_shape": (480, 640, 3),
                "img_shape": (480, 640, 3),
                "pad_shape": (480, 640, 3),
                "scale_factor": np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32),
                "flip": False,
                "flip_direction": None,
                "img_norm_cfg": {
                    "mean": np.array([123.675, 116.28, 103.53], dtype=np.float32),
                    "std": np.array([58.395, 57.12, 57.375], dtype=np.float32),
                    "to_rgb": True,
                },
            },
            {
                "filename": "./drive/MyDrive/ConvNeXT MaskRCNN/COCO/val2017/000000039769.jpg",
                "ori_filename": "000000039769.jpg",
                "ori_shape": (480, 640, 3),
                "img_shape": (704, 939, 3),
                "pad_shape": (704, 960, 3),
                "scale_factor": np.array([1.4671875, 1.4666667, 1.4671875, 1.4666667], dtype=np.float32),
                "flip": False,
                "flip_direction": None,
                "img_norm_cfg": {
                    "mean": np.array([123.675, 116.28, 103.53], dtype=np.float32),
                    "std": np.array([58.395, 57.12, 57.375], dtype=np.float32),
                    "to_rgb": True,
                },
            },
        ]

        labels = dict()
        local_path = hf_hub_download(repo_id="nielsr/init-files", filename="boxes.pt")
        labels["gt_bboxes"] = [torch.load(local_path).to(torch_device)]
        local_path = hf_hub_download(repo_id="nielsr/init-files", filename="labels.pt")
        labels["gt_labels"] = [torch.load(local_path).to(torch_device)]
        local_path = hf_hub_download(repo_id="nielsr/init-files", filename="masks.pt")
        labels["gt_masks"] = [torch.load(local_path).to(torch_device)]
        labels["gt_bboxes_ignore"] = None
        img_metas = [{"pad_shape": img.shape[::-1], "img_shape": img.shape[::-1]}]

        # forward pass
        with torch.no_grad():
            outputs = model(img.to(torch_device), img_metas=img_metas, labels=labels)
            losses = outputs.losses

        # TODO verify the results
        print(losses)
        raise NotImplementedError("To do")
