# # Copyright 2024 The HuggingFace Inc. team. All rights reserved.
# #
# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at
# #
# #     http://www.apache.org/licenses/LICENSE-2.0
# #
# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.
# """Image processor class for ImageBind."""

# import decord
# from fractions import Fraction
# import io
# import math
# import mimetypes
# import pathlib
# from pathlib import Path
# import torch
# import torch.nn as nn
# from torchvision import transforms
# from torchvision.transforms._transforms_video import NormalizeVideo
# from typing import BinaryIO, Dict, List, Optional, Tuple, Union

# import numpy as np

# from ...image_processing_utils import BaseImageProcessor, BatchFeature, get_size_dict
# from ...image_transforms import (
#     convert_to_rgb,
#     get_resize_output_image_size,
#     resize,
#     to_channel_dimension_format,
# )
# from ...image_utils import (
#     OPENAI_CLIP_MEAN,
#     OPENAI_CLIP_STD,
#     ChannelDimension,
#     ImageInput,
#     PILImageResampling,
#     VideoInput,
#     infer_channel_dimension_format,
#     is_scaled_image,
#     is_valid_image,
#     make_list_of_images,
#     to_numpy_array,
#     valid_images,
#     validate_kwargs,
#     validate_preprocess_arguments,
# )
# from ...utils import TensorType, is_vision_available, logging


# logger = logging.get_logger(__name__)

# decord.bridge.set_bridge("torch")

# if is_vision_available():
#     import PIL

# # def check_for_video_paths(videos) -> bool:
# #     return (isinstance(videos, list) and all(isinstance(video, str) and mimetypes.guess_type(video)[0].startswith('video/') for video in videos))

# #Adapted from https://github.com/facebookresearch/pytorchvideo/blob/1fadaef40dd393ca09680f55582399f4679fc9b7/pytorchvideo/data/encoded_video.py#L42
# def encoded_video_from_path(video_path):
#     """
#     Fetches the given video path using PathManager (allowing remote uris to be
#     fetched) and constructs the EncodedVideo object.

#     Args:
#         file_path (str): a PathManager file-path.
#     """
#     video_path = Path(video_path)
#     if video_path.is_file():
#         with video_path.open('rb') as file:
#             video_file = io.BytesIO(file.read())
#     else:
#         raise FileNotFoundError(f"{video_path} does not exist or is not a file")
    
#     sample_rate=16000
#     video = EncodedVideoDecord(
#         file=video_file,
#         video_name=pathlib.Path(video_path).name,
#         decode_video=True,
#         decode_audio=False,
#         **{"sample_rate": sample_rate},
#     )
#     return video
    

# # Copy from models.video_llava.image_processing_video_llava.make_batched_videos
# def make_batched_videos(videos) -> List[VideoInput]:
#     if isinstance(videos, (list, tuple)) and isinstance(videos[0], (list, tuple)) and is_valid_image(videos[0][0]):
#         return videos

#     elif isinstance(videos, (list, tuple)) and is_valid_image(videos[0]):
#         if isinstance(videos[0], PIL.Image.Image):
#             return [videos]
#         elif len(videos[0].shape) == 4:
#             return [list(video) for video in videos]

#     elif is_valid_image(videos) and len(videos.shape) == 4:
#         return [list(videos)]

#     raise ValueError(f"Could not make batched video from {videos}")


# # Copy from models.imagebind.feature_extraction_imagebind.uniform_chunk_sampling
# def uniform_chunk_sampling(
#     total_duration: float, chunk_duration: int, num_chunks: int
# ) -> List[Tuple[Fraction, Fraction]]:
#     """
#     Uniformly sample `num_chunks` chunks of duration `chunk_duration` from an audio/video of total duration `total_duration`.

#     Args:
#         total_duration (float): Total duration of the audio/video.
#         chunk_duration (int): Duration of each chunk(clip duration).
#         num_chunks (int): Number of chunks to sample(number of clips per video).

#     Returns:
#         List[Tuple[float, float]]: List of tuples where each tuple contains the start and end time of a chunk.
#     """
#     _current_clip_index = 0
#     _current_aug_index = 0
#     _augs_per_clip: int = 1
    
#     chunk_duration_fraction = Fraction(chunk_duration)
#     max_possible_clip_start = Fraction(max(total_duration - chunk_duration_fraction, 0)) # Previously chunk_duration was used instead of chunk_duration_fraction so that could be the reason for pixel values not matching
#     uniform_clip = Fraction(max_possible_clip_start / max(num_chunks - 1, 1))

#     result = []
#     is_last_clip = False
#     while not is_last_clip:
#         clip_start_sec = uniform_clip * _current_clip_index
#         _current_aug_index += 1
#         if _current_aug_index >= _augs_per_clip:
#             _current_clip_index += 1
#             _current_aug_index = 0
        
#         # Last clip is True if sampled self._clips_per_video or if end of video is reached.
#         is_last_clip = False
#         if (
#             _current_clip_index >= num_chunks
#             or uniform_clip * _current_clip_index > max_possible_clip_start
#         ):
#             _current_clip_index = 0
#             is_last_clip = True

#         # reset
#         if is_last_clip:
#             _current_clip_index = 0
#             _current_aug_index = 0

#         clip_end_sec = clip_start_sec + chunk_duration_fraction
#         result.append((clip_start_sec, clip_end_sec))
    
#     return result


# # Adapted from https://github.com/facebookresearch/pytorchvideo/blob/a0a131e/pytorchvideo/transforms/functional.py#L19
# def uniform_temporal_subsample(video: VideoInput, num_samples: int) -> VideoInput:
#     """
#     Uniformly subsamples num_samples indices from the temporal dimension of the video.
#     When num_samples is larger than the size of temporal dimension of the video, it
#     will sample frames based on nearest neighbor interpolation.

#     Args:
#         video (`VideoInput`):
#             Video to subsample.
#         num_samples (`int`):
#             Number of frames to sample.
#     """
#     # num_frames = len(video)

#     # # Sample by nearest neighbor interpolation if num_samples > t.
#     # indices = np.linspace(0, num_frames - 1, num_samples)
#     # indices = np.clip(indices, 0, num_frames - 1).astype(int)

#     # return [video[i] for i in indices]

#     temporal_dim: int = -3
#     num_frames = video.shape[temporal_dim]
#     assert num_samples > 0 and num_frames > 0
#     # Sample by nearest neighbor interpolation if num_samples > num_frames.
#     indices = torch.linspace(0, num_frames - 1, num_samples)
#     indices = torch.clamp(indices, 0, num_frames - 1).long()
#     return torch.index_select(video, temporal_dim, indices)

# def crop_boxes(boxes, x_offset, y_offset):
#     """
#     Perform crop on the bounding boxes given the offsets.
#     Args:
#         boxes (ndarray or None): bounding boxes to perform crop. The dimension
#             is `num boxes` x 4.
#         x_offset (int): cropping offset in the x axis.
#         y_offset (int): cropping offset in the y axis.
#     Returns:
#         cropped_boxes (ndarray or None): the cropped boxes with dimension of
#             `num boxes` x 4.
#     """
#     cropped_boxes = boxes.copy()
#     cropped_boxes[:, [0, 2]] = boxes[:, [0, 2]] - x_offset
#     cropped_boxes[:, [1, 3]] = boxes[:, [1, 3]] - y_offset

#     return cropped_boxes

# def uniform_crop(images, size, spatial_idx, boxes=None, scale_size=None):
#     """
#     Perform uniform spatial sampling on the images and corresponding boxes.
#     Args:
#         images (tensor): images to perform uniform crop. The dimension is
#             `num frames` x `channel` x `height` x `width`.
#         size (int): size of height and weight to crop the images.
#         spatial_idx (int): 0, 1, or 2 for left, center, and right crop if width
#             is larger than height. Or 0, 1, or 2 for top, center, and bottom
#             crop if height is larger than width.
#         boxes (ndarray or None): optional. Corresponding boxes to images.
#             Dimension is `num boxes` x 4.
#         scale_size (int): optinal. If not None, resize the images to scale_size before
#             performing any crop.
#     Returns:
#         cropped (tensor): images with dimension of
#             `num frames` x `channel` x `size` x `size`.
#         cropped_boxes (ndarray or None): the cropped boxes with dimension of
#             `num boxes` x 4.
#     """
#     assert spatial_idx in [0, 1, 2]
#     ndim = len(images.shape)
#     if ndim == 3:
#         images = images.unsqueeze(0)
#     height = images.shape[2]
#     width = images.shape[3]

