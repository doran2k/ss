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

<<<<<<< HEAD
from ...utils import (
    OptionalDependencyNotAvailable,
    _LazyModule,
    is_torch_available,
    is_vision_available,
)


_import_structure = {"configuration_detr": ["DetrConfig", "DetrOnnxConfig"]}

try:
    if not is_vision_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["feature_extraction_detr"] = ["DetrFeatureExtractor"]
    _import_structure["image_processing_detr"] = ["DetrImageProcessor"]
    _import_structure["image_processing_detr_fast"] = ["DetrImageProcessorFast"]

try:
    if not is_torch_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["modeling_detr"] = [
        "DetrForObjectDetection",
        "DetrForSegmentation",
        "DetrModel",
        "DetrPreTrainedModel",
    ]
=======
from ...utils import _LazyModule
from ...utils.import_utils import define_import_structure
>>>>>>> a09860d758302d61d4d1b73a791329e94f762b0e


if TYPE_CHECKING:
    from .configuration_detr import *
    from .feature_extraction_detr import *
    from .image_processing_detr import *
    from .image_processing_detr_fast import *
    from .modeling_detr import *
else:
    import sys

<<<<<<< HEAD
    sys.modules[__name__] = _LazyModule(
        __name__, globals()["__file__"], _import_structure, module_spec=__spec__
    )
=======
    _file = globals()["__file__"]
    sys.modules[__name__] = _LazyModule(__name__, _file, define_import_structure(_file), module_spec=__spec__)
>>>>>>> a09860d758302d61d4d1b73a791329e94f762b0e
