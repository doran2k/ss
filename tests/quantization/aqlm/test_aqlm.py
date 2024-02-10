# coding=utf-8
# Copyright 2024 The HuggingFace Team. All rights reserved.
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

import gc
import tempfile
import unittest

from transformers import AqlmConfig, AutoConfig, AutoModelForCausalLM, AutoTokenizer, OPTForCausalLM
from transformers.testing_utils import (
    require_accelerate,
    require_aqlm,
    require_torch_gpu,
    require_torch_multi_gpu,
    slow,
    torch_device,
)
from transformers.utils import is_accelerate_available, is_torch_available


if is_torch_available():
    import torch

if is_accelerate_available():
    from accelerate import init_empty_weights


@require_torch_gpu
class AqlmConfigTest(unittest.TestCase):
    def test_to_dict(self):
        """
        Simple test that checks if one uses a config and converts it to a dict, the dict is the same as the config object
        """
        quantization_config = AqlmConfig()
        config_to_dict = quantization_config.to_dict()

        for key in config_to_dict:
            self.assertEqual(getattr(quantization_config, key), config_to_dict[key])

    def test_from_dict(self):
        """
        Simple test that checks if one uses a dict and converts it to a config object, the config object is the same as the dict
        """
        dict = {
            "in_group_size": 32,
            "num_codebooks": 8,
            "nbits_per_codebook": 8,
            "linear_weights_not_to_quantize": ["lm_head.weight"],
        }
        quantization_config = AqlmConfig.from_dict(dict)

        self.assertEqual(dict["in_group_size"], quantization_config.in_group_size)
        self.assertEqual(dict["num_codebooks"], quantization_config.num_codebooks)
        self.assertEqual(dict["nbits_per_codebook"], quantization_config.nbits_per_codebook)
        self.assertEqual(dict["linear_weights_not_to_quantize"], quantization_config.linear_weights_not_to_quantize)


@slow
@require_torch_gpu
@require_aqlm
@require_accelerate
class AqlmTest(unittest.TestCase):
    model_name = "BlackSamorez/Mixtral-8x7b-AQLM-2Bit-1x16-hf-test-dispatch"

    input_text = "Hello my name is"

    EXPECTED_OUTPUT = "Hello my name is TODO"

    device_map = "cuda"

    # called only once for all test in this class
    @classmethod
    def setUpClass(cls):
        """
        Setup quantized model
        """
        cls.tokenizer = AutoTokenizer.from_pretrained(cls.model_name)
        cls.quantized_model = AutoModelForCausalLM.from_pretrained(
            cls.model_name,
            device_map=cls.device_map,
        )

    def tearDown(self):
        gc.collect()
        torch.cuda.empty_cache()
        gc.collect()

    def test_quantized_model_conversion(self):
        """
        Simple test that checks if the quantized model has been converted properly
        """
        from aqlm import QuantizedLinear
        from transformers.integrations import replace_with_aqlm_linear

        model_id = "facebook/opt-350m"
        config = AutoConfig.from_pretrained(model_id, revision="cb32f77e905cccbca1d970436fb0f5e6b58ee3c5")
        quantization_config = AqlmConfig()

        with init_empty_weights():
            model = OPTForCausalLM(config)

        nb_linears = 0
        for module in model.modules():
            if isinstance(module, torch.nn.Linear):
                nb_linears += 1

        model, _ = replace_with_aqlm_linear(model, quantization_config=quantization_config)
        nb_aqlm_linear = 0
        for module in model.modules():
            if isinstance(module, QuantizedLinear):
                nb_aqlm_linear += 1

        self.assertEqual(nb_linears, nb_aqlm_linear)

        # Try with `linear_weights_not_to_quantize`
        with init_empty_weights():
            model = OPTForCausalLM(config)

        model, _ = replace_with_aqlm_linear(
            model, quantization_config=quantization_config, linear_weights_not_to_quantize=["lm_head.weight"]
        )
        nb_aqlm_linear = 0
        for module in model.modules():
            if isinstance(module, QuantizedLinear):
                nb_aqlm_linear += 1

        self.assertEqual(nb_linears - 1, nb_aqlm_linear)

    def test_quantized_model(self):
        """
        Simple test that checks if the quantized model is working properly
        """
        input_ids = self.tokenizer(self.input_text, return_tensors="pt").to(torch_device)

        output = self.quantized_model.generate(**input_ids, max_new_tokens=40)
        self.assertEqual(self.tokenizer.decode(output[0], skip_special_tokens=True), self.EXPECTED_OUTPUT)

    def test_raise_if_non_quantized(self):
        model_id = "facebook/opt-125m"
        quantization_config = AqlmConfig(bits=4)

        with self.assertRaises(ValueError):
            _ = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=quantization_config)

    def test_save_pretrained(self):
        """
        Simple test that checks if the quantized model is working properly after being saved and loaded
        """
        with tempfile.TemporaryDirectory() as tmpdirname:
            self.quantized_model.save_pretrained(tmpdirname)
            model = AutoModelForCausalLM.from_pretrained(tmpdirname, device_map=self.device_map)

            input_ids = self.tokenizer(self.input_text, return_tensors="pt").to(torch_device)

            output = model.generate(**input_ids, max_new_tokens=40)
            self.assertEqual(self.tokenizer.decode(output[0], skip_special_tokens=True), self.EXPECTED_OUTPUT)

    @require_torch_multi_gpu
    def test_quantized_model_multi_gpu(self):
        """
        Simple test that checks if the quantized model is working properly with multiple GPUs
        """
        input_ids = self.tokenizer(self.input_text, return_tensors="pt").to(torch_device)

        quantized_model = AutoModelForCausalLM.from_pretrained(self.model_name, device_map="auto")

        self.assertTrue(set(quantized_model.hf_device_map.values()) == {0, 1, 2, 3})

        output = quantized_model.generate(**input_ids, max_new_tokens=40)

        self.assertEqual(self.tokenizer.decode(output[0], skip_special_tokens=True), self.EXPECTED_OUTPUT)
