from typing import List, Tuple, Union, Optional

import torch
from torch import nn, Tensor

from transformers import PreTrainedModel
from transformers.modeling_outputs import ImagePointDescriptionOutput, BaseModelOutputWithNoAttention
from transformers.models.superpoint.configuration_superpoint import SuperPointConfig


class SuperPointEncoder(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.conv_layers_sizes = config.conv_layers_sizes
        self.descriptor_dim = config.descriptor_dim

        self.relu = nn.ReLU(inplace=True)
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)

        self.conv1a = nn.Conv2d(1, self.conv_layers_sizes[0], kernel_size=3, stride=1, padding=1)
        self.conv1b = nn.Conv2d(
            self.conv_layers_sizes[0], self.conv_layers_sizes[0], kernel_size=3, stride=1, padding=1
        )
        self.conv2a = nn.Conv2d(
            self.conv_layers_sizes[0], self.conv_layers_sizes[1], kernel_size=3, stride=1, padding=1
        )
        self.conv2b = nn.Conv2d(
            self.conv_layers_sizes[1], self.conv_layers_sizes[1], kernel_size=3, stride=1, padding=1
        )
        self.conv3a = nn.Conv2d(
            self.conv_layers_sizes[1], self.conv_layers_sizes[2], kernel_size=3, stride=1, padding=1
        )
        self.conv3b = nn.Conv2d(
            self.conv_layers_sizes[2], self.conv_layers_sizes[2], kernel_size=3, stride=1, padding=1
        )
        self.conv4a = nn.Conv2d(
            self.conv_layers_sizes[2], self.conv_layers_sizes[3], kernel_size=3, stride=1, padding=1
        )
        self.conv4b = nn.Conv2d(
            self.conv_layers_sizes[3], self.conv_layers_sizes[3], kernel_size=3, stride=1, padding=1
        )

    def forward(
        self,
        input,
        output_hidden_states: Optional[bool] = False,
        return_dict: Optional[bool] = True,
    ):
        all_hidden_states = () if output_hidden_states else None
        # TODO refactor the code to make it cleaner

        """ Run the CNN to encode the image. """
        input = self.relu(self.conv1a(input))
        input = self.relu(self.conv1b(input))
        input = self.pool(input)

        if output_hidden_states:
            all_hidden_states = all_hidden_states + (input,)

        input = self.relu(self.conv2a(input))
        input = self.relu(self.conv2b(input))
        input = self.pool(input)

        if output_hidden_states:
            all_hidden_states = all_hidden_states + (input,)

        input = self.relu(self.conv3a(input))
        input = self.relu(self.conv3b(input))
        input = self.pool(input)

        if output_hidden_states:
            all_hidden_states = all_hidden_states + (input,)

        input = self.relu(self.conv4a(input))
        output = self.relu(self.conv4b(input))

        if output_hidden_states:
            all_hidden_states = all_hidden_states + (output,)

        if not return_dict:
            return tuple(v for v in [output, all_hidden_states] if v is not None)

        return BaseModelOutputWithNoAttention(
            last_hidden_state=output,
            hidden_states=all_hidden_states,
        )


