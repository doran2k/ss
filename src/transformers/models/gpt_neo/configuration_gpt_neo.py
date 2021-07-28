# coding=utf-8
# Copyright 2021 The HuggingFace Inc. team. All rights reserved.
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
""" GPT Neo model configuration """

from collections import OrderedDict
from typing import Any, Mapping, Optional

from ... import PreTrainedTokenizer, TensorType, is_torch_available
from ...configuration_utils import PretrainedConfig
from ...onnx import OnnxConfigWithPast
from ...utils import logging


logger = logging.get_logger(__name__)

GPT_NEO_PRETRAINED_CONFIG_ARCHIVE_MAP = {
    "EleutherAI/gpt-neo-1.3B": "https://huggingface.co/EleutherAI/gpt-neo-1.3B/resolve/main/config.json",
    # See all GPTNeo models at https://huggingface.co/models?filter=gpt_neo
}


class GPTNeoConfig(PretrainedConfig):
    r"""
    This is the configuration class to store the configuration of a :class:`~transformers.GPTNeoModel`. It is used to
    instantiate a GPT Neo model according to the specified arguments, defining the model architecture. Instantiating a
    configuration with the defaults will yield a similar configuration to that of the GPTNeo `gpt-neo-1.3B
    <https://huggingface.co/EleutherAI/gpt-neo-1.3B>`__ architecture.

    Configuration objects inherit from :class:`~transformers.PretrainedConfig` and can be used to control the model
    outputs. Read the documentation from :class:`~transformers.PretrainedConfig` for more information.


    Args:
        vocab_size (:obj:`int`, `optional`, defaults to 50257):
            Vocabulary size of the GPT Neo model. Defines the number of different tokens that can be represented by the
            :obj:`inputs_ids` passed when calling :class:`~transformers.GPTNeoModel`. Vocabulary size of the model.
            Defines the different tokens that can be represented by the `inputs_ids` passed to the forward method of
            :class:`~transformers.GPTNeoModel`.
        attention_types (:obj:`List`, `optional`, defaults to :obj:`[[["global", "local"], 12]]`):
            The type of attention for each layer in a :obj:`List` of the following format :obj:`[[["attention_type"],
            num_layerss]]` e.g. for a 24 layer model :obj:`[[["global"], 24]]` or :obj:`[[["global", "local"], 12]]`
            Choose the value of ``attention_type`` from :obj:`["global", "local"]`
        hidden_size (:obj:`int`, `optional`, defaults to 2048):
            Dimensionality of the encoder layers and the pooler layer.
        num_layers (:obj:`int`, `optional`, defaults to 24):
            Number of hidden layers in the Transformer encoder.
        num_heads (:obj:`int`, `optional`, defaults to 16):
            Number of attention heads for each attention layer in the Transformer encoder.
        intermediate_size (:obj:`int`, `optional`, defaults to 8192):
            Dimensionality of the "intermediate" (i.e., feed-forward) layer in the Transformer encoder.
        activation_function (:obj:`str` or :obj:`function`, `optional`, defaults to :obj:`"gelu_new"`):
            The non-linear activation function (function or string) in the encoder and pooler. If string,
            :obj:`"gelu"`, :obj:`"relu"`, :obj:`"selu"` and :obj:`"gelu_new"` are supported.
        embed_dropout (:obj:`float`, `optional`, defaults to 0.0):
            The dropout probabilitiy for all fully connected layers in the embeddings, encoder, and pooler.
        attention_dropout (:obj:`float`, `optional`, defaults to 0.0):
            The dropout ratio for the attention probabilities.
        max_position_embeddings (:obj:`int`, `optional`, defaults to 2048):
            The maximum sequence length that this model might ever be used with. Typically set this to something large
            just in case (e.g., 512 or 1024 or 2048).
        type_vocab_size (:obj:`int`, `optional`, defaults to 2):
            The vocabulary size of the :obj:`token_type_ids` passed when calling :class:`~transformers.GPTNeoModel`.
        initializer_range (:obj:`float`, `optional`, defaults to 0.02):
            The standard deviation of the truncated_normal_initializer for initializing all weight matrices.
        layer_norm_epsilon (:obj:`float`, `optional`, defaults to 1e-5):
            The epsilon used by the layer normalization layers.
        use_cache (:obj:`bool`, `optional`, defaults to :obj:`True`):
            Whether or not the model should return the last key/values attentions (not used by all models). Only
            relevant if ``config.is_decoder=True``.
        gradient_checkpointing (:obj:`bool`, `optional`, defaults to :obj:`False`):
            If True, use gradient checkpointing to save memory at the expense of slower backward pass.

        Example::

            >>> from transformers import GPTNeoModel, GPTNeoConfig

            >>> # Initializing a GPTNeo EleutherAI/gpt-neo-1.3B style configuration
            >>> configuration = GPTNeoConfig()

            >>> # Initializing a model from the EleutherAI/gpt-neo-1.3B style configuration
            >>> model = GPTNeoModel(configuration)

            >>> # Accessing the model configuration
            >>> configuration = model.config
    """
    model_type = "gpt_neo"

    def __init__(
        self,
        vocab_size=50257,
        max_position_embeddings=2048,
        hidden_size=2048,
        num_layers=24,
        attention_types=[[["global", "local"], 12]],
        num_heads=16,
        intermediate_size=None,
        window_size=256,
        activation_function="gelu_new",
        resid_dropout=0.0,
        embed_dropout=0.0,
        attention_dropout=0.0,
        layer_norm_epsilon=1e-5,
        initializer_range=0.02,
        summary_type="cls_index",
        summary_use_proj=True,
        summary_activation=None,
        summary_proj_to_labels=True,
        summary_first_dropout=0.1,
        gradient_checkpointing=False,
        use_cache=True,
        bos_token_id=50256,
        eos_token_id=50256,
        **kwargs
    ):
        super().__init__(bos_token_id=bos_token_id, eos_token_id=eos_token_id, **kwargs)

        self.vocab_size = vocab_size
        self.max_position_embeddings = max_position_embeddings
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.num_heads = num_heads
        self.intermediate_size = intermediate_size
        self.window_size = window_size
        self.activation_function = activation_function
        self.resid_dropout = resid_dropout
        self.embed_dropout = embed_dropout
        self.attention_dropout = attention_dropout
        self.layer_norm_epsilon = layer_norm_epsilon
        self.initializer_range = initializer_range
        self.summary_type = summary_type
        self.summary_use_proj = summary_use_proj
        self.summary_activation = summary_activation
        self.summary_first_dropout = summary_first_dropout
        self.summary_proj_to_labels = summary_proj_to_labels
        self.gradient_checkpointing = gradient_checkpointing
        self.use_cache = use_cache

        self.bos_token_id = bos_token_id
        self.eos_token_id = eos_token_id

        self.attention_types = attention_types
        self.attention_layers = self.expand_attention_types_params(attention_types)

        if len(self.attention_layers) != self.num_layers:
            raise ValueError(
                "Configuration for convolutional module is incorrect."
                "It is required that `len(config.attention_layers)` == `config.num_layers`"
                f"but is `len(config.attention_layers) = {len(self.attention_layers)}`,"
                f"`config.num_layers = {self.num_layers}`."
                "`config.attention_layers` is prepared using `config.attention_types`."
                "Please verify the value of `config.attention_types` argument."
            )

    @staticmethod
    def expand_attention_types_params(attention_types):
        attentions = []
        for item in attention_types:
            for _ in range(item[1]):
                attentions.extend(item[0])
        return attentions

    @property
    def num_attention_heads(self):
        return self.num_heads

    @property
    def num_hidden_layers(self):
        return self.num_layers


