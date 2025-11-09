"""Project-wide Python startup hooks to smooth over dependency issues."""
import numpy as np

# NumPy 2.x removes several scalar aliases; reintroduce them for legacy deps.
_legacy_scalars = {
    "float_": np.float64,
    "int_": np.int64,
    "bool_": np.bool_,
    "complex_": np.complex128,
}

for _name, _alias in _legacy_scalars.items():
    if not hasattr(np, _name):
        setattr(np, _name, _alias)
