"""Versioned JSON representation of image-processing values; never uses pickle."""
import base64
import io
import zlib
from datetime import date, datetime

import numpy as np
from PIL import Image

MAX_BYTES = 64 * 1024 * 1024
DTYPES = {'bool', 'uint8', 'int8', 'int64', 'float32', 'float64'}

def encode(value):
    if isinstance(value, Image.Image):
        buffer = io.BytesIO()
        value.save(buffer, format='PNG')
        return {'type': 'image', 'png': base64.b64encode(buffer.getvalue()).decode()}
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        return {'type': 'array', 'dtype': str(array.dtype), 'shape': list(array.shape),
                'data': base64.b64encode(zlib.compress(array.tobytes())).decode()}
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, (date, datetime)): return {'type': 'date', 'value': value.isoformat()}
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            return {'type': 'mapping', 'items': [[encode(key), encode(item)] for key, item in value.items()]}
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [encode(item) for item in value]
    return value

def decode(value):
    if isinstance(value, list): return [decode(item) for item in value]
    if not isinstance(value, dict): return value
    kind = value.get('type')
    if kind == 'mapping': return {decode(key): decode(item) for key, item in value['items']}
    if kind == 'date':
        return datetime.fromisoformat(value['value']) if 'T' in value['value'] else date.fromisoformat(value['value'])
    if kind == 'image':
        content = base64.b64decode(value['png'], validate=True)
        if len(content) > MAX_BYTES: raise ValueError('Imagem excede o limite de processamento.')
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > MAX_BYTES // 4: raise ValueError('Imagem muito grande.')
            return image.convert('RGB').copy()
    if kind == 'array':
        if value['dtype'] not in DTYPES: raise ValueError('Tipo de matriz não permitido.')
        shape = value['shape']
        if not 1 <= len(shape) <= 3 or any(not isinstance(n, int) or n < 1 for n in shape):
            raise ValueError('Dimensões inválidas.')
        expected = int(np.prod(shape, dtype=object)) * np.dtype(value['dtype']).itemsize
        if expected > MAX_BYTES: raise ValueError('Matriz muito grande.')
        compressed = base64.b64decode(value['data'], validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, expected + 1)
        if len(raw) != expected or not inflater.eof: raise ValueError('Matriz inválida.')
        return np.frombuffer(raw, dtype=value['dtype']).reshape(shape).copy()
    return {key: decode(item) for key, item in value.items()}