def custom_unfold(input, dimension, size, step):
    """Custom torch.Tensor.unfold implementation to enable export to ONNX."""
    import torch
    shape = input.size()
    rank = len(shape)
    sizedim = shape[dimension]
    low_indices = torch.arange(0, sizedim, step)
    hi_indices = torch.arange(size, sizedim + 1, step)
    min_length = (sizedim - size) // step + 1
    # print("low_indices", low_indices)
    # print("hi_indices", hi_indices)
    # print("min_length", min_length)
    # hi_indices = hi_indices[:min_length]
    # import pdb; pdb.set_trace()
    # indices = torch.stack([low_indices, hi_indices], dim=1)
    # indices = indices[:, :, None]
    # print("low_indices", low_indices)
    # print("hi_indices", hi_indices)
    it = list(zip(range(0, sizedim, step), range(size, sizedim + 1, step)))
    supposed_indices = torch.stack(
        [torch.arange(start=lo, end=hi) for (lo, hi) in it],
        dim=0
    )
    print(supposed_indices)
    # print("supposed indices", supposed_indices)
    indices = torch.arange(size) + low_indices[:min_length][:, None]
    print(indices)

    #indices = indices[:min_length]
    # print(indices)
    # print(supposed_indices)
    print("matching", torch.all(indices == supposed_indices))
    # stack = input[torch.arange(indices.shape[0])[:, None] , :]
    s = [slice(None)] * rank
    s[dimension] = indices
    sliced = input[s]
    print("input shape", input.shape)
    print("indices shape", indices.shape)
    print("sliced shape", sliced.shape)
    # print(stack, stack.shape)
    stack = []
    for t in it:
        s = [slice(None)] * rank
        s[dimension] = slice(t[0], t[1])
        stack.append(input[s])
        # stack.append(torch.narrow(input, dim=dimension, start=t[0], length=t[1]-t[0]))
    print("stack shape", len(stack), stack[0].shape)
    perm = list(range(0, rank))
    sliced_perm = list(range(0, rank + 1))
    perm.append(perm.pop(dimension))
    sliced_perm.append(sliced_perm.pop(dimension + 1))
    print("perm", perm)
    print("sliced perm", perm)
    # stack = stack.permute(perm)
    unsqueeze = [t.permute(perm).unsqueeze(dimension) for t in stack]
    ready_sliced = sliced.permute(sliced_perm)
    print("unsqueeze shape", unsqueeze[0].shape)
    print("ready_sliced shape", ready_sliced.shape)
    res = torch.cat(unsqueeze, dim=dimension)
    print("res shape", res.shape)
    return ready_sliced
    return torch.cat(unsqueeze, dim=dimension)


