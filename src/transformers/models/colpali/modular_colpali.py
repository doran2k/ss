# coding=utf-8
# Copyright 2024 The HuggingFace Inc. team.
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


from dataclasses import dataclass
from typing import ClassVar, List, Optional, Tuple, Union

import torch
import torch.utils.checkpoint
from torch import nn

from transformers.models.paligemma.configuration_paligemma import PaliGemmaConfig
from transformers.models.paligemma.modeling_paligemma import PaliGemmaForConditionalGeneration
from transformers.models.paligemma.processing_paligemma import (
    IMAGE_TOKEN,
    PaliGemmaProcessor,
    build_string_from_input,
    make_batched_images,
)

from ...cache_utils import Cache
from ...feature_extraction_utils import BatchFeature
from ...image_utils import ImageInput, is_valid_image
from ...processing_utils import (
    ProcessingKwargs,
    Unpack,
)
from ...tokenization_utils_base import (
    PreTokenizedInput,
    TextInput,
)
from ...utils import (
    ModelOutput,
    add_start_docstrings,
    add_start_docstrings_to_model_forward,
    is_flash_attn_2_available,
    logging,
    replace_return_docstrings,
)


if is_flash_attn_2_available():
    from flash_attn.bert_padding import index_first_axis, pad_input, unpad_input  # noqa


logger = logging.get_logger(__name__)


class ColPaliConfig(PaliGemmaConfig):
    r"""
    This is the configuration class to store the configuration of a [`ColPaliForRetrieval`]. It is used to instantiate an
    ColPaliForRetrieval according to the specified arguments, defining the model architecture.

    The ColPali config is very similar to [`PaligemmaConfig`], but with an extra attribute defining the embedding dimension.

    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information.


    Args:
        vision_config (`PaliGemmaVisionConfig`,  *optional*):
            Custom vision config or dict
        text_config (`Union[AutoConfig, dict]`, *optional*):
            The config object of the text backbone. Can be any of `LlamaConfig` or `MistralConfig`.
        ignore_index (`int`, *optional*, defaults to -100):
            The ignore index for the loss function.
        image_token_index (`int`, *optional*, defaults to 256000):
            The image token index to encode the image prompt.
        vocab_size (`int`, *optional*, defaults to 257152):
            Vocabulary size of the PaliGemmamodel. Defines the number of different tokens that can be represented by the
            `inputs_ids` passed when calling [`~PaliGemmaForConditionalGeneration`]
        projection_dim (`int`, *optional*, defaults to 2048):
            Dimension of the multimodal projection space.
        hidden_size (`int`, *optional*, defaults to 2048):
            Dimension of the hidden layer of the Language model.
        embedding_dim (`int`, *optional*, defaults to 128):
            Dimension of the multi-vector embeddings produced by the model.

    Example:

    ```python
    from transformers.models.colpali import ColPaliConfig, ColPaliForRetrieval

    config = ColPaliConfig()
    model = ColPaliForRetrieval(config)
    ```
    """

    def __init__(
        self,
        vision_config=None,
        text_config=None,
        ignore_index=-100,
        image_token_index=256000,
        vocab_size=257152,
        projection_dim=2048,
        hidden_size=2048,
        embedding_dim: int = 128,
        **kwargs,
    ):
        super().__init__(
            vision_config=vision_config,
            text_config=text_config,
            ignore_index=ignore_index,
            image_token_index=image_token_index,
            vocab_size=vocab_size,
            projection_dim=projection_dim,
            hidden_size=hidden_size,
            **kwargs,
        )
        self.model_type = "colpali"
        self.is_composition = False
        self.embedding_dim = embedding_dim


class ColPaliProcessorKwargs(ProcessingKwargs, total=False):
    _defaults = {
        "text_kwargs": {
            "padding": "longest",
        },
        "images_kwargs": {
            "data_format": "channels_first",
            "do_convert_rgb": True,
        },
        "common_kwargs": {"return_tensors": "pt"},
    }