class SuperPointInterestPointDecoder(nn.Module):
    def __init__(self, config: SuperPointConfig):
        super().__init__()
        self.conv_layers_sizes = config.conv_layers_sizes
        self.descriptor_dim = config.descriptor_dim
        self.keypoint_threshold = config.keypoint_threshold
        self.max_keypoints = config.max_keypoints
        self.nms_radius = config.nms_radius
        self.border_removal_distance = config.remove_borders

        self.relu = nn.ReLU(inplace=True)
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        self.convSa = nn.Conv2d(
            self.conv_layers_sizes[3], self.conv_layers_sizes[4], kernel_size=3, stride=1, padding=1
        )
        self.convSb = nn.Conv2d(self.conv_layers_sizes[4], 65, kernel_size=1, stride=1, padding=0)

    def forward(self, encoded):
        # Compute the dense keypoint scores
        scores = self.get_scores(encoded)
        # Extract keypoints
        keypoints, scores = self.extract_keypoints(scores)

        return keypoints, scores

    def get_scores(self, encoded):
        """Compute the dense keypoint scores"""
        scores = self.relu(self.convSa(encoded))
        scores = self.convSb(scores)
        scores = torch.nn.functional.softmax(scores, 1)[:, :-1]
        b, _, h, w = scores.shape
        scores = scores.permute(0, 2, 3, 1).reshape(b, h, w, 8, 8)
        scores = scores.permute(0, 1, 3, 2, 4).reshape(b, h * 8, w * 8)
        scores = self.simple_nms(scores, self.nms_radius)
        return scores

    def extract_keypoints(self, scores):
        b, h, w = scores.shape

        # Threshold keypoints by score value
        # The following lines are the original code made to handle batch sizes > 1
        # keypoints = [torch.nonzero(s > self.keypoint_threshold) for s in scores]
        # scores = [s[tuple(k.t())] for s, k in zip(scores, keypoints)]

        keypoints = torch.nonzero(scores[0] > self.keypoint_threshold)
        scores = scores[0][tuple(keypoints.t())]

        # Discard keypoints near the image borders
        keypoints, scores = self.remove_borders(keypoints, scores, self.border_removal_distance, h * 8, w * 8)

        # Keep the k keypoints with highest score
        if self.max_keypoints >= 0:
            keypoints, scores = self.top_k_keypoints(keypoints, scores, self.max_keypoints)

        # Convert (h, w) to (x, y)
        keypoints = torch.flip(keypoints, [1]).float()

        return keypoints, scores

    @staticmethod
    def simple_nms(scores, nms_radius: int):
        assert nms_radius >= 0

        def max_pool(x):
            return torch.nn.functional.max_pool2d(x, kernel_size=nms_radius * 2 + 1, stride=1, padding=nms_radius)

        zeros = torch.zeros_like(scores)
        max_mask = scores == max_pool(scores)
        for _ in range(2):
            supp_mask = max_pool(max_mask.float()) > 0
            supp_scores = torch.where(supp_mask, zeros, scores)
            new_max_mask = supp_scores == max_pool(supp_scores)
            max_mask = max_mask | (new_max_mask & (~supp_mask))
        return torch.where(max_mask, scores, zeros)

    @staticmethod
    def remove_borders(keypoints, scores, border: int, height: int, width: int):
        """Removes keypoints too close to the border"""
        mask_h = (keypoints[:, 0] >= border) & (keypoints[:, 0] < (height - border))
        mask_w = (keypoints[:, 1] >= border) & (keypoints[:, 1] < (width - border))
        mask = mask_h & mask_w
        return keypoints[mask], scores[mask]

    @staticmethod
    def top_k_keypoints(keypoints, scores, k: int):
        if k >= len(keypoints):
            return keypoints, scores
        scores, indices = torch.topk(scores, k, dim=0)
        return keypoints[indices], scores


class SuperPointDescriptorDecoder(nn.Module):
    def __init__(self, config: SuperPointConfig):
        super().__init__()
        self.conv_layers_sizes = config.conv_layers_sizes
        self.descriptor_dim = config.descriptor_dim
        self.keypoint_threshold = config.keypoint_threshold
        self.max_keypoints = config.max_keypoints
        self.nms_radius = config.nms_radius
        self.border_removal_distance = config.remove_borders

        self.relu = nn.ReLU(inplace=True)
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        self.convDa = nn.Conv2d(
            self.conv_layers_sizes[3], self.conv_layers_sizes[4], kernel_size=3, stride=1, padding=1
        )
        self.convDb = nn.Conv2d(self.conv_layers_sizes[4], self.descriptor_dim, kernel_size=1, stride=1, padding=0)

    def forward(self, encoded, keypoints):
        """Compute the dense descriptors"""
        descriptors = self.convDb(self.relu(self.convDa(encoded)))
        descriptors = torch.nn.functional.normalize(descriptors, p=2, dim=1)

        # Extract descriptors
        # The following line was the original code made to handle batch sizes > 1
        # descriptors = self.sample_descriptors(k[None], d[None], 8)[0] for k, d in zip(keypoints, descriptors)]
        descriptors = self.sample_descriptors(keypoints[None], descriptors[0][None], 8)[0]

        return descriptors

    @staticmethod
    def sample_descriptors(keypoints, descriptors, s: int = 8):
        """Interpolate descriptors at keypoint locations"""
        b, c, h, w = descriptors.shape
        keypoints = keypoints - s / 2 + 0.5
        keypoints /= torch.tensor(
            [(w * s - s / 2 - 0.5), (h * s - s / 2 - 0.5)],
        ).to(
            keypoints
        )[None]
        keypoints = keypoints * 2 - 1  # normalize to (-1, 1)
        args = {"align_corners": True} if torch.__version__ >= "1.3" else {}
        descriptors = torch.nn.functional.grid_sample(
            descriptors, keypoints.view(b, 1, -1, 2), mode="bilinear", **args
        )
        descriptors = torch.nn.functional.normalize(descriptors.reshape(b, c, -1), p=2, dim=1)
        return descriptors