#     if scale_size is not None:
#         if width <= height:
#             width, height = scale_size, int(height / width * scale_size)
#         else:
#             width, height = int(width / height * scale_size), scale_size
#         images = torch.nn.functional.interpolate(
#             images,
#             size=(height, width),
#             mode="bilinear",
#             align_corners=False,
#         )

#     y_offset = int(math.ceil((height - size) / 2))
#     x_offset = int(math.ceil((width - size) / 2))

#     if height > width:
#         if spatial_idx == 0:
#             y_offset = 0
#         elif spatial_idx == 2:
#             y_offset = height - size
#     else:
#         if spatial_idx == 0:
#             x_offset = 0
#         elif spatial_idx == 2:
#             x_offset = width - size
#     cropped = images[:, :, y_offset : y_offset + size, x_offset : x_offset + size]
#     cropped_boxes = crop_boxes(boxes, x_offset, y_offset) if boxes is not None else None
#     if ndim == 3:
#         cropped = cropped.squeeze(0)
#     return cropped, cropped_boxes


# class SpatialCrop(nn.Module):
#     """
#     Convert the video into 3 smaller clips spatially. Must be used after the
#         temporal crops to get spatial crops, and should be used with
#         -2 in the spatial crop at the slowfast augmentation stage (so full
#         frames are passed in here). Will return a larger list with the
#         3x spatial crops as well.
#     """

#     def __init__(self, crop_size: int = 224, num_crops: int = 3):
#         super().__init__()
#         self.crop_size = crop_size
#         if num_crops == 3:
#             self.crops_to_ext = [0, 1, 2]
#             self.flipped_crops_to_ext = []
#         elif num_crops == 1:
#             self.crops_to_ext = [1]
#             self.flipped_crops_to_ext = []
#         else:
#             raise NotImplementedError("Nothing else supported yet")

#     def forward(self, videos):
#         """
#         Args:
#             videos: A list of C, T, H, W videos.
#         Returns:
#             videos: A list with 3x the number of elements. Each video converted
#                 to C, T, H', W' by spatial cropping.
#         """
#         assert isinstance(videos, list), "Must be a list of videos after temporal crops"
#         assert all([video[0].ndim == 4 for video in videos]), "Must be (C,T,H,W)"
#         res = []
#         for video in videos:
#             for spatial_idx in self.crops_to_ext:
#                 res.append(uniform_crop(video[0], self.crop_size, spatial_idx)[0])
#             if not self.flipped_crops_to_ext:
#                 continue
#             flipped_video = transforms.functional.hflip(video[0])
#             for spatial_idx in self.flipped_crops_to_ext:
#                 res.append(uniform_crop(flipped_video, self.crop_size, spatial_idx)[0])
#         return res

# #Adapted from https://github.com/facebookresearch/pytorchvideo/blob/1fadaef40dd393ca09680f55582399f4679fc9b7/pytorchvideo/data/encoded_video_decord.py#L28
# class EncodedVideoDecord():
#     """

#     Accessing clips from an encoded video using Decord video reading API
#     as the decoding backend. For more details, please refer to -
#     `Decord <https://github.com/dmlc/decord>`
#     """

#     def __init__(
#         self,
#         file: BinaryIO,
#         video_name: Optional[str] = None,
#         decode_video: bool = True,
#         decode_audio: bool = False,
#         sample_rate: int = 44100,
#         mono: bool = True,
#         width: int = -1,
#         height: int = -1,
#         num_threads: int = 0,
#         fault_tol: int = -1,
#     ) -> None:
#         """
#         Args:
#             file (BinaryIO): a file-like object (e.g. io.BytesIO or io.StringIO) that
#                 contains the encoded video.
#             video_name (str): An optional name assigned to the video.
#             decode_video (bool): If disabled, video is not decoded.
#             decode_audio (bool): If disabled, audio is not decoded.
#             sample_rate: int, default is -1
#                 Desired output sample rate of the audio, unchanged if `-1` is specified.
#             mono: bool, default is True
#                 Desired output channel layout of the audio. `True` is mono layout. `False`
#                 is unchanged.
#             width : int, default is -1
#                 Desired output width of the video, unchanged if `-1` is specified.
#             height : int, default is -1
#                 Desired output height of the video, unchanged if `-1` is specified.
#             num_threads : int, default is 0
#                 Number of decoding thread, auto if `0` is specified.
#             fault_tol : int, default is -1
#                 The threshold of corrupted and recovered frames. This is to prevent silent fault
#                 tolerance when for example 50% frames of a video cannot be decoded and duplicate
#                 frames are returned. You may find the fault tolerant feature sweet in many
#                 cases, but not for training models. Say `N = # recovered frames`
#                 If `fault_tol` < 0, nothing will happen.
#                 If 0 < `fault_tol` < 1.0, if N > `fault_tol * len(video)`,
#                 raise `DECORDLimitReachedError`.
#                 If 1 < `fault_tol`, if N > `fault_tol`, raise `DECORDLimitReachedError`.
#         """
#         if not decode_video:
#             raise NotImplementedError()

#         self._video_name = video_name

#         try:
#             self._av_reader = decord.VideoReader(
#                 uri=file,
#                 ctx=decord.cpu(0),
#                 width=width,
#                 height=height,
#                 num_threads=num_threads,
#                 fault_tol=fault_tol,
#             )
#         except Exception as e:
#             raise RuntimeError(f"Failed to open video {video_name} with Decord. {e}")

#         self._fps = self._av_reader.get_avg_fps()

#         self._duration = float(len(self._av_reader)) / float(self._fps)

#     @property
#     def name(self) -> Optional[str]:
#         """
#         Returns:
#             name: the name of the stored video if set.
#         """
#         return self._video_name

#     @property
#     def duration(self) -> float:
#         """
#         Returns:
#             duration: the video's duration/end-time in seconds.
#         """
#         return self._duration

#     def close(self):
#         if self._av_reader is not None:
#             del self._av_reader
#             self._av_reader = None

#     def get_clip(
#         self, start_sec: float, end_sec: float
#     ) -> Dict[str, Optional[torch.Tensor]]:
#         """
#         Retrieves frames from the encoded video at the specified start and end times
#         in seconds (the video always starts at 0 seconds).

#         Args:
#             start_sec (float): the clip start time in seconds
#             end_sec (float): the clip end time in seconds
#         Returns:
#             clip_data:
#                 A dictionary mapping the entries at "video" and "audio" to a tensors.

#                 "video": A tensor of the clip's RGB frames with shape:
#                 (channel, time, height, width). The frames are of type torch.float32 and
#                 in the range [0 - 255].

#                 "audio": A tensor of the clip's audio samples with shape:
#                 (samples). The samples are of type torch.float32 and
#                 in the range [0 - 255].

#             Returns None if no video or audio found within time range.

#         """
#         if start_sec > end_sec or start_sec > self._duration:
#             raise RuntimeError(
#                 f"Incorrect time window for Decord decoding for video: {self._video_name}."
#             )

#         start_idx = math.ceil(self._fps * start_sec)
#         end_idx = math.ceil(self._fps * end_sec)
#         end_idx = min(end_idx, len(self._av_reader))
#         frame_idxs = list(range(start_idx, end_idx))

#         try:
#             outputs = self._av_reader.get_batch(frame_idxs)
#         except Exception as e:
#             logger.debug(f"Failed to decode video with Decord: {self._video_name}. {e}")
#             raise e

#         video = outputs

#         if video is not None:
#             video = video.to(torch.float32)
#             #Permute tensor from (time, height, weight, channel) to (channel, height, width, time).
#             video = video.permute(3, 0, 1, 2)


#         return video

# class ImageBindImageProcessor(BaseImageProcessor):
#     r"""
#     Constructs an ImageBind image processor.

