"""Publish the bundled image, checking both source and destination bytes."""

import hashlib
import os
from pathlib import Path
import struct


EXPECTED_SHA256 = 'd02bfecc8f87d3b95e343d78fa04dc28ca08e9f26e9ae2168b3d6ad7d80347fb'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_BYTES = 1048576


def verify(payload):
    """Reject a damaged or accidentally replaced bundled artwork."""
    if not payload.startswith(PNG_SIGNATURE) or len(payload) < 24:
        raise ValueError('The bundled artwork is not a complete PNG header.')
    if struct.unpack('>II', payload[16:24]) != (1024, 1024):
        raise ValueError('The artwork must be exactly 1024 by 1024 pixels.')
    if len(payload) > MAX_BYTES:
        raise ValueError('The artwork exceeds the one MiB limit.')
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f'Artwork integrity check failed: {digest}')
    return digest


def main():
    source = Path(__file__).resolve().with_name('entry.png')
    payload = source.read_bytes()
    digest = verify(payload)

    output_dir = Path(os.environ.get('MAKEFUN_OUTPUT_DIR', '/output'))
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / 'entry.png'
    temporary = output_dir / '.entry.png.tmp'
    try:
        temporary.write_bytes(payload)
        if temporary.read_bytes() != payload:
            raise OSError('Temporary output differs from the bundled artwork.')
        temporary.replace(target)
        written = target.read_bytes()
        if written != payload or verify(written) != digest:
            raise OSError('Published output failed byte integrity verification.')
    finally:
        if temporary.exists():
            temporary.unlink()

    print(f'Wrote {target}: {len(payload)} bytes; SHA-256 {digest}')


if __name__ == '__main__':
    main()
