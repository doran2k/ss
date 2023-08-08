# Copyright 2022-present NAVER Corp, The Microsoft Research Asia LayoutLM Team Authors and the HuggingFace Inc. team.
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

from ...utils import OptionalDependencyNotAvailable, _LazyModule, is_tokenizers_available, is_torch_available


_import_structure = {
    "configuration_bros": ["BROS_PRETRAINED_CONFIG_ARCHIVE_MAP", "BrosConfig"],
    "tokenization_bros": ["BrosTokenizer"],
}

try:
    if not is_tokenizers_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["tokenization_bros_fast"] = ["BrosTokenizerFast"]

try:
    if not is_torch_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["modeling_bros"] = [
        "BROS_PRETRAINED_MODEL_ARCHIVE_LIST",
        "BrosPreTrainedModel",
        "BrosModel",
        "BrosForTokenClassification",
        "BrosForTokenClassificationWithSpade",
    ]


if TYPE_CHECKING:
    from .configuration_bros import BROS_PRETRAINED_CONFIG_ARCHIVE_MAP, BrosConfig
    from .tokenization_bros import BrosTokenizer

    try:
        if not is_tokenizers_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .tokenization_bros_fast import BrosTokenizerFast

    try:
        if not is_torch_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .modeling_bros import (
            BROS_PRETRAINED_MODEL_ARCHIVE_LIST,
            BrosForTokenClassification,
            BrosModel,
            BrosPreTrainedModel,
            BrosForTokenClassificationWithSpade,
        )


else:
    import sys

    sys.modules[__name__] = _LazyModule(__name__, globals()["__file__"], _import_structure, module_spec=__spec__)