#     Args:
#         do_resize (`bool`, *optional*, defaults to `True`):
#             Whether to resize the image's (height, width) dimensions to the specified `size`. Can be overridden by
#             `do_resize` in the `preprocess` method.
#         size (`Dict[str, int]` *optional*, defaults to `{"shortest_edge": 224}`):
#             Size of the image after resizing. The shortest edge of the image is resized to size["shortest_edge"], with
#             the longest edge resized to keep the input aspect ratio. Can be overridden by `size` in the `preprocess`
#             method.
#         resample (`PILImageResampling`, *optional*, defaults to `Resampling.BICUBIC`):
#             Resampling filter to use if resizing the image. Can be overridden by `resample` in the `preprocess` method.
#         do_center_crop (`bool`, *optional*, defaults to `True`):
#             Whether to center crop the image to the specified `crop_size`. Can be overridden by `do_center_crop` in the
#             `preprocess` method.
#         crop_size (`Dict[str, int]` *optional*, defaults to 224):
#             Size of the output image after applying `center_crop`. Can be overridden by `crop_size` in the `preprocess`
#             method.
#         do_rescale (`bool`, *optional*, defaults to `True`):
#             Whether to rescale the image by the specified scale `rescale_factor`. Can be overridden by `do_rescale` in
#             the `preprocess` method.
#         rescale_factor (`int` or `float`, *optional*, defaults to `1/255`):
#             Scale factor to use if rescaling the image. Can be overridden by `rescale_factor` in the `preprocess`
#             method.
#         do_normalize (`bool`, *optional*, defaults to `True`):
#             Whether to normalize the image. Can be overridden by `do_normalize` in the `preprocess` method.
#         image_mean (`float` or `List[float]`, *optional*, defaults to `[0.48145466, 0.4578275, 0.40821073]`):
#             Mean to use if normalizing the image. This is a float or list of floats the length of the number of
#             channels in the image. Can be overridden by the `image_mean` parameter in the `preprocess` method.
#         image_std (`float` or `List[float]`, *optional*, defaults to `[0.26862954, 0.26130258, 0.27577711]`):
#             Standard deviation to use if normalizing the image. This is a float or list of floats the length of the
#             number of channels in the image. Can be overridden by the `image_std` parameter in the `preprocess` method.
#             Can be overridden by the `image_std` parameter in the `preprocess` method.
#         do_convert_rgb (`bool`, *optional*, defaults to `True`):
#             Whether to convert the image to RGB.
#         do_chunk (`bool`, *optional*, defaults to `False`):
#             Whether to chunk the video into multiple clips.
#         chunk_duration (`int`, *optional*, defaults to 2):
#             Duration of each chunk in seconds(clip duration).
#         num_chunks (`int`, *optional*, defaults to 5):
#             Number of chunks to sample(number of clips per video).
#         num_frames_per_chunk (`int`, *optional*, defaults to 2):
#             Number of frames to sample per chunk.
#         fps (`int`, *optional*, defaults to 30):
#             Frame rate of the video. It's assumed that all videos have the same frame rate.
#     """

#     model_input_names = ["pixel_values"]

#     def __init__(
#         self,
#         do_resize: bool = True,
#         size: Dict[str, int] = None,
#         resample: PILImageResampling = PILImageResampling.BICUBIC,
#         do_center_crop: bool = True,
#         crop_size: Dict[str, int] = None,
#         do_rescale: bool = True,
#         rescale_factor: Union[int, float] = 1 / 255,
#         do_normalize: bool = True,
#         image_mean: Optional[Union[float, List[float]]] = None,
#         image_std: Optional[Union[float, List[float]]] = None,
#         do_convert_rgb: bool = True,
#         do_chunk: bool = False,
#         chunk_duration: int = 2,
#         num_chunks: int = 5,
#         num_frames_per_chunk: int = 2,
#         fps: int = 30,
#         **kwargs,
#     ) -> None:
#         super().__init__(**kwargs)
#         size = size if size is not None else {"shortest_edge": 224}
#         size = get_size_dict(size, default_to_square=False)
#         crop_size = crop_size if crop_size is not None else {"height": 224, "width": 224}
#         crop_size = get_size_dict(crop_size, default_to_square=True, param_name="crop_size")

#         self.do_resize = do_resize
#         self.size = size
#         self.resample = resample
#         self.do_center_crop = do_center_crop
#         self.crop_size = crop_size
#         self.do_rescale = do_rescale
#         self.rescale_factor = rescale_factor
#         self.do_normalize = do_normalize
#         self.image_mean = image_mean if image_mean is not None else OPENAI_CLIP_MEAN
#         self.image_std = image_std if image_std is not None else OPENAI_CLIP_STD
#         self.do_convert_rgb = do_convert_rgb
#         self.do_chunk = do_chunk
#         self.chunk_duration = chunk_duration
#         self.num_chunks = num_chunks
#         self.num_frames_per_chunk = num_frames_per_chunk
#         self.fps = fps
#         self._valid_processor_keys = [
#             "images",
#             "do_resize",
#             "size",
#             "resample",
#             "do_center_crop",
#             "crop_size",
#             "do_rescale",
#             "rescale_factor",
#             "do_normalize",
#             "image_mean",
#             "image_std",
#             "do_convert_rgb",
#             "do_chunk",
#             "chunk_duration",
#             "num_chunks",
#             "fps",
#             "return_tensors",
#             "data_format",
#             "input_data_format",
#         ]

#         # for backwards compatibility of KOSMOS-2
#         if "use_square_size" in kwargs and kwargs["use_square_size"]:
#             self.size = {"height": size["shortest_edge"], "width": size["shortest_edge"]}
#             # Let's remove `use_square_size` (as it is removed from #27690), so the future Kosmos-2 image processors
#             # won't have this attr. being saved. (otherwise, it will enter this if branch while there is no more
#             # `shortest_edge` key.
#             delattr(self, "use_square_size")

#     # Copied from models.clip.image_processing_clip.CLIPImageProcessor.resize
#     def resize(
#         self,
#         image: np.ndarray,
#         size: Dict[str, int],
#         resample: PILImageResampling = PILImageResampling.BICUBIC,
#         data_format: Optional[Union[str, ChannelDimension]] = None,
#         input_data_format: Optional[Union[str, ChannelDimension]] = None,
#         **kwargs,
#     ) -> np.ndarray:
#         """
#         Resize an image. The shortest edge of the image is resized to size["shortest_edge"], with the longest edge
#         resized to keep the input aspect ratio.

#         Args:
#             image (`np.ndarray`):
#                 Image to resize.
#             size (`Dict[str, int]`):
#                 Size of the output image.
#             resample (`PILImageResampling`, *optional*, defaults to `PILImageResampling.BICUBIC`):
#                 Resampling filter to use when resiizing the image.
#             data_format (`str` or `ChannelDimension`, *optional*):
#                 The channel dimension format of the image. If not provided, it will be the same as the input image.
#             input_data_format (`ChannelDimension` or `str`, *optional*):
#                 The channel dimension format of the input image. If not provided, it will be inferred.
#         """
#         default_to_square = True
#         if "shortest_edge" in size:
#             size = size["shortest_edge"]
#             default_to_square = False
#         elif "height" in size and "width" in size:
#             size = (size["height"], size["width"])
#         else:
#             raise ValueError("Size must contain either 'shortest_edge' or 'height' and 'width'.")

#         output_size = get_resize_output_image_size(
#             image,
#             size=size,
#             default_to_square=default_to_square,
#             input_data_format=input_data_format,
#         )
#         return resize(
#             image,
#             size=output_size,
#             resample=resample,
#             data_format=data_format,
#             input_data_format=input_data_format,
#             **kwargs,
#         )

