# flake8: noqa
# There's no way to ignore "F401 '...' imported but unused" warnings in this
# module, but to preserve other warnings. So, don't check this module at all.

# Copyright 2020 The HuggingFace Team. All rights reserved.
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
from typing import TYPE_CHECKING

# rely on isort to merge the imports
from ...utils import  _LazyModule, OptionalDependencyNotAvailable, is_tokenizers_available
from ...utils import is_tf_available



from ...utils import is_torch_available




_import_structure = {
    "configuration_flexibert": ["FLEXIBERT_PRETRAINED_CONFIG_ARCHIVE_MAP", "FlexiBERTConfig"],
    "tokenization_flexibert": ["FlexiBERTTokenizer"],
}

try:
    if not is_tokenizers_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["tokenization_flexibert_fast"] = ["FlexiBERTTokenizerFast"]

try:
    if not is_torch_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["modeling_flexibert"] = [
        "FLEXIBERT_PRETRAINED_MODEL_ARCHIVE_LIST",
        "FlexiBERTForMaskedLM",
        "FlexiBERTForCausalLM",
        "FlexiBERTForMultipleChoice",
        "FlexiBERTForQuestionAnswering",
        "FlexiBERTForSequenceClassification",
        "FlexiBERTForTokenClassification",
        "FlexiBERTLayer",
        "FlexiBERTModel",
        "FlexiBERTPreTrainedModel",
        "load_tf_weights_in_flexibert",
    ]



try:
    if not is_tf_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["modeling_tf_flexibert"] = [
        "TF_FLEXIBERT_PRETRAINED_MODEL_ARCHIVE_LIST",
        "TFFlexiBERTForMaskedLM",
        "TFFlexiBERTForCausalLM",
        "TFFlexiBERTForMultipleChoice",
        "TFFlexiBERTForQuestionAnswering",
        "TFFlexiBERTForSequenceClassification",
        "TFFlexiBERTForTokenClassification",
        "TFFlexiBERTLayer",
        "TFFlexiBERTModel",
        "TFFlexiBERTPreTrainedModel",
    ]




if TYPE_CHECKING:
    from .configuration_flexibert import FLEXIBERT_PRETRAINED_CONFIG_ARCHIVE_MAP, FlexiBERTConfig
    from .tokenization_flexibert import FlexiBERTTokenizer

    try:
        if not is_tokenizers_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .tokenization_flexibert_fast import FlexiBERTTokenizerFast

    try:
        if not is_torch_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .modeling_flexibert import (
            FLEXIBERT_PRETRAINED_MODEL_ARCHIVE_LIST,
            FlexiBERTForMaskedLM,
            FlexiBERTForCausalLM,
            FlexiBERTForMultipleChoice,
            FlexiBERTForQuestionAnswering,
            FlexiBERTForSequenceClassification,
            FlexiBERTForTokenClassification,
            FlexiBERTLayer,
            FlexiBERTModel,
            FlexiBERTPreTrainedModel,
            load_tf_weights_in_flexibert,
        )



    try:
        if not is_tf_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .modeling_tf_flexibert import (
            TF_FLEXIBERT_PRETRAINED_MODEL_ARCHIVE_LIST,
            TFFlexiBERTForMaskedLM,
            TFFlexiBERTForCausalLM,
            TFFlexiBERTForMultipleChoice,
            TFFlexiBERTForQuestionAnswering,
            TFFlexiBERTForSequenceClassification,
            TFFlexiBERTForTokenClassification,
            TFFlexiBERTLayer,
            TFFlexiBERTModel,
            TFFlexiBERTPreTrainedModel,
        )



else:
    import sys

    sys.modules[__name__] = _LazyModule(__name__, globals()["__file__"], _import_structure, module_spec=__spec__)
