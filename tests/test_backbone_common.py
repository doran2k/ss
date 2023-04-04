# coding=utf-8
# Copyright 2023 The HuggingFace Inc. team. All rights reserved.
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

import copy
import inspect

from transformers.testing_utils import require_torch, torch_device


@require_torch
class BackboneTesterMixin:
    all_model_classes = ()
    has_attentions = True
    is_training = False
    test_pruning = False
    test_resize_embeddings = False
    test_head_masking = False

    def test_forward_signature(self):
        config, _ = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            signature = inspect.signature(model.forward)
            # signature.parameters is an OrderedDict => so arg_names order is deterministic
            arg_names = [*signature.parameters.keys()]
            expected_arg_names = ["pixel_values"]
            self.assertListEqual(arg_names[:1], expected_arg_names)

    def test_channels(self):
        config, _ = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            num_features = model.num_features
            self.assertEqual(len(model.channels), len(config.out_features))
            self.assertListEqual(model.channels, num_features[1 : len(config.out_features) + 1])

            config.out_features = None
            config.out_indices = None
            model = model_class(config)
            self.assertEqual(len(model.channels), 1)
            self.assertListEqual(model.channels, [num_features[-1]])

    def test_create_from_modified_config(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            model.to(torch_device)
            model.eval()
            result = model(**inputs_dict)

            self.assertEqual(len(result.feature_maps), len(config.out_features))
            self.assertEqual(len(model.channels), len(config.out_features))

            # Check output of last stage is taken if out_features=None, out_indices=None
            modified_config = copy.deepcopy(config)
            modified_config.out_features = None
            modified_config.out_indices = None
            model = model_class(modified_config)
            model.to(torch_device)
            model.eval()
            result = model(**inputs_dict)

            self.assertEqual(len(result.feature_maps), 1)
            self.assertEqual(len(model.channels), 1)

            # Check backbone can be initialized with fresh weights
            modified_config = copy.deepcopy(config)
            modified_config.use_pretrained_backbone = False
            model = model_class(modified_config)
            model.to(torch_device)
            model.eval()
            result = model(**inputs_dict)

    def test_backbone_common_attributes(self):
        config, _ = self.model_tester.prepare_config_and_inputs_for_common()

        for backbone_class in self.all_model_classes:
            backbone = backbone_class(config)

            self.assertTrue(hasattr(backbone, "stage_names"))
            self.assertTrue(hasattr(backbone, "num_features"))
            self.assertTrue(hasattr(backbone, "out_indices"))
            self.assertTrue(hasattr(backbone, "out_features"))
            self.assertTrue(hasattr(backbone, "out_feature_channels"))
            self.assertTrue(hasattr(backbone, "channels"))

            # Verify num_features has been initialized in the backbone init
            self.assertIsNotNone(backbone.num_features)
            self.assertTrue(len(backbone.channels) == len(backbone.out_indices))
            self.assertTrue(len(backbone.stage_names) == len(backbone.num_features))
            self.assertTrue(len(backbone.channels) <= len(backbone.num_features))
            self.assertTrue(len(backbone.out_feature_channels) == len(backbone.stage_names))

    def test_backbone_outputs(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        batch_size = inputs_dict["pixel_values"].shape[0]

        for backbone_class in self.all_model_classes:
            backbone = backbone_class(config)
            backbone.to(torch_device)
            backbone.eval()

            outputs = backbone(**inputs_dict)

            # Test default outputs and verify feature maps
            self.assertIsInstance(outputs.feature_maps, tuple)
            self.assertTrue(len(outputs.feature_maps) == len(backbone.channels))
            for feature_map, n_channels in zip(outputs.feature_maps, backbone.channels):
                self.assertTrue(feature_map.shape[:2], (batch_size, n_channels))
            self.assertIsNone(outputs.hidden_states)
            self.assertIsNone(outputs.attentions)

            # Test output_hidden_states=True
            outputs = backbone(**inputs_dict, output_hidden_states=True)
            self.assertIsNotNone(outputs.hidden_states)
            self.assertTrue(len(outputs.hidden_states), len(backbone.stage_names))
            for hidden_state, n_channels in zip(outputs.hidden_states, backbone.channels):
                self.assertTrue(hidden_state.shape[:2], (batch_size, n_channels))

            # Test output_attentions=True
            if self.has_attentions:
                outputs = backbone(**inputs_dict, output_attentions=True)
                self.assertIsNotNone(outputs.attentions)