#     #Adapted from https://github.com/facebookresearch/pytorchvideo/blob/1fadaef40dd393ca09680f55582399f4679fc9b7/pytorchvideo/transforms/functional.py#L92
#     def short_side_scale(
#         self,
#         x: torch.Tensor,
#         size: int = 224,
#         interpolation: str = "bilinear",
#         backend: str = "pytorch",
#     ) -> torch.Tensor:
#         """
#         Determines the shorter spatial dim of the video (i.e. width or height) and scales
#         it to the given size. To maintain aspect ratio, the longer side is then scaled
#         accordingly.
#         Args:
#             x (torch.Tensor): A video tensor of shape (C, T, H, W) and type torch.float32.
#             size (int): The size the shorter side is scaled to.
#             interpolation (str): Algorithm used for upsampling,
#                 options: nearest' | 'linear' | 'bilinear' | 'bicubic' | 'trilinear' | 'area'
#             backend (str): backend used to perform interpolation. Options includes
#                 `pytorch` as default, and `opencv`. Note that opencv and pytorch behave
#                 differently on linear interpolation on some versions.
#                 https://discuss.pytorch.org/t/pytorch-linear-interpolation-is-different-from-pil-opencv/71181
#         Returns:
#             An x-like Tensor with scaled spatial dims.
#         """  # noqa
#         assert len(x.shape) == 4
#         assert x.dtype == torch.float32
#         _, _, h, w = x.shape
#         if w < h:
#             new_h = int(math.floor((float(h) / w) * size))
#             new_w = size
#         else:
#             new_h = size
#             new_w = int(math.floor((float(w) / h) * size))
#         if backend == "pytorch":
#             return torch.nn.functional.interpolate(
#                 x, size=(new_h, new_w), mode=interpolation, align_corners=False
#             )
#         else:
#             raise NotImplementedError(f"{backend} backend not supported.")


#     def chunk(
#         self, video: VideoInput, fps: int, chunk_duration: int, num_chunks: int, num_frames_per_chunk: int
#     ) -> List[VideoInput]:
#         """
#         Uniformly sample `num_chunks` chunks of duration `chunk_duration` from a video.

#         Args:
#             video (`VideoInput`):
#                 Video to chunk.
#             fps (`int`):
#                 Frame rate of the video
#             chunk_duration (`int`):
#                 Duration of each chunk(clip duration).
#             num_chunks (`int`):
#                 Number of chunks to sample(number of clips per video).
#             num_frames_per_chunk (`int`):
#                 Number of frames to sample per chunk.######(WHY IS IT DEFINED WHEN chunk_duration can fulfill its purpose?)######
#         """
#         video_duration = video.duration # EncodedVideoDecord obj
#         if video_duration < chunk_duration:
#             logger.warning_once(
#                 "Chunk duration is greater than audio duration. Chunks will be repeated, consider adjusting either `chunk_duration` or `num_chunks`"
#                 "to avoid unnecessary memory/compute usage."
#             )

#         all_clips_timepoints = uniform_chunk_sampling(video_duration, chunk_duration, num_chunks)

#         all_clips = []
#         for clip_timepoints in all_clips_timepoints:
#             # Read the clip, get frames
#             video_clip = video.get_clip(clip_timepoints[0], clip_timepoints[1])
#             if video_clip is None:
#                 raise ValueError("No clip found")
#             video_clip = uniform_temporal_subsample(video_clip, num_samples=chunk_duration)
#             video_clip = video_clip / 255.0  # since this is float, need 0-1
#             all_clips.append(video_clip)

#         return all_clips

#     # Copied from models.clip.image_processing_clip.CLIPImageProcessor.preprocess with preprocess->_preprocess_image
#     def _preprocess_image(
#         self,
#         images: ImageInput,
#         is_video: bool = None,
#         do_resize: bool = None,
#         size: Dict[str, int] = None,
#         resample: PILImageResampling = None,
#         do_center_crop: bool = None,
#         crop_size: int = None,
#         do_rescale: bool = None,
#         rescale_factor: float = None,
#         do_normalize: bool = None,
#         image_mean: Optional[Union[float, List[float]]] = None,
#         image_std: Optional[Union[float, List[float]]] = None,
#         do_convert_rgb: bool = None,
#         data_format: Optional[ChannelDimension] = ChannelDimension.FIRST,
#         input_data_format: Optional[Union[str, ChannelDimension]] = None,
#     ) -> np.ndarray:
#         validate_preprocess_arguments(
#             do_rescale=do_rescale,
#             rescale_factor=rescale_factor,
#             do_normalize=do_normalize,
#             image_mean=image_mean,
#             image_std=image_std,
#             do_center_crop=do_center_crop,
#             crop_size=crop_size,
#             do_resize=do_resize,
#             size=size,
#             resample=resample,
#         )

#         if not is_video:
#           if do_convert_rgb:
#               images = [convert_to_rgb(image) for image in images]

#         # All transformations expect numpy arrays.
#         if not is_video:
#             images = [to_numpy_array(image) for image in images]
#         if not is_video:
#           if is_scaled_image(images[0]) and do_rescale:
#               logger.warning_once(
#                   "It looks like you are trying to rescale already rescaled images. If the input"
#                   " images have pixel values between 0 and 1, set `do_rescale=False` to avoid rescaling them again."
#               )
#         if not is_video:
#           if input_data_format is None:
#               # We assume that all images have the same channel dimension format.
#               input_data_format = infer_channel_dimension_format(images[0])

#         if not is_video:
#             if do_resize:
#                 images = [
#                     self.resize(image=image, size=size, resample=resample, input_data_format=input_data_format)
#                     for image in images
#                 ]

#             if do_center_crop:
#                 images = [
#                     self.center_crop(image=image, size=crop_size, input_data_format=input_data_format) for image in images
#                 ]

#             if do_rescale:
#                 images = [
#                     self.rescale(image=image, scale=rescale_factor, input_data_format=input_data_format)
#                     for image in images
#                 ]

#             if do_normalize:
#                 images = [
#                     self.normalize(image=image, mean=image_mean, std=image_std, input_data_format=input_data_format)
#                     for image in images
#                 ]

#             images = [
#                 to_channel_dimension_format(image, data_format, input_channel_dim=input_data_format) for image in images
#             ]
#         else:
#             if do_resize:
#                 images = self.short_side_scale(images)
#             if do_normalize:
#                 images = NormalizeVideo(
#                             mean=image_mean,
#                             std=image_std,
#                         )(images),

#         return images

#     # Ignore copy
#     def preprocess(
#         self,
#         images: Optional[ImageInput] = None,
#         videos: Optional[VideoInput] = None,
#         do_resize: bool = None,
#         size: Dict[str, int] = None,
#         resample: PILImageResampling = None,
#         do_center_crop: bool = None,
#         crop_size: int = None,
#         do_rescale: bool = None,
#         rescale_factor: float = None,
#         do_normalize: bool = None,
#         image_mean: Optional[Union[float, List[float]]] = None,
#         image_std: Optional[Union[float, List[float]]] = None,
#         do_convert_rgb: bool = None,
#         do_chunk: bool = None,
#         chunk_duration: int = None,
#         num_chunks: int = None,
#         num_frames_per_chunk: int = None,
#         fps: int = None,
#         return_tensors: Optional[Union[str, TensorType]] = None,
#         data_format: Optional[ChannelDimension] = ChannelDimension.FIRST,
#         input_data_format: Optional[Union[str, ChannelDimension]] = None,
#         **kwargs,
#     ) -> PIL.Image.Image:
#         """
#         Preprocess an image or batch of images.