class ColPaliProcessor(PaliGemmaProcessor):
    r"""
    Constructs a ColPali processor which wraps a PaliGemmaProcessor and special methods to process images and queries, as
    well as to compute the late-interaction retrieval score.

    [`ColPaliProcessor`] offers all the functionalities of [`PaliGemmaProcessor`]. See the [`~PaliGemmaProcessor.__call__`]
     for more information.

    Args:
        image_processor ([`SiglipImageProcessor`], *optional*):
            The image processor is a required input.
        tokenizer ([`LlamaTokenizerFast`], *optional*):
            The tokenizer is a required input.
        chat_template (`str`, *optional*): A Jinja template which will be used to convert lists of messages
            in a chat into a tokenizable string.
    """

    visual_prompt_prefix: ClassVar[str] = "Describe the image."
    query_prefix: ClassVar[str] = "Question: "

    @property
    def query_augmentation_token(self) -> str:
        """
        Return the query augmentation token.
        Query augmentation buffers are used as reasoning buffers during inference.
        """
        return self.tokenizer.pad_token

    def __call__(
        self,
        images: ImageInput = None,
        text: Union[TextInput, PreTokenizedInput, List[TextInput], List[PreTokenizedInput]] = None,
        audio=None,
        videos=None,
        **kwargs: Unpack[ColPaliProcessorKwargs],
    ) -> BatchFeature:
        """
        Main method to prepare for the model either (1) one or several texts, either (2) one or several image(s). This method is custom
        wrapper around the PaliGemmaProcessor's [`~PaliGemmaProcessor.__call__`] method adapted for the ColPali model. It cannot process
        both text and images at the same time.

        When preparing the the text(s), this method forwards the `text` and `kwargs` arguments to LlamaTokenizerFast's
        [`~LlamaTokenizerFast.__call__`].
        When preparing the the image(s), this method forwards the `images` and `kwargs` arguments to SiglipImageProcessor's
        [`~SiglipImageProcessor.__call__`].
        Please refer to the doctsring of the above two methods for more information.

        Args:
            images (`PIL.Image.Image`, `np.ndarray`, `torch.Tensor`, `List[PIL.Image.Image]`, `List[np.ndarray]`, `List[torch.Tensor]`):
                The image or batch of images to be prepared. Each image can be a PIL image, NumPy array or PyTorch
                tensor. In case of a NumPy array/PyTorch tensor, each image should be of shape (C, H, W), where C is a
                number of channels, H and W are image height and width.
            text (`str`, `List[str]`, `List[List[str]]`):
                The sequence or batch of sequences to be encoded. Each sequence can be a string or a list of strings
                (pretokenized string). If the sequences are provided as list of strings (pretokenized), you must set
                `is_split_into_words=True` (to lift the ambiguity with a batch of sequences).
            return_tensors (`str` or [`~utils.TensorType`], *optional*):
                If set, will return tensors of a particular framework. Acceptable values are:

                - `'tf'`: Return TensorFlow `tf.constant` objects.
                - `'pt'`: Return PyTorch `torch.Tensor` objects.
                - `'np'`: Return NumPy `np.ndarray` objects.
                - `'jax'`: Return JAX `jnp.ndarray` objects.

        Returns:
            [`BatchFeature`]: A [`BatchFeature`] with the following fields:

            - **input_ids** -- List of token ids to be fed to a model.
            - **attention_mask** -- List of indices specifying which tokens should be attended to by the model (when
              `return_attention_mask=True` or if *"attention_mask"* is in `self.model_input_names` and if `text` is not
              `None`).
            - **pixel_values** -- Pixel values to be fed to a model. Returned when `images` is not `None`.
        """
        output_kwargs = self._merge_kwargs(
            ColPaliProcessorKwargs,
            tokenizer_init_kwargs=self.tokenizer.init_kwargs,
            **kwargs,
        )
        suffix = output_kwargs["text_kwargs"].pop("suffix", None)

        return_token_type_ids = True if suffix is not None else False

        if text is None and images is None:
            raise ValueError("Either text or images must be provided")
        if text is not None and images is not None:
            raise ValueError("Only one of text or images can be processed at a time")

        if images is not None:
            if is_valid_image(images):
                images = [images]
            elif isinstance(images, list) and is_valid_image(images[0]):
                pass
            elif not (isinstance(images, list) and isinstance(images[0], list) and is_valid_image(images[0][0])):
                raise ValueError("images must be an image, list of images or list of list of images")

            texts_doc = [self.visual_prompt_prefix] * len(images)
            images = [image.convert("RGB") for image in images]

            input_strings = [
                build_string_from_input(
                    prompt=prompt,
                    bos_token=self.tokenizer.bos_token,
                    image_seq_len=self.image_seq_length,
                    image_token=IMAGE_TOKEN,
                    num_images=len(image_list) if isinstance(image_list, list) else 1,
                )
                for prompt, image_list in zip(texts_doc, images)
            ]
            images = make_batched_images(images)
            pixel_values = self.image_processor(images, **output_kwargs["images_kwargs"])["pixel_values"]

            # max_length has to account for the image tokens
            if output_kwargs["text_kwargs"].get("max_length", None) is not None:
                output_kwargs["text_kwargs"]["max_length"] += self.image_seq_length

            inputs = self.tokenizer(
                input_strings,
                return_token_type_ids=False,
                **output_kwargs["text_kwargs"],
            )

            return_data = {**inputs, "pixel_values": pixel_values}

            if return_token_type_ids:
                labels = inputs["input_ids"].masked_fill(inputs["token_type_ids"] == 0, -100)
                return_data.update({"labels": labels})

            return BatchFeature(data=return_data)

        elif text is not None:
            if isinstance(text, str):
                text = [text]
            elif not (isinstance(text, list) and isinstance(text[0], str)):
                raise ValueError("Text must be a string or a list of strings")

            if suffix is None:
                suffix = self.query_augmentation_token * 10
            texts_query: List[str] = []

            for query in text:
                query = self.tokenizer.bos_token + self.query_prefix + query
                query += suffix  # add suffix (pad tokens)
                query += "\n"  # make input ISO to PaliGemma's processor
                texts_query.append(query)

            output_kwargs["text_kwargs"]["max_length"] = output_kwargs["text_kwargs"].get("max_length", 50)

            batch_query = self.tokenizer(
                texts_query,
                return_token_type_ids=False,
                **output_kwargs["text_kwargs"],
            )

            return batch_query

    def process_images(
        self,
        images: ImageInput = None,
        **kwargs: Unpack[ColPaliProcessorKwargs],
    ) -> BatchFeature:
        """
        Prepare for the model one or several image(s). This method is a wrapper around the `__call__` method of the ColPaliProcessor's
        [`ColPaliProcessor.__call__`].

        This method forwards the `images` and `kwargs` arguments to SiglipImageProcessor's [`~SiglipImageProcessor.__call__`].

        Args:
            images (`PIL.Image.Image`, `np.ndarray`, `torch.Tensor`, `List[PIL.Image.Image]`, `List[np.ndarray]`, `List[torch.Tensor]`):
                The image or batch of images to be prepared. Each image can be a PIL image, NumPy array or PyTorch
                tensor. In case of a NumPy array/PyTorch tensor, each image should be of shape (C, H, W), where C is a
                number of channels, H and W are image height and width.
            return_tensors (`str` or [`~utils.TensorType`], *optional*):
                If set, will return tensors of a particular framework. Acceptable values are:

                - `'tf'`: Return TensorFlow `tf.constant` objects.
                - `'pt'`: Return PyTorch `torch.Tensor` objects.
                - `'np'`: Return NumPy `np.ndarray` objects.
                - `'jax'`: Return JAX `jnp.ndarray` objects.

        Returns:
            [`BatchFeature`]: A [`BatchFeature`] with the following fields:

            - **input_ids** -- List of token ids to be fed to a model.
            - **attention_mask** -- List of indices specifying which tokens should be attended to by the model (when
              `return_attention_mask=True` or if *"attention_mask"* is in `self.model_input_names` and if `text` is not
              `None`).
            - **pixel_values** -- Pixel values to be fed to a model. Returned when `images` is not `None`.
        """
        return self.__call__(images=images, **kwargs)

    def process_queries(
        self,
        text: Union[TextInput, List[TextInput]],
        **kwargs: Unpack[ColPaliProcessorKwargs],
    ) -> BatchFeature:
        """
        Prepare for the model one or several texts. This method is a wrapper around the `__call__` method of the ColPaliProcessor's
        [`ColPaliProcessor.__call__`].

        This method forwards the `text` and `kwargs` arguments to LlamaTokenizerFast's [`~LlamaTokenizerFast.__call__`].

        Args:
            text (`str`, `List[str]`, `List[List[str]]`):
                The sequence or batch of sequences to be encoded. Each sequence can be a string or a list of strings
                (pretokenized string). If the sequences are provided as list of strings (pretokenized), you must set
                `is_split_into_words=True` (to lift the ambiguity with a batch of sequences).
            return_tensors (`str` or [`~utils.TensorType`], *optional*):
                If set, will return tensors of a particular framework. Acceptable values are:

                - `'tf'`: Return TensorFlow `tf.constant` objects.
                - `'pt'`: Return PyTorch `torch.Tensor` objects.
                - `'np'`: Return NumPy `np.ndarray` objects.
                - `'jax'`: Return JAX `jnp.ndarray` objects.

        Returns:
            [`BatchFeature`]: A [`BatchFeature`] with the following fields:

            - **input_ids** -- List of token ids to be fed to a model.
            - **attention_mask** -- List of indices specifying which tokens should be attended to by the model (when
              `return_attention_mask=True` or if *"attention_mask"* is in `self.model_input_names` and if `text` is not
              `None`).
        """
        return self.__call__(text=text, **kwargs)

    def score_retrieval(
        self,
        query_embeddings: Union[torch.Tensor, List[torch.Tensor]],
        passage_embeddings: Union[torch.Tensor, List[torch.Tensor]],
        batch_size: int = 128,
        output_dtype: Optional[torch.dtype] = torch.float32,
        output_device: Union[torch.device, str] = "cpu",
    ) -> torch.Tensor:
        """
        Compute the late-interaction/MaxSim score (ColBERT-like) for the given multi-vector
        query embeddings (`qs`) and passage embeddings (`ps`). For ColPali, a passage is the
        image of a document page.

        Because the embedding tensors are multi-vector and can thus have different shapes, they
        should be fed as:
        (1) a list of tensors, where the i-th tensor is of shape (sequence_length_i, embedding_dim)
        (2) a single tensor of shape (n_passages, max_sequence_length, embedding_dim) -> usually
            obtained by padding the list of tensors.

        Args:
            query_embeddings (`Union[torch.Tensor, List[torch.Tensor]`): Query embeddings.
            passage_embeddings (`Union[torch.Tensor, List[torch.Tensor]`): Passage embeddings.
            batch_size (`int`, *optional*, defaults to 128): Batch size for computing scores.
            output_dtype (`torch.dtype`, *optional*, defaults to `torch.float32`): The dtype of the output tensor.
                If `None`, the dtype of the input embeddings is used.
            output_device (`torch.device` or `str`, *optional*, defaults to "cpu"): The device of the output tensor.

        Returns:
            `torch.Tensor`: A tensor of shape `(n_queries, n_passages)` containing the scores. The score
            tensor is saved on the "cpu" device.
        """

        if len(query_embeddings) == 0:
            raise ValueError("No queries provided")
        if len(passage_embeddings) == 0:
            raise ValueError("No passages provided")

        if query_embeddings[0].device != passage_embeddings[0].device:
            raise ValueError("Queries and passages must be on the same device")

        if query_embeddings[0].dtype != passage_embeddings[0].dtype:
            raise ValueError("Queries and passages must have the same dtype")

        if output_dtype is None:
            output_dtype = query_embeddings[0].dtype

        scores: List[torch.Tensor] = []

        for i in range(0, len(query_embeddings), batch_size):
            batch_scores: List[torch.Tensor] = []
            batch_queries = torch.nn.utils.rnn.pad_sequence(
                query_embeddings[i : i + batch_size], batch_first=True, padding_value=0
            )
            for j in range(0, len(passage_embeddings), batch_size):
                batch_passages = torch.nn.utils.rnn.pad_sequence(
                    passage_embeddings[j : j + batch_size], batch_first=True, padding_value=0
                )
                batch_scores.append(
                    torch.einsum("bnd,csd->bcns", batch_queries, batch_passages).max(dim=3)[0].sum(dim=2)
                )
            scores.append(torch.cat(batch_scores, dim=1).to(output_dtype).to(output_device))

        return torch.cat(scores, dim=0)

    def get_n_patches(
        self,
        image_size: Tuple[int, int],  # for API consistency wrt to colpali-engine's interpretability module
        patch_size: int,
    ) -> Tuple[int, int]:
        """
        Return the number of patches (n_patches_x, n_patches_y) for the give image along the two image axis.
        """
        n_patches_x = self.image_processor.size["width"] // patch_size
        n_patches_y = self.image_processor.size["height"] // patch_size

        return n_patches_x, n_patches_y

    def get_image_mask(self, batch_images: BatchFeature) -> torch.Tensor:
        """
        Return an image mask that indicates which input tokens correspond to visual tokens.
        """
        return batch_images.input_ids == self.image_token_id


