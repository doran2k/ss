# coding=utf-8
# Copyright 2023 The HuggingFace Inc. team.
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
"""Convert GCViT checkpoints from the timm library."""

import argparse
import json
from pathlib import Path

import requests
import timm
import torch
from huggingface_hub import hf_hub_download
from PIL import Image

from transformers import AutoFeatureExtractor, GCViTConfig, GCViTForImageClassification


def get_gcvit_config(gcvit_name):
    config = GCViTConfig()
    name_split = gcvit_name.split("_")
    model_size = name_split[1]
    img_size = int(name_split[3][-3:])
    
    print(model_size)
    if model_size == "xxtiny":
        depths = (2, 2, 6, 2)
        num_heads = (2, 4, 8, 16)
    elif model_size == "xtiny":
        depths = (3, 4, 6, 5)
        num_heads = (2, 4, 8, 16)
    elif model_size == "tiny":
        depths = (3, 4, 19, 5)
        num_heads = (2, 4, 8, 16)
    elif model_size == "small":
        embed_dim = 96
        depths = (3, 4, 19, 5)
        num_heads = (3, 6, 12, 24)
        mlp_ratio = 2
        layer_scale = 1e-5
    else:
        embed_dim = 128
        depths = (3, 4, 19, 5)
        num_heads = (4, 8, 16, 32)
        mlp_ratio = 2
        layer_scale = 1e-5

    if ("22k" in gcvit_name) and ("to" not in gcvit_name):
        num_classes = 21841
        repo_id = "huggingface/label-files"
        filename = "imagenet-22k-id2label.json"
        id2label = json.load(open(hf_hub_download(repo_id, filename, repo_type="dataset"), "r"))
        id2label = {int(k): v for k, v in id2label.items()}
        config.id2label = id2label
        config.label2id = {v: k for k, v in id2label.items()}

    else:
        num_classes = 1000
        repo_id = "huggingface/label-files"
        filename = "imagenet-1k-id2label.json"
        id2label = json.load(open(hf_hub_download(repo_id, filename, repo_type="dataset"), "r"))
        id2label = {int(k): v for k, v in id2label.items()}
        config.id2label = id2label
        config.label2id = {v: k for k, v in id2label.items()}

    config.image_size = img_size
    config.num_labels = num_classes
    config.embed_dim = embed_dim
    config.depths = depths
    config.num_heads = num_heads
    config.mlp_ratio = mlp_ratio
    config.layer_scale = layer_scale

    return config


def rename_key(name):
    if "patch_embed.proj" in name:
        name = name.replace("patch_embed.proj", "embeddings.patch_embeddings.projection")
    if "patch_embed.norm" in name:
        name = name.replace("patch_embed.norm", "embeddings.norm")
    if "layers" in name:
        name = "encoder." + name
    if "attn.proj" in name:
        name = name.replace("attn.proj", "attention.output.dense")
    if "attn" in name:
        name = name.replace("attn", "attention.self")
    if "norm1" in name:
        name = name.replace("norm1", "layernorm_before")
    if "norm2" in name:
        name = name.replace("norm2", "layernorm_after")
    if "mlp.fc1" in name:
        name = name.replace("mlp.fc1", "intermediate.dense")
    if "mlp.fc2" in name:
        name = name.replace("mlp.fc2", "output.dense")
    if "q_bias" in name:
        name = name.replace("q_bias", "query.bias")
    if "k_bias" in name:
        name = name.replace("k_bias", "key.bias")
    if "v_bias" in name:
        name = name.replace("v_bias", "value.bias")
    if "cpb_mlp" in name:
        name = name.replace("cpb_mlp", "continuous_position_bias_mlp")
    if name == "norm.weight":
        name = "layernorm.weight"
    if name == "norm.bias":
        name = "layernorm.bias"

    if "head" in name:
        name = name.replace("head", "classifier")
    else:
        name = "gcvit." + name

    return name


def convert_state_dict(orig_state_dict, model):
    for key in orig_state_dict.copy().keys():
        val = orig_state_dict.pop(key)

        if "mask" in key:
            continue
        elif "qkv" in key:
            key_split = key.split(".")
            layer_num = int(key_split[1])
            block_num = int(key_split[3])
            dim = model.gcvit.encoder.layers[layer_num].blocks[block_num].attention.self.all_head_size

            if "weight" in key:
                orig_state_dict[
                    f"gcvit.encoder.layers.{layer_num}.blocks.{block_num}.attention.self.query.weight"
                ] = val[:dim, :]
                orig_state_dict[
                    f"gcvit.encoder.layers.{layer_num}.blocks.{block_num}.attention.self.key.weight"
                ] = val[dim : dim * 2, :]
                orig_state_dict[
                    f"gcvit.encoder.layers.{layer_num}.blocks.{block_num}.attention.self.value.weight"
                ] = val[-dim:, :]
            else:
                orig_state_dict[
                    f"gcvit.encoder.layers.{layer_num}.blocks.{block_num}.attention.self.query.bias"
                ] = val[:dim]
                orig_state_dict[f"gcvit.encoder.layers.{layer_num}.blocks.{block_num}.attention.self.key.bias"] = val[
                    dim : dim * 2
                ]
                orig_state_dict[
                    f"gcvit.encoder.layers.{layer_num}.blocks.{block_num}.attention.self.value.bias"
                ] = val[-dim:]
        else:
            orig_state_dict[rename_key(key)] = val

    return orig_state_dict


def convert_gcvit_checkpoint(gcvit_name, pytorch_dump_folder_path):
    timm_model = timm.create_model(gcvit_name, pretrained=True)
    timm_model.eval()

    config = get_gcvit_config(gcvit_name)
    print(config)
    model = GCViTForImageClassification(config)
    model.eval()


    new_state_dict = convert_state_dict(timm_model.state_dict(), model)
    model.load_state_dict(new_state_dict)

    url = "http://images.cocodataset.org/val2017/000000039769.jpg"

    feature_extractor = AutoFeatureExtractor.from_pretrained("microsoft/{}".format(gcvit_name.replace("_", "-")))
    image = Image.open(requests.get(url, stream=True).raw)
    inputs = feature_extractor(images=image, return_tensors="pt")

    timm_outs = timm_model(inputs["pixel_values"])
    hf_outs = model(**inputs).logits

    assert torch.allclose(timm_outs, hf_outs, atol=1e-3)

    print(f"Saving model {gcvit_name} to {pytorch_dump_folder_path}")
    model.save_pretrained(pytorch_dump_folder_path)

    print(f"Saving feature extractor to {pytorch_dump_folder_path}")
    feature_extractor.save_pretrained(pytorch_dump_folder_path)

    model.push_to_hub(
        repo_path_or_name=Path(pytorch_dump_folder_path, gcvit_name),
        organization="jorgeav",
        commit_message="Add model",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Required parameters
    parser.add_argument(
        "--gcvit_name",
        default="gcvit_xtiny",
        type=str,
        help="Name of the GCViT timm model you'd like to convert.",
    )
    parser.add_argument(
        "--pytorch_dump_folder_path", default=None, type=str, help="Path to the output PyTorch model directory."
    )

    args = parser.parse_args()
    convert_gcvit_checkpoint(args.gcvit_name, args.pytorch_dump_folder_path)