#         Args:
#             images (`ImageInput`, *optional*):
#                 Image to preprocess. Expects a single or batch of images with pixel values ranging from 0 to 255. If
#                 passing in images with pixel values between 0 and 1, set `do_rescale=False`. Either `images` or
#                 `videos` must be provided.
#             videos (`VideoInput`, *optional*):
#                 Video to preprocess. Expects a single or batch of videos with pixel values ranging from 0 to 255. If
#                 passing in videos with pixel values between 0 and 1, set `do_rescale=False`. Either `images` or
#                 `videos` must be provided.
#             do_resize (`bool`, *optional*, defaults to `self.do_resize`):
#                 Whether to resize the image.
#             size (`Dict[str, int]`, *optional*, defaults to `self.size`):
#                 Size of the image after resizing. Shortest edge of the image is resized to size["shortest_edge"], with
#                 the longest edge resized to keep the input aspect ratio.
#             resample (`int`, *optional*, defaults to `self.resample`):
#                 Resampling filter to use if resizing the image. This can be one of the enum `PILImageResampling`. Only
#                 has an effect if `do_resize` is set to `True`.
#             do_center_crop (`bool`, *optional*, defaults to `self.do_center_crop`):
#                 Whether to center crop the image.
#             crop_size (`Dict[str, int]`, *optional*, defaults to `self.crop_size`):
#                 Size of the center crop. Only has an effect if `do_center_crop` is set to `True`.
#             do_rescale (`bool`, *optional*, defaults to `self.do_rescale`):
#                 Whether to rescale the image.
#             rescale_factor (`float`, *optional*, defaults to `self.rescale_factor`):
#                 Rescale factor to rescale the image by if `do_rescale` is set to `True`.
#             do_normalize (`bool`, *optional*, defaults to `self.do_normalize`):
#                 Whether to normalize the image.
#             image_mean (`float` or `List[float]`, *optional*, defaults to `self.image_mean`):
#                 Image mean to use for normalization. Only has an effect if `do_normalize` is set to `True`.
#             image_std (`float` or `List[float]`, *optional*, defaults to `self.image_std`):
#                 Image standard deviation to use for normalization. Only has an effect if `do_normalize` is set to
#                 `True`.
#             do_convert_rgb (`bool`, *optional*, defaults to `self.do_convert_rgb`):
#                 Whether to convert the image to RGB.
#             do_chunk (`bool`, *optional*, defaults to `self.do_chunk`):
#                 Whether to chunk the video into multiple clips.
#             chunk_duration (`int`, *optional*, defaults to `self.chunk_duration`):
#                 Duration of each chunk in seconds(clip duration).
#             num_chunks (`int`, *optional*, defaults to `self.num_chunks`):
#                 Number of chunks to sample(number of clips per video).
#             num_frames_per_chunk (`int`, *optional*, defaults to `self.num_frames_per_chunk`):
#                 Number of frames to sample per chunk.
#             fps (`int`, *optional*, defaults to `self.fps`):
#                 Frame rate of the video. It's assumed that all videos have the same frame rate.
#             return_tensors (`str` or `TensorType`, *optional*):
#                 The type of tensors to return. Can be one of:
#                 - Unset: Return a list of `np.ndarray`.
#                 - `TensorType.TENSORFLOW` or `'tf'`: Return a batch of type `tf.Tensor`.
#                 - `TensorType.PYTORCH` or `'pt'`: Return a batch of type `torch.Tensor`.
#                 - `TensorType.NUMPY` or `'np'`: Return a batch of type `np.ndarray`.
#                 - `TensorType.JAX` or `'jax'`: Return a batch of type `jax.numpy.ndarray`.
#             data_format (`ChannelDimension` or `str`, *optional*, defaults to `ChannelDimension.FIRST`):
#                 The channel dimension format for the output image. Can be one of:
#                 - `"channels_first"` or `ChannelDimension.FIRST`: image in (num_channels, height, width) format.
#                 - `"channels_last"` or `ChannelDimension.LAST`: image in (height, width, num_channels) format.
#                 - Unset: Use the channel dimension format of the input image.
#             input_data_format (`ChannelDimension` or `str`, *optional*):
#                 The channel dimension format for the input image. If unset, the channel dimension format is inferred
#                 from the input image. Can be one of:
#                 - `"channels_first"` or `ChannelDimension.FIRST`: image in (num_channels, height, width) format.
#                 - `"channels_last"` or `ChannelDimension.LAST`: image in (height, width, num_channels) format.
#                 - `"none"` or `ChannelDimension.NONE`: image in (height, width) format.
#         """
#         if images is None and videos is None:
#             raise ValueError("Either `images` or `videos` must be provided.")

#         if images is not None and videos is not None:
#             raise ValueError("Only one of `images` or `videos` can be provided.")

#         do_resize = do_resize if do_resize is not None else self.do_resize
#         size = size if size is not None else self.size
#         size = get_size_dict(size, param_name="size", default_to_square=False)
#         resample = resample if resample is not None else self.resample
#         do_center_crop = do_center_crop if do_center_crop is not None else self.do_center_crop
#         crop_size = crop_size if crop_size is not None else self.crop_size
#         crop_size = get_size_dict(crop_size, param_name="crop_size", default_to_square=True)
#         do_rescale = do_rescale if do_rescale is not None else self.do_rescale
#         rescale_factor = rescale_factor if rescale_factor is not None else self.rescale_factor
#         do_normalize = do_normalize if do_normalize is not None else self.do_normalize
#         image_mean = image_mean if image_mean is not None else self.image_mean
#         image_std = image_std if image_std is not None else self.image_std
#         do_convert_rgb = do_convert_rgb if do_convert_rgb is not None else self.do_convert_rgb
#         do_chunk = do_chunk if do_chunk is not None else self.do_chunk
#         chunk_duration = chunk_duration if chunk_duration is not None else self.chunk_duration
#         num_chunks = num_chunks if num_chunks is not None else self.num_chunks
#         num_frames_per_chunk = num_frames_per_chunk if num_frames_per_chunk is not None else self.num_frames_per_chunk
#         fps = fps if fps is not None else self.fps

#         if images is not None:
#             is_video = False
#             images = make_list_of_images(images)
#         if videos is not None:
#             is_video = True
#             videos = make_batched_videos(videos)

#         validate_kwargs(captured_kwargs=kwargs.keys(), valid_processor_keys=self._valid_processor_keys)

#         if (videos is not None and not valid_images(videos)) or (images is not None and not valid_images(images)):
#             raise ValueError(
#                 "Invalid input type. Must be of type PIL.Image.Image, numpy.ndarray, "
#                 "torch.Tensor, tf.Tensor or jax.ndarray."
#             )

#         if images is not None:
#             pixel_values = self._preprocess_image(
#                 images=images,
#                 is_video = is_video,
#                 do_resize=do_resize,
#                 size=size,
#                 resample=resample,
#                 do_center_crop=do_center_crop,
#                 crop_size=crop_size,
#                 do_rescale=do_rescale,
#                 rescale_factor=rescale_factor,
#                 do_normalize=do_normalize,
#                 image_mean=image_mean,
#                 image_std=image_std,
#                 do_convert_rgb=do_convert_rgb,
#                 data_format=data_format,
#                 input_data_format=input_data_format,
#             )
#         else:
#             pixel_values = []
                              
#             for video in videos:
#                 # if check_for_video_paths(videos):
#                 #     is_video = True
#                 #     video = encoded_video_from_path(
#                 #         video,
#                 #     )
#                 if do_chunk:
#                     clips = self.chunk(
#                         video=video,
#                         fps=fps,
#                         chunk_duration=chunk_duration,
#                         num_chunks=num_chunks,
#                         num_frames_per_chunk=num_frames_per_chunk,
#                     )

#                     _pixel_values = [
#                         self._preprocess_image(
#                             images=clip,
#                             is_video = is_video,
#                             do_resize=do_resize,
#                             size=size,
#                             resample=PILImageResampling.BILINEAR,
#                             do_center_crop=do_center_crop,
#                             crop_size=crop_size,
#                             do_rescale=do_rescale,
#                             rescale_factor=rescale_factor,
#                             do_normalize=do_normalize,
#                             image_mean=image_mean,
#                             image_std=image_std,
#                             do_convert_rgb=do_convert_rgb,
#                             data_format=data_format,
#                             input_data_format=input_data_format,
#                         )
#                         for clip in clips
#                     ]
#                 else:
#                     _pixel_values = [
#                         self._preprocess_image(
#                             images=video,
#                             is_video = is_video,
#                             do_resize=do_resize,
#                             size=size,
#                             resample=resample,
#                             do_center_crop=do_center_crop,
#                             crop_size=crop_size,
#                             do_rescale=do_rescale,
#                             rescale_factor=rescale_factor,
#                             do_normalize=do_normalize,
#                             image_mean=image_mean,
#                             image_std=image_std,
#                             do_convert_rgb=do_convert_rgb,
#                             data_format=data_format,
#                             input_data_format=input_data_format,
#                         )
#                     ]

