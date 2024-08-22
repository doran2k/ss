# This file is autogenerated by the command `make fix-copies`, do not edit.
from ..utils import DummyObject, requires_backends


class BaseImageProcessorFast(metaclass=DummyObject):
    _backends = ["torchvision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["torchvision"])


class IJepaImageProcessorFast(metaclass=DummyObject):
    _backends = ["torchvision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["torchvision"])


class ViTImageProcessorFast(metaclass=DummyObject):
    _backends = ["torchvision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["torchvision"])
