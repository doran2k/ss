import torch

from ..modeling_flash_attention_utils import _flash_attention_forward


def flash_attention_forward(
    config, query, key, value, attention_mask, target_dtype=torch.float16, training=False, layer_idx=0, **kwargs
):
    if attention_mask is not None:
        seq_len = attention_mask.shape[1]
        query = query[:, :, :seq_len]
        value = value[:, :, :seq_len]
    else:
        seq_len = query.shape[1]

    # Re-transpose them
    query = query.transpose(1, 2)
    key = key.transpose(1, 2)
    value = value.transpose(1, 2)

    dropout_rate = config.attention_dropout if training else 0.0

    input_dtype = query.dtype
    if input_dtype == torch.float32:
        query = query.to(target_dtype)
        key = key.to(target_dtype)
        value = value.to(target_dtype)

    attn_output = _flash_attention_forward(
        query,
        key,
        value,
        attention_mask,
        seq_len,
        config=config,
        dropout=dropout_rate,
        layer_idx=layer_idx,
        **kwargs,
    )

    return attn_output, None
