from typing import List
import torch


class BaseEncoder:
    """
    Base class for all encoders.
    
    An encoder should return encoded representations of any columnar data.
    The procedure for this is defined inside the `encode()` method.
    
    If this encoder is expected to handle an output column, then it also needs to implement the respective `decode()` method that handles the inverse transformation from encoded representations to the final prediction in the original column space.
    
    For encoders that learn representations (as opposed to rule-based), the `prepare()` method will handle all learning logic.
    
    The `to()` method is used to move PyTorch-based encoders to and from a GPU.
    
    :param  is_target: Whether the data to encode is the target, as per the problem definition.
    :param is_timeseries_encoder: Whether encoder represents sequential/time-series data. Lightwood must provide specific treatment for this kind of encoder
    :param is_trainable_encoder: Whether the encoder must return learned representations. Lightwood checks whether this flag is present in order to pass data to the feature representation via the ``prepare`` statement. 
    
    Class Attributes:
    - _prepared: Internal flag to signal that the `prepare()` method has been successfully executed.
    - is_nn_encoder: Whether the encoder is neural network-based.
    - dependencies: list of additional columns that the encoder might need to encode.
    - output_size: length of each encoding tensor for a single data point.
    
    """ # noqa
    is_target: bool
    prepared: bool

    is_timeseries_encoder: bool = False
    is_trainable_encoder: bool = False

    def __init__(self, is_target=False) -> None:
        self.is_target = is_target
        self._prepared = False
        self.uses_subsets = False
        self.dependencies = []
        self.output_size = None

    # Not all encoders need to be prepared
    def prepare(self, priming_data) -> None:
        self._prepared = True

    def encode(self, column_data) -> torch.Tensor:
        raise NotImplementedError

    def decode(self, encoded_data) -> List[object]:
        raise NotImplementedError

    # Should work for all torch-based encoders, but custom behavior may have to be implemented for weird models
    def to(self, device, available_devices):
        # Find all nn.Module type objects and convert them
        # @TODO: Make this work recursively
        for v in vars(self):
            attr = getattr(self, v)
            if isinstance(attr, torch.nn.Module):
                attr.to(device)
        return self
