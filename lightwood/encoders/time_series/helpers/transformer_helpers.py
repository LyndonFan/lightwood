import math
import torch
import torch.nn as nn


def len_to_mask(lengths, zeros):
    """
    :param lengths: list of ints with the lengths of the sequences
    :param zeros: bool. If false, the first lengths[i] values will be True and the rest will be false.
            If true, the first values will be False and the rest True
    :return: Boolean tensor of dimension (L, T) with L = len(lenghts) and T = lengths.max(), where with rows with lengths[i] True values followed by lengths.max()-lengths[i] False values. The True and False values are inverted if `zeros == True`
    """
    # Clean trick from:
    # https://stackoverflow.com/questions/53403306/how-to-batch-convert-sentence-lengths-to-masks-in-pytorch
    mask = torch.arange(lengths.max(), device=lengths.device)[None, :] < lengths[:, None]
    if zeros:
        mask = ~mask  # Logical not
    return mask.transpose(0, 1)


def get_chunk(source, source_lengths, start, step):
    """Source is 3D tensor, shaped (batch_size, timesteps, n_dimensions)"""
    # Compute the lengths of the sequences
    # The -1 comes from the fact that the last element is used as target but not as data!
    lengths = torch.clamp((source_lengths - 1) - start, min=0, max=step)

    # This is necessary for MultiHeadedAttention to work
    end = source.shape[1]  # min(start + step, source.shape[1]) ?
    data = source[:, :end-1, :]
    target = source[:, 1:, :]

    return data, target, lengths


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.2, max_len=5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        if not d_model % 2:
            pe[:, 1::2] = torch.cos(position * div_term)
        else:
            pe[:, 1::2] = torch.cos(position * div_term)[:, :d_model//2]
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer("pe", pe)

    def forward(self, x):
        x = x + self.pe[: x.size(0), :]
        return self.dropout(x)


class TransformerEncoder(nn.Module):
    def __init__(self, ninp, nhead, nhid, nlayers, dropout=0.2):
        super(TransformerEncoder, self).__init__()
        self.src_mask = None
        self.pos_encoder = PositionalEncoding(ninp, dropout)
        encoder_layers = nn.TransformerEncoderLayer(ninp, nhead, nhid, dropout)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layers, nlayers)
        self.init_weights()

    def _generate_square_subsequent_mask(self, sz):
        mask = (torch.triu(torch.ones(sz, sz)) == 1).transpose(0, 1)
        # Take the logarithm
        mask = (
            mask.float()
            .masked_fill(mask == 0, float("-inf"))
            .masked_fill(mask == 1, float(0.0))
        )
        return mask

    def init_weights(self):
        for p in self.parameters():
            if p.dim() > 1:
                torch.nn.init.xavier_uniform_(p)

    def forward(self, src, lengths, device):
        if self.src_mask is None or self.src_mask.size(0) != src.size(0):
            # Attention mask to avoid attending to upcoming parts of the sequence
            self.src_mask = self._generate_square_subsequent_mask(src.size(0)).to(
                device
            )
        src = self.pos_encoder(src)
        # The lengths_mask has to be of size [batch, lengths]
        lengths_mask = len_to_mask(lengths, zeros=True).to(device)
        output = self.transformer_encoder(
            src, mask=self.src_mask, src_key_padding_mask=lengths_mask
        )
        return output

    def bptt(self, batch, criterion, device):
        """This method implements truncated backpropagation through time
        Returns: output tensor, None as hidden_state, which does not apply in this case, and loss value"""
        loss = 0
        train_batch, len_batch = batch
        batch_size, timesteps, _ = train_batch.shape

        for start_chunk in range(0, timesteps, timesteps):
            data, targets, lengths_chunk = get_chunk(train_batch, len_batch, start_chunk, timesteps)
            output = self.forward(data, lengths_chunk, device)
            loss += criterion(output, targets, lengths_chunk)

        return output, None, loss