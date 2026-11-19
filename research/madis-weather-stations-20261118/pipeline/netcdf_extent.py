"""Validate the declared byte extent of a classic MADIS NetCDF file."""

MAX_INFLATED_BYTES = 600_000_000


def validate_extent(path):
    """Check declared classic/CDF-2 byte extents before a permissive reader opens it.

    Layout follows Unidata's classic-format specification. This bounded product
    does not support streaming record counts or >4 GiB variables. Both would
    require a different acquisition contract. No field values are interpreted.
    """
    import math
    import struct

    total = path.stat().st_size
    widths = {1: 1, 2: 1, 3: 2, 4: 4, 5: 4, 6: 8}
    with path.open('rb') as source:

        def take(size):
            if size < 0 or source.tell() + size > total:
                raise ValueError('Truncated NetCDF header')
            value = source.read(size)
            if len(value) != size:
                raise ValueError('Truncated NetCDF header')
            return value

        def integer():
            return struct.unpack('>I', take(4))[0]

        def skip(size):
            if size < 0 or source.tell() + size > total:
                raise ValueError('Truncated NetCDF header value')
            source.seek(size, 1)

        def name():
            size = integer()
            skip((size + 3) // 4 * 4)

        def count(expected):
            tag, amount = integer(), integer()
            if (tag, amount) == (0, 0):
                return 0
            if tag != expected or amount > 100_000:
                raise ValueError('Unsupported NetCDF header list')
            return amount

        def attributes():
            for _ in range(count(12)):
                name()
                datatype, size = integer(), integer()
                if datatype not in widths:
                    raise ValueError('Unsupported classic type')
                skip((size * widths[datatype] + 3) // 4 * 4)

        magic = take(4)
        if magic not in (b'CDF\x01', b'CDF\x02'):
            raise ValueError('Expected classic or CDF-2 NetCDF')
        records = integer()
        if records == 0xFFFFFFFF:
            raise ValueError('Streaming record count is not supported')
        dimensions = []
        for _ in range(count(10)):
            name()
            dimensions.append(integer())
        if dimensions.count(0) > 1:
            raise ValueError('More than one unlimited dimension')
        attributes()
        variables = []
        for _ in range(count(11)):
            name()
            rank = integer()
            if rank > 1024:
                raise ValueError('Unsupported NetCDF rank')
            ids = [integer() for _ in range(rank)]
            if any(i >= len(dimensions) for i in ids):
                raise ValueError('Invalid NetCDF dimension ID')
            shape = [dimensions[i] for i in ids]
            if 0 in shape[1:]:
                raise ValueError('Unlimited dimension is not first')
            attributes()
            datatype, declared = integer(), integer()
            begin = struct.unpack(
                '>Q' if magic == b'CDF\x02' else '>I',
                take(8 if magic == b'CDF\x02' else 4),
            )[0]
            if datatype not in widths:
                raise ValueError('Unsupported classic type')
            is_record = bool(shape and shape[0] == 0)
            actual = math.prod(shape[1:] if is_record else shape) * widths[datatype]
            padded = (actual + 3) // 4 * 4
            if padded != declared or padded > MAX_INFLATED_BYTES:
                raise ValueError('Invalid or unsupported NetCDF variable extent')
            variables.append((begin, actual, padded, is_record))
        header_end = source.tell()
    fixed = [v for v in variables if not v[3]]
    record = [v for v in variables if v[3]]
    required = max([header_end] + [begin + padded for begin, _, padded, _ in fixed])
    for begin, _, _, is_record in variables:
        if (not is_record or records) and begin < header_end:
            raise ValueError('NetCDF data overlaps header')
    if record and records:
        stride = record[0][1] if len(record) == 1 else sum(v[2] for v in record)
        first = min(v[0] for v in record)
        for begin, actual, _, _ in record:
            if begin + actual > first + stride:
                raise ValueError('NetCDF record variable exceeds declared stride')
        required = max(required, first + records * stride)
    if total < required:
        raise ValueError('Truncated NetCDF data section')
    return required