#                 _pixel_values = SpatialCrop(224, num_crops=3)(_pixel_values)
#                 # Avoid List[List[List[np.ndarray]]]
#                 _pixel_values = torch.stack(_pixel_values, dim = 0)
#                 pixel_values.append(_pixel_values)
#                 # _pixel_values = np.stack(_pixel_values)
#                 # # Make it shape (num_chunks, num_channels, num_frames_per_chunk, height, width)
#                 # _pixel_values = np.swapaxes(_pixel_values, 1, 2)
#                 # pixel_values.append(_pixel_values)
#             pixel_values = torch.stack(pixel_values, dim=0)
#         return BatchFeature(data={"pixel_values": pixel_values}, tensor_type=return_tensors)















# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
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
"""Image processor class for ImageBind."""

import math
from fractions import Fraction
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from ...image_processing_utils import BaseImageProcessor, BatchFeature, get_size_dict
from ...image_transforms import (
    convert_to_rgb,
    get_resize_output_image_size,
    resize,
    to_channel_dimension_format,
)
from ...image_utils import (
    OPENAI_CLIP_MEAN,
    OPENAI_CLIP_STD,
    ChannelDimension,
    ImageInput,
    PILImageResampling,
    VideoInput,
    infer_channel_dimension_format,
    is_scaled_image,
    is_valid_image,
    make_list_of_images,
    to_numpy_array,
    valid_images,
    validate_kwargs,
    validate_preprocess_arguments,
)
from ...utils import TensorType, is_vision_available, logging


logger = logging.get_logger(__name__)


if is_vision_available():
    import PIL


# Copy from models.video_llava.image_processing_video_llava.make_batched_videos
def make_batched_videos(videos) -> List[VideoInput]:
    if isinstance(videos, (list, tuple)) and isinstance(videos[0], (list, tuple)) and is_valid_image(videos[0][0]):
        return videos

    elif isinstance(videos, (list, tuple)) and is_valid_image(videos[0]):
        if isinstance(videos[0], PIL.Image.Image):
            return [videos]
        elif len(videos[0].shape) == 4:
            return [list(video) for video in videos]

    elif is_valid_image(videos) and len(videos.shape) == 4:
        return [list(videos)]

    raise ValueError(f"Could not make batched video from {videos}")


# Copy from models.imagebind.feature_extraction_imagebind.uniform_chunk_sampling
def uniform_chunk_sampling(
    total_duration: float, chunk_duration: float, num_chunks: int
) -> List[Tuple[Fraction, Fraction]]:
    """
    Uniformly sample `num_chunks` chunks of duration `chunk_duration` from an audio/video of total duration `total_duration`.

    Args:
        total_duration (float): Total duration of the audio/video.
        chunk_duration (float): Duration of each chunk.
        num_chunks (int): Number of chunks to sample.

    Returns:
        List[Tuple[float, float]]: List of tuples where each tuple contains the start and end time of a chunk.
    """
    chunk_duration_fraction = Fraction(chunk_duration)
    max_possible_clip_start = Fraction(max(total_duration - chunk_duration, 0))
    uniform_clip = Fraction(max_possible_clip_start / max(num_chunks - 1, 1))

    result = []
    for clip_index in range(num_chunks):
        clip_start_sec = uniform_clip * clip_index
        clip_end_sec = clip_start_sec + chunk_duration_fraction
        result.append((clip_start_sec, clip_end_sec))

    return result


# Adapted from https://github.com/facebookresearch/pytorchvideo/blob/a0a131e/pytorchvideo/transforms/functional.py#L19
def uniform_temporal_subsample(video: VideoInput, num_samples: int) -> VideoInput:
    """
    Uniformly subsamples num_samples indices from the temporal dimension of the video.
    When num_samples is larger than the size of temporal dimension of the video, it
    will sample frames based on nearest neighbor interpolation.

    Args:
        video (`VideoInput`):
            Video to subsample.
        num_samples (`int`):
            Number of frames to sample.
    """
    num_frames = len(video)

    # Sample by nearest neighbor interpolation if num_samples > t.
    indices = np.linspace(0, num_frames - 1, num_samples)
    indices = np.clip(indices, 0, num_frames - 1).astype(int)

    return [video[i] for i in indices]


