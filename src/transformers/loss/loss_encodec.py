import torch
import torch.nn.functional as F


def EncodecLoss(model, input_values, audio_values):
    """
    Computes the reconstruction and commitment losses for the EncodecModel.

    Args:
        model (`EncodecModel`):
            The Encodec model instance.
        input_values (`torch.Tensor` of shape `(batch_size, sequence_length)`):
            Original input audio values.
        audio_values (`torch.Tensor` of shape `(batch_size, sequence_length)`):
            Reconstructed audio values from the model.

    Returns:
        `tuple[torch.Tensor, torch.Tensor]`: A tuple containing:
            - reconstruction_loss (`torch.Tensor`): Combined time and frequency domain reconstruction loss
            - commitment_loss (`torch.Tensor`): VQ commitment loss
    """

    # Compute commitment loss
    embeddings = model.encoder(input_values)
    _, quantization_steps = model.quantizer.encode(embeddings, bandwidth=None)

    commitment_loss = torch.tensor(0.0, device=input_values.device)
    for residual, quantize in quantization_steps:
        loss = F.mse_loss(quantize.permute(0, 2, 1), residual.permute(0, 2, 1))
        commitment_loss += loss
    commitment_loss *= model.commitment_weight

    # Compute reconstruction loss
    # Time domain loss
    time_loss = F.l1_loss(audio_values, input_values)

    # Frequency domain loss
    scales = [2**i for i in range(5, 12)]
    frequency_loss = 0.0
    for scale in scales:
        n_fft = scale
        hop_length = scale // 4
        S_x = model.compute_mel_spectrogram(input_values, n_fft, hop_length, n_mels=64)
        S_x_hat = model.compute_mel_spectrogram(audio_values, n_fft, hop_length, n_mels=64)
        l1 = F.l1_loss(S_x_hat, S_x)
        l2 = F.mse_loss(S_x_hat, S_x)
        frequency_loss += l1 + l2

    frequency_loss = frequency_loss / (len(scales) * 2)

    # Combine losses
    lambda_t = 1.0  # Hardcoding these to match the weights detailed in paper
    lambda_f = 1.0
    reconstruction_loss = lambda_t * time_loss + lambda_f * frequency_loss

    return reconstruction_loss, commitment_loss
