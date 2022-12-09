# coding=utf-8
# Copyright 2022 HuggingFace Inc.
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


import unittest

import numpy as np

from transformers.testing_utils import require_torch, require_vision
from transformers.utils import is_torch_available, is_vision_available

from ...test_feature_extraction_common import FeatureExtractionSavingTestMixin
from ...test_image_processing_common import prepare_video_inputs


if is_torch_available():
    import torch

if is_vision_available():
    from PIL import Image

    from transformers import VideoMAEImageProcessor


class VideoMAEImageProcessingTester(unittest.TestCase):
    def __init__(
        self,
        parent,
        batch_size=7,
        num_channels=3,
        num_frames=10,
        image_size=18,
        min_resolution=30,
        max_resolution=400,
        do_resize=True,
        size=None,
        do_normalize=True,
        image_mean=[0.5, 0.5, 0.5],
        image_std=[0.5, 0.5, 0.5],
        crop_size=None,
    ):
        size = size if size is not None else {"shortest_edge": 18}
        crop_size = crop_size if crop_size is not None else {"height": 18, "width": 18}

        self.parent = parent
        self.batch_size = batch_size
        self.num_channels = num_channels
        self.num_frames = num_frames
        self.image_size = image_size
        self.min_resolution = min_resolution
        self.max_resolution = max_resolution
        self.do_resize = do_resize
        self.size = size
        self.do_normalize = do_normalize
        self.image_mean = image_mean
        self.image_std = image_std
        self.crop_size = crop_size

    def prepare_image_processor_dict(self):
        return {
            "image_mean": self.image_mean,
            "image_std": self.image_std,
            "do_normalize": self.do_normalize,
            "do_resize": self.do_resize,
            "size": self.size,
            "crop_size": self.crop_size,
        }


@require_torch
@require_vision
class VideoMAEFeatureExtractionTest(FeatureExtractionSavingTestMixin, unittest.TestCase):

    image_processing_class = VideoMAEImageProcessor if is_vision_available() else None

    def setUp(self):
        self.image_processor_tester = VideoMAEImageProcessingTester(self)

    @property
    def image_processor_dict(self):
        return self.image_processor_tester.prepare_image_processor_dict()

    def test_image_processor_properties(self):
        image_processing = self.image_processing_class(**self.image_processor_dict)
        self.assertTrue(hasattr(image_processing, "image_mean"))
        self.assertTrue(hasattr(image_processing, "image_std"))
        self.assertTrue(hasattr(image_processing, "do_normalize"))
        self.assertTrue(hasattr(image_processing, "do_resize"))
        self.assertTrue(hasattr(image_processing, "do_center_crop"))
        self.assertTrue(hasattr(image_processing, "size"))

    def test_feat_extract_from_dict_with_kwargs(self):
        feature_extractor = self.feature_extraction_class.from_dict(self.feat_extract_dict)
        self.assertEqual(feature_extractor.size, {"shortest_edge": 18})
        self.assertEqual(feature_extractor.crop_size, {"height": 18, "width": 18})

        feature_extractor = self.feature_extraction_class.from_dict(self.feat_extract_dict, size=42, crop_size=84)
        self.assertEqual(feature_extractor.size, {"shortest_edge": 42})
        self.assertEqual(feature_extractor.crop_size, {"height": 84, "width": 84})

    def test_batch_feature(self):
        pass

    def test_call_pil(self):
        # Initialize image_processing
        image_processing = self.image_processing_class(**self.image_processor_dict)
        # create random PIL videos
        video_inputs = prepare_video_inputs(self.image_processor_tester, equal_resolution=False)
        for video in video_inputs:
            self.assertIsInstance(video, list)
            self.assertIsInstance(video[0], Image.Image)

        # Test not batched input
        encoded_videos = image_processing(video_inputs[0], return_tensors="pt").pixel_values
        self.assertEqual(
            encoded_videos.shape,
            (
                1,
                self.image_processor_tester.num_frames,
                self.image_processor_tester.num_channels,
                self.image_processor_tester.crop_size["height"],
                self.image_processor_tester.crop_size["width"],
            ),
        )

        # Test batched
        encoded_videos = image_processing(video_inputs, return_tensors="pt").pixel_values
        self.assertEqual(
            encoded_videos.shape,
            (
                self.image_processor_tester.batch_size,
                self.image_processor_tester.num_frames,
                self.image_processor_tester.num_channels,
                self.image_processor_tester.crop_size["height"],
                self.image_processor_tester.crop_size["width"],
            ),
        )

    def test_call_numpy(self):
        # Initialize image_processing
        image_processing = self.image_processing_class(**self.image_processor_dict)
        # create random numpy tensors
        video_inputs = prepare_video_inputs(self.image_processor_tester, equal_resolution=False, numpify=True)
        for video in video_inputs:
            self.assertIsInstance(video, list)
            self.assertIsInstance(video[0], np.ndarray)

        # Test not batched input
        encoded_videos = image_processing(video_inputs[0], return_tensors="pt").pixel_values
        self.assertEqual(
            encoded_videos.shape,
            (
                1,
                self.image_processor_tester.num_frames,
                self.image_processor_tester.num_channels,
                self.image_processor_tester.crop_size["height"],
                self.image_processor_tester.crop_size["width"],
            ),
        )

        # Test batched
        encoded_videos = image_processing(video_inputs, return_tensors="pt").pixel_values
        self.assertEqual(
            encoded_videos.shape,
            (
                self.image_processor_tester.batch_size,
                self.image_processor_tester.num_frames,
                self.image_processor_tester.num_channels,
                self.image_processor_tester.crop_size["height"],
                self.image_processor_tester.crop_size["width"],
            ),
        )

    def test_call_pytorch(self):
        # Initialize image_processing
        image_processing = self.image_processing_class(**self.image_processor_dict)
        # create random PyTorch tensors
        video_inputs = prepare_video_inputs(self.image_processor_tester, equal_resolution=False, torchify=True)
        for video in video_inputs:
            self.assertIsInstance(video, list)
            self.assertIsInstance(video[0], torch.Tensor)

        # Test not batched input
        encoded_videos = image_processing(video_inputs[0], return_tensors="pt").pixel_values
        self.assertEqual(
            encoded_videos.shape,
            (
                1,
                self.image_processor_tester.num_frames,
                self.image_processor_tester.num_channels,
                self.image_processor_tester.crop_size["height"],
                self.image_processor_tester.crop_size["width"],
            ),
        )

        # Test batched
        encoded_videos = image_processing(video_inputs, return_tensors="pt").pixel_values
        self.assertEqual(
            encoded_videos.shape,
            (
                self.image_processor_tester.batch_size,
                self.image_processor_tester.num_frames,
                self.image_processor_tester.num_channels,
                self.image_processor_tester.crop_size["height"],
                self.image_processor_tester.crop_size["width"],
            ),
        )