class ImageBindImageProcessor(BaseImageProcessor):
    r"""
    Constructs an ImageBind image processor.

    Args:
        do_resize (`bool`, *optional*, defaults to `True`):
            Whether to resize the image's (height, width) dimensions to the specified `size`. Can be overridden by
            `do_resize` in the `preprocess` method.
        size (`Dict[str, int]` *optional*, defaults to `{"shortest_edge": 224}`):
            Size of the image after resizing. The shortest edge of the image is resized to size["shortest_edge"], with
            the longest edge resized to keep the input aspect ratio. Can be overridden by `size` in the `preprocess`
            method.
        resample (`PILImageResampling`, *optional*, defaults to `Resampling.BICUBIC`):
            Resampling filter to use if resizing the image. Can be overridden by `resample` in the `preprocess` method.
        do_center_crop (`bool`, *optional*, defaults to `True`):
            Whether to center crop the image to the specified `crop_size`. Can be overridden by `do_center_crop` in the
            `preprocess` method.
        crop_size (`Dict[str, int]` *optional*, defaults to 224):
            Size of the output image after applying `center_crop`. Can be overridden by `crop_size` in the `preprocess`
            method.
        do_rescale (`bool`, *optional*, defaults to `True`):
            Whether to rescale the image by the specified scale `rescale_factor`. Can be overridden by `do_rescale` in
            the `preprocess` method.
        rescale_factor (`int` or `float`, *optional*, defaults to `1/255`):
            Scale factor to use if rescaling the image. Can be overridden by `rescale_factor` in the `preprocess`
            method.
        do_normalize (`bool`, *optional*, defaults to `True`):
            Whether to normalize the image. Can be overridden by `do_normalize` in the `preprocess` method.
        image_mean (`float` or `List[float]`, *optional*, defaults to `[0.48145466, 0.4578275, 0.40821073]`):
            Mean to use if normalizing the image. This is a float or list of floats the length of the number of
            channels in the image. Can be overridden by the `image_mean` parameter in the `preprocess` method.
        image_std (`float` or `List[float]`, *optional*, defaults to `[0.26862954, 0.26130258, 0.27577711]`):
            Standard deviation to use if normalizing the image. This is a float or list of floats the length of the
            number of channels in the image. Can be overridden by the `image_std` parameter in the `preprocess` method.
            Can be overridden by the `image_std` parameter in the `preprocess` method.
        do_convert_rgb (`bool`, *optional*, defaults to `True`):
            Whether to convert the image to RGB.
        do_chunk (`bool`, *optional*, defaults to `True`):
            Whether to chunk the video into multiple clips.
        chunk_duration (`float`, *optional*, defaults to 2.0):
            Duration of each chunk in seconds.
        num_chunks (`int`, *optional*, defaults to 5):
            Number of chunks to sample.
        num_frames_per_chunk (`int`, *optional*, defaults to 2):
            Number of frames to sample per chunk.
        fps (`int`, *optional*, defaults to 30):
            Frame rate of the video. It's assumed that all videos have the same frame rate.
    """

    model_input_names = ["pixel_values"]

    def __init__(
        self,
        do_resize: bool = True,
        size: Dict[str, int] = None,
        resample: PILImageResampling = PILImageResampling.BICUBIC,
        do_center_crop: bool = True,
        crop_size: Dict[str, int] = None,
        do_rescale: bool = True,
        rescale_factor: Union[int, float] = 1 / 255,
        do_normalize: bool = True,
        image_mean: Optional[Union[float, List[float]]] = None,
        image_std: Optional[Union[float, List[float]]] = None,
        do_convert_rgb: bool = True,
        do_chunk: bool = True,
        chunk_duration: float = 2.0,
        num_chunks: int = 5,
        num_frames_per_chunk: int = 2,
        fps: int = 30,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        size = size if size is not None else {"shortest_edge": 224}
        size = get_size_dict(size, default_to_square=False)
        crop_size = crop_size if crop_size is not None else {"height": 224, "width": 224}
        crop_size = get_size_dict(crop_size, default_to_square=True, param_name="crop_size")

        self.do_resize = do_resize
        self.size = size
        self.resample = resample
        self.do_center_crop = do_center_crop
        self.crop_size = crop_size
        self.do_rescale = do_rescale
        self.rescale_factor = rescale_factor
        self.do_normalize = do_normalize
        self.image_mean = image_mean if image_mean is not None else OPENAI_CLIP_MEAN
        self.image_std = image_std if image_std is not None else OPENAI_CLIP_STD
        self.do_convert_rgb = do_convert_rgb
        self.do_chunk = do_chunk
        self.chunk_duration = chunk_duration
        self.num_chunks = num_chunks
        self.num_frames_per_chunk = num_frames_per_chunk
        self.fps = fps
        self._valid_processor_keys = [
            "images",
            "do_resize",
            "size",
            "resample",
            "do_center_crop",
            "crop_size",
            "do_rescale",
            "rescale_factor",
            "do_normalize",
            "image_mean",
            "image_std",
            "do_convert_rgb",
            "do_chunk",
            "chunk_duration",
            "num_chunks",
            "fps",
            "return_tensors",
            "data_format",
            "input_data_format",
        ]

        # for backwards compatibility of KOSMOS-2
        if "use_square_size" in kwargs and kwargs["use_square_size"]:
            self.size = {"height": size["shortest_edge"], "width": size["shortest_edge"]}
            # Let's remove `use_square_size` (as it is removed from #27690), so the future Kosmos-2 image processors
            # won't have this attr. being saved. (otherwise, it will enter this if branch while there is no more
            # `shortest_edge` key.
            delattr(self, "use_square_size")

    # Copied from models.clip.image_processing_clip.CLIPImageProcessor.resize
    def resize(
        self,
        image: np.ndarray,
        size: Dict[str, int],
        resample: PILImageResampling = PILImageResampling.BICUBIC,
        data_format: Optional[Union[str, ChannelDimension]] = None,
        input_data_format: Optional[Union[str, ChannelDimension]] = None,
        **kwargs,
    ) -> np.ndarray:
        """
        Resize an image. The shortest edge of the image is resized to size["shortest_edge"], with the longest edge
        resized to keep the input aspect ratio.

        Args:
            image (`np.ndarray`):
                Image to resize.
            size (`Dict[str, int]`):
                Size of the output image.
            resample (`PILImageResampling`, *optional*, defaults to `PILImageResampling.BICUBIC`):
                Resampling filter to use when resiizing the image.
            data_format (`str` or `ChannelDimension`, *optional*):
                The channel dimension format of the image. If not provided, it will be the same as the input image.
            input_data_format (`ChannelDimension` or `str`, *optional*):
                The channel dimension format of the input image. If not provided, it will be inferred.
        """
        default_to_square = True
        if "shortest_edge" in size:
            size = size["shortest_edge"]
            default_to_square = False
        elif "height" in size and "width" in size:
            size = (size["height"], size["width"])
        else:
            raise ValueError("Size must contain either 'shortest_edge' or 'height' and 'width'.")

        output_size = get_resize_output_image_size(
            image,
            size=size,
            default_to_square=default_to_square,
            input_data_format=input_data_format,
        )
        return resize(
            image,
            size=output_size,
            resample=resample,
            data_format=data_format,
            input_data_format=input_data_format,
            **kwargs,
        )

    def chunk(
        self, video: VideoInput, fps: int, chunk_duration: float, num_chunks: int, num_frames_per_chunk: int
    ) -> List[VideoInput]:
        """
        Uniformly sample `num_chunks` chunks of duration `chunk_duration` from a video.

        Args:
            video (`VideoInput`):
                Video to chunk.
            fps (`int`):
                Frame rate of the video
            chunk_duration (`float`):
                Duration of each chunk.
            num_chunks (`int`):
                Number of chunks to sample.
            num_frames_per_chunk (`int`):
                Number of frames to sample per chunk.
        """
        video_duration = len(video) / fps
        if video_duration < chunk_duration:
            logger.warning_once(
                "Chunk duration is greater than audio duration. Chunks will be repeated, consider adjusting either `chunk_duration` or `num_chunks`"
                "to avoid unnecessary memory/compute usage."
            )

        all_clips_timepoints = uniform_chunk_sampling(video_duration, chunk_duration, num_chunks)

        all_clips = []
        for clip_timepoints in all_clips_timepoints:
            video_clip = video[math.ceil(clip_timepoints[0] * fps) : math.ceil(clip_timepoints[1] * fps)]
            video_clip = uniform_temporal_subsample(video_clip, num_samples=num_frames_per_chunk)
            all_clips.append(video_clip)

        return all_clips

    # Copied from models.clip.image_processing_clip.CLIPImageProcessor.preprocess with preprocess->_preprocess_image
    def _preprocess_image(
        self,
        images: ImageInput,
        do_resize: bool = None,
        size: Dict[str, int] = None,
        resample: PILImageResampling = None,
        do_center_crop: bool = None,
        crop_size: int = None,
        do_rescale: bool = None,
        rescale_factor: float = None,
        do_normalize: bool = None,
        image_mean: Optional[Union[float, List[float]]] = None,
        image_std: Optional[Union[float, List[float]]] = None,
        do_convert_rgb: bool = None,
        data_format: Optional[ChannelDimension] = ChannelDimension.FIRST,
        input_data_format: Optional[Union[str, ChannelDimension]] = None,
    ) -> np.ndarray:
        validate_preprocess_arguments(
            do_rescale=do_rescale,
            rescale_factor=rescale_factor,
            do_normalize=do_normalize,
            image_mean=image_mean,
            image_std=image_std,
            do_center_crop=do_center_crop,
            crop_size=crop_size,
            do_resize=do_resize,
            size=size,
            resample=resample,
        )

        if do_convert_rgb:
            images = [convert_to_rgb(image) for image in images]

        # All transformations expect numpy arrays.
        images = [to_numpy_array(image) for image in images]

        if is_scaled_image(images[0]) and do_rescale:
            logger.warning_once(
                "It looks like you are trying to rescale already rescaled images. If the input"
                " images have pixel values between 0 and 1, set `do_rescale=False` to avoid rescaling them again."
            )

        if input_data_format is None:
            # We assume that all images have the same channel dimension format.
            input_data_format = infer_channel_dimension_format(images[0])

        if do_resize:
            images = [
                self.resize(image=image, size=size, resample=resample, input_data_format=input_data_format)
                for image in images
            ]

        if do_center_crop:
            images = [
                self.center_crop(image=image, size=crop_size, input_data_format=input_data_format) for image in images
            ]

        if do_rescale:
            images = [
                self.rescale(image=image, scale=rescale_factor, input_data_format=input_data_format)
                for image in images
            ]

        if do_normalize:
            images = [
                self.normalize(image=image, mean=image_mean, std=image_std, input_data_format=input_data_format)
                for image in images
            ]

        images = [
            to_channel_dimension_format(image, data_format, input_channel_dim=input_data_format) for image in images
        ]

        return images

    # Ignore copy
    def preprocess(
        self,
        images: Optional[ImageInput] = None,
        videos: Optional[VideoInput] = None,
        do_resize: bool = None,
        size: Dict[str, int] = None,
        resample: PILImageResampling = None,
        do_center_crop: bool = None,
        crop_size: int = None,
        do_rescale: bool = None,
        rescale_factor: float = None,
        do_normalize: bool = None,
        image_mean: Optional[Union[float, List[float]]] = None,
        image_std: Optional[Union[float, List[float]]] = None,
        do_convert_rgb: bool = None,
        do_chunk: bool = None,
        chunk_duration: float = None,
        num_chunks: int = None,
        num_frames_per_chunk: int = None,
        fps: int = None,
        return_tensors: Optional[Union[str, TensorType]] = None,
        data_format: Optional[ChannelDimension] = ChannelDimension.FIRST,
        input_data_format: Optional[Union[str, ChannelDimension]] = None,
        **kwargs,
    ) -> PIL.Image.Image:
        """
        Preprocess an image or batch of images.

        Args:
            images (`ImageInput`, *optional*):
                Image to preprocess. Expects a single or batch of images with pixel values ranging from 0 to 255. If
                passing in images with pixel values between 0 and 1, set `do_rescale=False`. Either `images` or
                `videos` must be provided.
            videos (`VideoInput`, *optional*):
                Video to preprocess. Expects a single or batch of videos with pixel values ranging from 0 to 255. If
                passing in videos with pixel values between 0 and 1, set `do_rescale=False`. Either `images` or
                `videos` must be provided.
            do_resize (`bool`, *optional*, defaults to `self.do_resize`):
                Whether to resize the image.
            size (`Dict[str, int]`, *optional*, defaults to `self.size`):
                Size of the image after resizing. Shortest edge of the image is resized to size["shortest_edge"], with
                the longest edge resized to keep the input aspect ratio.
            resample (`int`, *optional*, defaults to `self.resample`):
                Resampling filter to use if resizing the image. This can be one of the enum `PILImageResampling`. Only
                has an effect if `do_resize` is set to `True`.
            do_center_crop (`bool`, *optional*, defaults to `self.do_center_crop`):
                Whether to center crop the image.
            crop_size (`Dict[str, int]`, *optional*, defaults to `self.crop_size`):
                Size of the center crop. Only has an effect if `do_center_crop` is set to `True`.
            do_rescale (`bool`, *optional*, defaults to `self.do_rescale`):
                Whether to rescale the image.
            rescale_factor (`float`, *optional*, defaults to `self.rescale_factor`):
                Rescale factor to rescale the image by if `do_rescale` is set to `True`.
            do_normalize (`bool`, *optional*, defaults to `self.do_normalize`):
                Whether to normalize the image.
            image_mean (`float` or `List[float]`, *optional*, defaults to `self.image_mean`):
                Image mean to use for normalization. Only has an effect if `do_normalize` is set to `True`.
            image_std (`float` or `List[float]`, *optional*, defaults to `self.image_std`):
                Image standard deviation to use for normalization. Only has an effect if `do_normalize` is set to
                `True`.
            do_convert_rgb (`bool`, *optional*, defaults to `self.do_convert_rgb`):
                Whether to convert the image to RGB.
            do_chunk (`bool`, *optional*, defaults to `self.do_chunk`):
                Whether to chunk the video into multiple clips.
            chunk_duration (`float`, *optional*, defaults to `self.chunk_duration`):
                Duration of each chunk in seconds.
            num_chunks (`int`, *optional*, defaults to `self.num_chunks`):
                Number of chunks to sample.
            num_frames_per_chunk (`int`, *optional*, defaults to `self.num_frames_per_chunk`):
                Number of frames to sample per chunk.
            fps (`int`, *optional*, defaults to `self.fps`):
                Frame rate of the video. It's assumed that all videos have the same frame rate.
            return_tensors (`str` or `TensorType`, *optional*):
                The type of tensors to return. Can be one of:
                - Unset: Return a list of `np.ndarray`.
                - `TensorType.TENSORFLOW` or `'tf'`: Return a batch of type `tf.Tensor`.
                - `TensorType.PYTORCH` or `'pt'`: Return a batch of type `torch.Tensor`.
                - `TensorType.NUMPY` or `'np'`: Return a batch of type `np.ndarray`.
                - `TensorType.JAX` or `'jax'`: Return a batch of type `jax.numpy.ndarray`.
            data_format (`ChannelDimension` or `str`, *optional*, defaults to `ChannelDimension.FIRST`):
                The channel dimension format for the output image. Can be one of:
                - `"channels_first"` or `ChannelDimension.FIRST`: image in (num_channels, height, width) format.
                - `"channels_last"` or `ChannelDimension.LAST`: image in (height, width, num_channels) format.
                - Unset: Use the channel dimension format of the input image.
            input_data_format (`ChannelDimension` or `str`, *optional*):
                The channel dimension format for the input image. If unset, the channel dimension format is inferred
                from the input image. Can be one of:
                - `"channels_first"` or `ChannelDimension.FIRST`: image in (num_channels, height, width) format.
                - `"channels_last"` or `ChannelDimension.LAST`: image in (height, width, num_channels) format.
                - `"none"` or `ChannelDimension.NONE`: image in (height, width) format.
        """
        if images is None and videos is None:
            raise ValueError("Either `images` or `videos` must be provided.")

        if images is not None and videos is not None:
            raise ValueError("Only one of `images` or `videos` can be provided.")

        do_resize = do_resize if do_resize is not None else self.do_resize
        size = size if size is not None else self.size
        size = get_size_dict(size, param_name="size", default_to_square=False)
        resample = resample if resample is not None else self.resample
        do_center_crop = do_center_crop if do_center_crop is not None else self.do_center_crop
        crop_size = crop_size if crop_size is not None else self.crop_size
        crop_size = get_size_dict(crop_size, param_name="crop_size", default_to_square=True)
        do_rescale = do_rescale if do_rescale is not None else self.do_rescale
        rescale_factor = rescale_factor if rescale_factor is not None else self.rescale_factor
        do_normalize = do_normalize if do_normalize is not None else self.do_normalize
        image_mean = image_mean if image_mean is not None else self.image_mean
        image_std = image_std if image_std is not None else self.image_std
        do_convert_rgb = do_convert_rgb if do_convert_rgb is not None else self.do_convert_rgb
        do_chunk = do_chunk if do_chunk is not None else self.do_chunk
        chunk_duration = chunk_duration if chunk_duration is not None else self.chunk_duration
        num_chunks = num_chunks if num_chunks is not None else self.num_chunks
        num_frames_per_chunk = num_frames_per_chunk if num_frames_per_chunk is not None else self.num_frames_per_chunk
        fps = fps if fps is not None else self.fps

        if images is not None:
            images = make_list_of_images(images)
        if videos is not None:
            videos = make_batched_videos(videos)

        validate_kwargs(captured_kwargs=kwargs.keys(), valid_processor_keys=self._valid_processor_keys)

        if (videos is not None and not valid_images(videos)) or (images is not None and not valid_images(images)):
            raise ValueError(
                "Invalid input type. Must be of type PIL.Image.Image, numpy.ndarray, "
                "torch.Tensor, tf.Tensor or jax.ndarray."
            )

        if images is not None:
            pixel_values = self._preprocess_image(
                images=images,
                do_resize=do_resize,
                size=size,
                resample=resample,
                do_center_crop=do_center_crop,
                crop_size=crop_size,
                do_rescale=do_rescale,
                rescale_factor=rescale_factor,
                do_normalize=do_normalize,
                image_mean=image_mean,
                image_std=image_std,
                do_convert_rgb=do_convert_rgb,
                data_format=data_format,
                input_data_format=input_data_format,
            )
        else:
            pixel_values = []
            for video in videos:
                if do_chunk:
                    clips = self.chunk(
                        video=video,
                        fps=fps,
                        chunk_duration=chunk_duration,
                        num_chunks=num_chunks,
                        num_frames_per_chunk=num_frames_per_chunk,
                    )

                    _pixel_values = [
                        self._preprocess_image(
                            images=clip,
                            do_resize=do_resize,
                            size=size,
                            resample=PILImageResampling.BILINEAR,
                            do_center_crop=do_center_crop,
                            crop_size=crop_size,
                            do_rescale=do_rescale,
                            rescale_factor=rescale_factor,
                            do_normalize=do_normalize,
                            image_mean=image_mean,
                            image_std=image_std,
                            do_convert_rgb=do_convert_rgb,
                            data_format=data_format,
                            input_data_format=input_data_format,
                        )
                        for clip in clips
                    ]
                else:
                    _pixel_values = [
                        self._preprocess_image(
                            images=video,
                            do_resize=do_resize,
                            size=size,
                            resample=resample,
                            do_center_crop=do_center_crop,
                            crop_size=crop_size,
                            do_rescale=do_rescale,
                            rescale_factor=rescale_factor,
                            do_normalize=do_normalize,
                            image_mean=image_mean,
                            image_std=image_std,
                            do_convert_rgb=do_convert_rgb,
                            data_format=data_format,
                            input_data_format=input_data_format,
                        )
                    ]

                # Avoid List[List[List[np.ndarray]]]
                _pixel_values = np.stack(_pixel_values)
                # Make it shape (num_chunks, num_channels, num_frames_per_chunk, height, width)
                _pixel_values = np.swapaxes(_pixel_values, 1, 2)
                pixel_values.append(_pixel_values)

        return BatchFeature(data={"pixel_values": pixel_values}, tensor_type=return_tensors)
    
