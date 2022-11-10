from typing import List, Union

from ..utils import (
    add_end_docstrings,
    is_decord_available,
    is_torch_available,
    is_vision_available,
    logging,
    requires_backends,
)
from .base import PIPELINE_INIT_ARGS, Pipeline


if is_decord_available():
    from decord import VideoReader, cpu

if is_vision_available():
    import numpy as np
    from PIL import Image


if is_torch_available():
    from ..models.auto.modeling_auto import MODEL_FOR_VIDEO_CLASSIFICATION_MAPPING

logger = logging.get_logger(__name__)


@add_end_docstrings(PIPELINE_INIT_ARGS)
class VideoClassificationPipeline(Pipeline):
    """
    Video classification pipeline using any `AutoModelForVideoClassification`. This pipeline predicts the class of a
    video.

    This video classification pipeline can currently be loaded from [`pipeline`] using the following task identifier:
    `"video-classification"`.

    See the list of available models on
    [huggingface.co/models](https://huggingface.co/models?filter=video-classification).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        requires_backends(self, "vision")
        self.check_model_type(MODEL_FOR_VIDEO_CLASSIFICATION_MAPPING)

        self.frame_sample_rate = kwargs.pop("frame_sample_rate", 4)
        self.num_frames = self.model.config.num_frames

    def _sanitize_parameters(self, top_k=None):
        postprocess_params = {}
        if top_k is not None:
            postprocess_params["top_k"] = top_k
        return {}, {}, postprocess_params

    def __call__(self, videos: Union[str, List[str], List["Image.Image"], List[List["Image.Image"]]], **kwargs):
        """
        Assign labels to the image(s) passed as inputs.

        Args:
            videos (`str`, `List[str]`, `PIL.Image` or `List[PIL.Image]`):
                The pipeline handles three types of videos:

                - A string containing a http link pointing to a video
                - A string containing a local path to an video
                - An video's frames loaded in PIL directly

                The pipeline accepts either a single video or a batch of videos, which must then be passed as a string.
                Videos in a batch must all be in the same format: all as http links, all as local paths, or all as a
                list (or list of lists) of PIL Images containing the frames of the video(s).
            top_k (`int`, *optional*, defaults to 5):
                The number of top labels that will be returned by the pipeline. If the provided number is higher than
                the number of labels available in the model configuration, it will default to the number of labels.

        Return:
            A dictionary or a list of dictionaries containing result. If the input is a single video, will return a
            dictionary, if the input is a list of several videos, will return a list of dictionaries corresponding to
            the videos.

            The dictionaries contain the following keys:

            - **label** (`str`) -- The label identified by the model.
            - **score** (`int`) -- The score attributed by the model for that label.
        """
        return super().__call__(videos, **kwargs)

    def preprocess(self, video):

        if isinstance(video, str):
            videoreader = VideoReader(video, num_threads=1, ctx=cpu(0))
            videoreader.seek(0)

            converted_len = int(self.num_frames * self.frame_sample_rate)

            seg_len = len(videoreader)
            end_idx = np.random.randint(converted_len, seg_len)
            start_idx = end_idx - converted_len
            indices = np.linspace(start_idx, end_idx, num=self.num_frames)
            indices = np.clip(indices, start_idx, end_idx - 1).astype(np.int64)

            video = videoreader.get_batch(indices).asnumpy()
            video = list(video)

        model_inputs = self.feature_extractor(list(video), return_tensors=self.framework)
        return model_inputs

    def _forward(self, model_inputs):
        model_outputs = self.model(**model_inputs)
        return model_outputs

    def postprocess(self, model_outputs, top_k=5):
        if top_k > self.model.config.num_labels:
            top_k = self.model.config.num_labels

        if self.framework == "pt":
            probs = model_outputs.logits.softmax(-1)[0]
            scores, ids = probs.topk(top_k)
        else:
            raise ValueError(f"Unsupported framework: {self.framework}")

        scores = scores.tolist()
        ids = ids.tolist()
        return [{"score": score, "label": self.model.config.id2label[_id]} for score, _id in zip(scores, ids)]