# Copied from transformers.models.convnext.modeling_convnext.ConvNextPreTrainedModel with ConvNextV2->SuperPoint, convnextv2->superpoint
class SuperPointPreTrainedModel(PreTrainedModel):
    """
    An abstract class to handle weights initialization and a simple interface for downloading and loading pretrained
    models.
    """

    config_class = SuperPointConfig
    base_model_prefix = "superpoint"
    main_input_name = "pixel_values"
    supports_gradient_checkpointing = False

    def _init_weights(self, module):
        """Initialize the weights"""
        if isinstance(module, (nn.Linear, nn.Conv2d)):
            # Slightly different from the TF version which uses truncated_normal for initialization
            # cf https://github.com/pytorch/pytorch/pull/5617
            module.weight.data.normal_(mean=0.0, std=self.config.initializer_range)
            if module.bias is not None:
                module.bias.data.zero_()
        elif isinstance(module, nn.LayerNorm):
            module.bias.data.zero_()
            module.weight.data.fill_(1.0)


class SuperPointModel(SuperPointPreTrainedModel):
    def __init__(self, config: SuperPointConfig):
        super().__init__(config)

        self.config = config

        self.encoder = SuperPointEncoder(config)
        self.keypoint_decoder = SuperPointInterestPointDecoder(config)
        self.descriptor_decoder = SuperPointDescriptorDecoder(config)

        self.post_init()

    def forward(
        self,
        pixel_values: torch.FloatTensor = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple, ImagePointDescriptionOutput]:
        output_hidden_states = (
            output_hidden_states if output_hidden_states is not None else self.config.output_hidden_states
        )
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        if pixel_values is None:
            raise ValueError("You have to specify pixel_values")

        encoder_outputs = self.encoder(
            pixel_values,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        last_hidden_state = encoder_outputs[0]

        keypoints, scores = self.keypoint_decoder(last_hidden_state)

        descriptors = self.descriptor_decoder(last_hidden_state, keypoints)

        if not return_dict:
            return (keypoints, scores, descriptors) + encoder_outputs[1:]

        return ImagePointDescriptionOutput(
            keypoints=keypoints,
            scores=scores,
            descriptors=descriptors,
            last_hidden_state=last_hidden_state,
            hidden_states=encoder_outputs.hidden_states,
        )


class SuperPointModelForInterestPointDescription(SuperPointPreTrainedModel):
    def __init__(self, config: SuperPointConfig):
        super().__init__(config)

        self.config = config

        self.superpoint = SuperPointModel(config)

        self.post_init()

    def forward(
        self,
        pixel_values: torch.FloatTensor = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple, ImagePointDescriptionOutput]:
        output_hidden_states = (
            output_hidden_states if output_hidden_states is not None else self.config.output_hidden_states
        )
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        if pixel_values is None:
            raise ValueError("You have to specify pixel_values")

        outputs = self.superpoint(pixel_values, output_hidden_states=output_hidden_states, return_dict=return_dict)

        if not return_dict:
            return (outputs.keypoints, outputs.scores, outputs.descriptors) + outputs.hidden_states

        return ImagePointDescriptionOutput(
            keypoints=outputs.keypoints,
            scores=outputs.scores,
            descriptors=outputs.descriptors,
            last_hidden_state=outputs.last_hidden_state,
            hidden_states=outputs.hidden_states,
        )