@dataclass
class ColPaliForRetrievalOutput(ModelOutput):
    """
    Base class for ColPali embeddings output.

    Args:
        loss (`torch.FloatTensor` of shape `(1,)`, *optional*, returned when `labels` is provided):
            Language modeling loss (for next-token prediction).
        embeddings (`torch.FloatTensor` of shape `(batch_size, sequence_length, hidden_size)`):
            The embeddings of the model.
        past_key_values (`tuple(tuple(torch.FloatTensor))`, *optional*, returned when `use_cache=True` is passed or when `config.use_cache=True`):
            Tuple of `tuple(torch.FloatTensor)` of length `config.n_layers`, with each tuple having 2 tensors of shape
            `(batch_size, num_heads, sequence_length, embed_size_per_head)`)

            Contains pre-computed hidden-states (key and values in the self-attention blocks) that can be used (see
            `past_key_values` input) to speed up sequential decoding.
        hidden_states (`tuple(torch.FloatTensor)`, *optional*, returned when `output_hidden_states=True` is passed or when `config.output_hidden_states=True`):
            Tuple of `torch.FloatTensor` (one for the output of the embeddings, if the model has an embedding layer, +
            one for the output of each layer) of shape `(batch_size, sequence_length, hidden_size)`.

            Hidden-states of the model at the output of each layer plus the optional initial embedding outputs.
        attentions (`tuple(torch.FloatTensor)`, *optional*, returned when `output_attentions=True` is passed or when `config.output_attentions=True`):
            Tuple of `torch.FloatTensor` (one for each layer) of shape `(batch_size, num_heads, sequence_length,
            sequence_length)`.

            Attentions weights after the attention softmax, used to compute the weighted average in the self-attention
            heads.
        image_hidden_states (`torch.FloatTensor`, *optional*):
            A `torch.FloatTensor` of size `(batch_size, num_images, sequence_length, hidden_size)`.
            image_hidden_states of the model produced by the vision encoder after projecting last hidden state.
    """

    loss: Optional[torch.FloatTensor] = None
    embeddings: torch.Tensor = None
    past_key_values: Optional[Union[List[torch.FloatTensor], Cache]] = None
    hidden_states: Optional[Tuple[torch.FloatTensor]] = None
    attentions: Optional[Tuple[torch.FloatTensor]] = None
    image_hidden_states: Optional[torch.FloatTensor] = None