class GPTNeoOnnxConfig(OnnxConfigWithPast):
    def __init__(self, config: PretrainedConfig, task: str = "default", use_past: bool = False):
        if is_torch_available():
            import torch

            patching_specs = [(torch.Tensor, "unfold", custom_unfold)]
        super().__init__(config, task=task, patching_specs=patching_specs, use_past=use_past)

    @property
    def inputs(self) -> Mapping[str, Mapping[int, str]]:
        common_inputs = OrderedDict({"input_ids": {0: "batch", 1: "sequence"}})
        if self.use_past:
            for i in range(self._config.num_layers * 2):
                common_inputs[f"past_key_values.{i}"] = {0: "batch", 2: "sequence"}

            common_inputs["attention_mask"] = {0: "batch", 1: "sequence"}
        else:
            common_inputs["attention_mask"] = {0: "batch", 1: "sequence"}

        return common_inputs

    @property
    def outputs(self) -> Mapping[str, Mapping[int, str]]:
        common_outputs = super().outputs
        if self.use_past:
            for i in range(self._config.num_layers * 2):
                common_outputs[f"present.{i}"] = {0: "batch", 2: "sequence"}

        return common_outputs

    def generate_dummy_inputs(
        self,
        tokenizer: PreTrainedTokenizer,
        batch_size: int = -1,
        seq_length: int = -1,
        is_pair: bool = False,
        framework: Optional[TensorType] = None,
    ) -> Mapping[str, Any]:
        common_inputs = super().generate_dummy_inputs(tokenizer, batch_size, seq_length, is_pair, framework)

        # We need to order the input in the way they appears in the forward()
        ordered_inputs = OrderedDict({"input_ids": common_inputs["input_ids"]})

        batch = common_inputs["input_ids"].shape[0]
        past_shapes = {
            "global": (batch, self._config.num_heads, 1, self._config.hidden_size // self._config.num_attention_heads),
            "local": (batch, 1, self._config.hidden_size),
        }

        # Need to add the past_keys
        if self.use_past:
            if not is_torch_available():
                raise ValueError("Cannot generate dummy past_keys inputs without PyTorch installed.")
            else:
                import torch

                ordered_inputs["past_key_values"] = [
                    # torch.zeros((2, ) + past_shapes[self._config.attention_layers[i]])
                    (
                        torch.zeros(past_shapes[self._config.attention_layers[i]]),
                        torch.zeros(past_shapes[self._config.attention_layers[i]]),
                    )
                    for i in range(self._config.num_layers)
                ]

        ordered_inputs["attention_mask"] = common_inputs["attention_mask"]
        if self.use_past:
            ordered_inputs["attention_mask"] = torch.cat(
                [ordered_inputs["attention_mask"], torch.zeros(batch, 1)], dim=1
            )

        return ordered_inputs