COLPALI_FOR_RETRIEVAL_INPUT_DOCSTRING = r"""
    Args:
        input_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`):
            Indices of input sequence tokens in the vocabulary. Padding will be ignored by default should you provide
            it.
            Indices can be obtained using [`AutoTokenizer`]. See [`PreTrainedTokenizer.encode`] and
            [`PreTrainedTokenizer.__call__`] for details.
            [What are input IDs?](../glossary#input-ids)
        pixel_values (`torch.FloatTensor` of shape `(batch_size, num_channels, image_size, image_size)):
            The tensors corresponding to the input images. Pixel values can be obtained using
            [`AutoImageProcessor`]. See [`SiglipImageProcessor.__call__`] for details ([]`PaliGemmaProcessor`] uses
            [`SiglipImageProcessor`] for processing images). If none, ColPali will only process text (query embeddings).
        attention_mask (`torch.Tensor` of shape `(batch_size, sequence_length)`, *optional*):
            Mask to avoid performing attention on padding token indices. Mask values selected in `[0, 1]`:
            - 1 for tokens that are **not masked**,
            - 0 for tokens that are **masked**.
            [What are attention masks?](../glossary#attention-mask)
            Indices can be obtained using [`AutoTokenizer`]. See [`PreTrainedTokenizer.encode`] and
            [`PreTrainedTokenizer.__call__`] for details.
            If `past_key_values` is used, optionally only the last `decoder_input_ids` have to be input (see
            `past_key_values`).
            If you want to change padding behavior, you should read [`modeling_opt._prepare_decoder_attention_mask`]
            and modify to your needs. See diagram 1 in [the paper](https://arxiv.org/abs/1910.13461) for more
            information on the default strategy.
            - 1 indicates the head is **not masked**,
            - 0 indicates the head is **masked**.
        position_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
            Indices of positions of each input sequence tokens in the position embeddings. Selected in the range `[0,
            config.n_positions - 1]`.

            [What are position IDs?](../glossary#position-ids)
        past_key_values (`Cache` or `tuple(tuple(torch.FloatTensor))`, *optional*):
            Pre-computed hidden-states (key and values in the self-attention blocks and in the cross-attention
            blocks) that can be used to speed up sequential decoding. This typically consists in the `past_key_values`
            returned by the model at a previous stage of decoding, when `use_cache=True` or `config.use_cache=True`.

            Two formats are allowed:
            - a [`~cache_utils.Cache`] instance, see our
            [kv cache guide](https://huggingface.co/docs/transformers/en/kv_cache);
            - Tuple of `tuple(torch.FloatTensor)` of length `config.n_layers`, with each tuple having 2 tensors of
            shape `(batch_size, num_heads, sequence_length, embed_size_per_head)`). This is also known as the legacy
            cache format.

            The model will output the same cache format that is fed as input. If no `past_key_values` are passed, the
            legacy cache format will be returned.

            If `past_key_values` are used, the user can optionally input only the last `input_ids` (those that don't
            have their past key value states given to this model) of shape `(batch_size, 1)` instead of all `input_ids`
            of shape `(batch_size, sequence_length)`.
        inputs_embeds (`torch.FloatTensor` of shape `(batch_size, sequence_length, hidden_size)`, *optional*):
            Optionally, instead of passing `input_ids` you can choose to directly pass an embedded representation. This
            is useful if you want more control over how to convert `input_ids` indices into associated vectors than the
            model's internal embedding lookup matrix.
        labels (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
            Labels for computing the masked language modeling loss. Indices should either be in `[0, ...,
            config.vocab_size]` or -100 (see `input_ids` docstring). Tokens with indices set to `-100` are ignored
            (masked), the loss is only computed for the tokens with labels in `[0, ..., config.vocab_size]`.
        use_cache (`bool`, *optional*):
            If set to `True`, `past_key_values` key value states are returned and can be used to speed up decoding (see
            `past_key_values`).
        output_attentions (`bool`, *optional*):
            Whether or not to return the attentions tensors of all attention layers. See `attentions` under returned
            tensors for more detail.
        output_hidden_states (`bool`, *optional*):
            Whether or not to return the hidden states of all layers. See `hidden_states` under returned tensors for
            more detail.
        return_dict (`bool`, *optional*):
            Whether or not to return a [`~utils.ModelOutput`] instead of a plain tuple.
        num_logits_to_keep (`int`, *optional*):
            Calculate logits for the last `num_logits_to_keep` tokens. If `0`, calculate logits for all
            `input_ids` (special case). Only last token logits are needed for generation, and calculating them only for that
            token can save memory, which becomes pretty significant for long sequences or large vocabulary size.

    ```python
    import torch
    from PIL import Image

    from transformers import ColPaliForRetrieval, ColPaliProcessor

    model_name = "vidore/colpali-v1.2-hf"

    model = ColPaliForRetrieval.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map="cuda:0",  # or "mps" if on Apple Silicon
    ).eval()

    processor = ColPaliProcessor.from_pretrained(model_name)

    # Your inputs
    images = [
        Image.new("RGB", (32, 32), color="white"),
        Image.new("RGB", (16, 16), color="black"),
    ]
    queries = [
        "What is the organizational structure for our R&D department?",
        "Can you provide a breakdown of last year’s financial performance?",
    ]

    # Process the inputs
    batch_images = processor(images=images).to(model.device)
    batch_queries = processor(text=queries).to(model.device)

    # Forward pass
    with torch.no_grad():
        image_embeddings = model(**batch_images)
        query_embeddings = model(**batch_queries)

    scores = processor.score_retrieval(query_embeddings, image_embeddings)
    ```
"""


@add_start_docstrings(
    """
    ColPali leverages Vision Language Models (VLMs) to construct efficient multi-vector embeddings in the visual space for document retrieval.
    By feeding the ViT output patches from PaliGemma-3B to a linear projection, we create a multi-vector representation of documents. The model
    is trained to maximize the similarity between these document embeddings and the query embeddings, following the ColBERT method.

    Using ColPali removes the need for potentially complex and brittle layout recognition and OCR pipelines with a single model that can take into account
    both the textual and visual content (layout, charts, ...) of a document.

    ColPali was introduced in the following paper: [*ColPali: Efficient Document Retrieval with Vision Language Models*](https://arxiv.org/abs/2407.01449).

    Resources:
    - A blog post detailing ColPali, a vision retrieval model, can be found [here](https://huggingface.co/blog/manu/colpali). 📝
    - The code for using and training the original ColPali model and for the `colpali-engine` package can be found [here](https://github.com/illuin-tech/colpali). 🌎
    - Cookbooks to fine-tune ColPali (with optional quantization), generate similarity maps, ... can be found [here](https://github.com/tonywu71/colpali-cookbooks). 📚
    """
)
class ColPaliForRetrieval(PaliGemmaForConditionalGeneration):
    main_input_name: ClassVar[str] = "input_ids"  # transformers-related

    def __init__(self, config: ColPaliConfig):
        super().__init__(config=config)

        self.embedding_dim = self.config.embedding_dim
        self.custom_text_proj = nn.Linear(self.config.text_config.hidden_size, self.embedding_dim)

        if self.language_model._tied_weights_keys is not None:
            self._tied_weights_keys = [f"language_model.{k}" for k in self.language_model._tied_weights_keys]

        self.post_init()

    @add_start_docstrings_to_model_forward(COLPALI_FOR_RETRIEVAL_INPUT_DOCSTRING)
    @replace_return_docstrings(output_type=ColPaliForRetrievalOutput, config_class="ColPaliConfig")
    def forward(
        self,
        input_ids: torch.LongTensor = None,
        pixel_values: torch.FloatTensor = None,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.LongTensor] = None,
        past_key_values: Optional[Union[List[torch.FloatTensor], Cache]] = None,
        token_type_ids: Optional[torch.LongTensor] = None,
        cache_position: Optional[torch.LongTensor] = None,
        inputs_embeds: Optional[torch.FloatTensor] = None,
        labels: Optional[torch.LongTensor] = None,
        use_cache: Optional[bool] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        num_logits_to_keep: int = 0,
    ) -> Union[Tuple, ColPaliForRetrievalOutput]:
        if (input_ids is None) ^ (inputs_embeds is not None):
            raise ValueError("You must specify exactly one of input_ids or inputs_embeds")

        if pixel_values is not None and inputs_embeds is not None:
            raise ValueError(
                "You cannot specify both pixel_values and inputs_embeds at the same time, and must specify either one"
            )

        output_attentions = output_attentions if output_attentions is not None else self.config.output_attentions
        output_hidden_states = (
            output_hidden_states if output_hidden_states is not None else self.config.output_hidden_states
        )
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        is_training = token_type_ids is not None and labels is not None

        if inputs_embeds is None:
            inputs_embeds = self.get_input_embeddings()(input_ids)

        if cache_position is None:
            past_seen_tokens = past_key_values.get_seq_length() if past_key_values is not None else 0
            cache_position = torch.arange(
                past_seen_tokens, past_seen_tokens + inputs_embeds.shape[1], device=inputs_embeds.device
            )

        if position_ids is None:
            position_ids = cache_position.unsqueeze(0) + 1  # Paligemma positions are 1-indexed

        # Merge text and images
        if pixel_values is not None:
            image_outputs = self.vision_tower(pixel_values.to(inputs_embeds.dtype))
            selected_image_feature = image_outputs.last_hidden_state
            image_features = self.multi_modal_projector(selected_image_feature)
            image_features = image_features / (self.config.hidden_size**0.5)

            special_image_mask = (input_ids == self.config.image_token_index).unsqueeze(-1)
            special_image_mask = special_image_mask.expand_as(inputs_embeds).to(inputs_embeds.device)
            if inputs_embeds[special_image_mask].numel() != image_features.numel():
                image_tokens_in_text = torch.sum(input_ids == self.config.image_token_index)
                raise ValueError(
                    f"Number of images does not match number of special image tokens in the input text. "
                    f"Got {image_tokens_in_text} image tokens in the text but {image_features.shape[0] * image_features.shape[1]} "
                    "tokens from image embeddings."
                )
            image_features = image_features.to(inputs_embeds.device, inputs_embeds.dtype)
            inputs_embeds = inputs_embeds.masked_scatter(special_image_mask, image_features)

        # Mask out pad-token-ids in labels for BC
        if labels is not None and self.pad_token_id in labels:
            logger.warning_once(
                "`labels` contains `pad_token_id` which will be masked with `config.ignore_index`. ",
                "You have to mask out `pad_token_id` when preparing `labels`, this behavior will be removed in v.4.46.",
            )
            labels = torch.where(input_ids == self.pad_token_id, self.config.ignore_index, labels)

        causal_mask = self._update_causal_mask(
            attention_mask, token_type_ids, inputs_embeds, past_key_values, cache_position, is_training
        )

        outputs = self.language_model(
            attention_mask=causal_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            use_cache=use_cache,
            output_attentions=output_attentions,
            output_hidden_states=True,
            return_dict=return_dict,
            cache_position=cache_position,
            num_logits_to_keep=num_logits_to_keep,
        )

        last_hidden_states = outputs.hidden_states[-1]  # (batch_size, sequence_length, hidden_size)
        proj = self.custom_text_proj(last_hidden_states)  # (batch_size, sequence_length, dim)

        # L2 normalization
        embeddings = proj / proj.norm(dim=-1, keepdim=True)  # (batch_size, sequence_length, dim)

        embeddings = embeddings * attention_mask.unsqueeze(-1)  # (batch_size, sequence_length, dim)

        loss = None
        if not return_dict:
            output = (embeddings,) + outputs[2:]
            output[2] = output[2] if output_hidden_states is not None else None
            output[-1] = (image_features if pixel_values is not None else None,)
            return (loss,) + output if loss is not None else output

        return ColPaliForRetrievalOutput(
            loss=loss,
            embeddings=embeddings,
            past_key_values=outputs.past_key_values,
            hidden_states=outputs.hidden_states if output_hidden_states else None,
            attentions=outputs.attentions,
            image_hidden_states=image_features if pixel_values is not None else None,
        )

    def resize_token_embeddings(
        self,
        new_num_tokens: Optional[int] = None,
        pad_to_multiple_of: Optional[int] = None,
        mean_resizing: bool = True,
    ) -> nn.Embedding:
        model_embeds = self.language_model.resize_token_embeddings(
            new_num_tokens=new_num_tokens,
            pad_to_multiple_of=pad_to_multiple_of,
            mean_resizing=mean_resizing,
        )

        self.config.text_config.vocab_size = model_embeds.num_embeddings
        self.config.vocab_size = model_embeds.num_embeddings
        self.vocab_size = model_embeds.num_embeddings

        return model_embeds
