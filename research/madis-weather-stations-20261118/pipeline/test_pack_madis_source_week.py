import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pack_madis_source_week as pack


def mapping(provider):
    return {'provider': provider, 'key': f'noaa-madis:{provider}:TEST'}


class PackTests(unittest.TestCase):
    def test_exclude_mixed_restricted_and_unknown(self):
        source = {
            'stations': list(map(mapping, ('MIX', 'OPEN', 'CLOSED', 'UNKNOWN'))),
            'snapshots': {'air_temp': [[index, 'utc', 3, 'C'] for index in range(4)]},
            'source_hours': 168,
        }
        policy = {
            'MIX': {'weather': '3', 'subproviders': {'PUBLIC': '3', 'RESTRICTED': '4'}},
            'OPEN': {'weather': '3', 'subproviders': {}},
            'CLOSED': {'weather': '4', 'subproviders': {}},
        }
        public, retained, excluded = pack.eligible_map(source, policy)
        self.assertEqual(public['stations'], [mapping('OPEN')])
        self.assertEqual(public['snapshots'], {'air_temp': [[0, 'utc', 3, 'C']]})
        self.assertEqual(retained, {1: 0})
        self.assertEqual(excluded, {'MIX': 1, 'CLOSED': 1, 'UNKNOWN': 1})
        source['stations'][1]['provider'] = 'CLOSED'
        with self.assertRaisesRegex(ValueError, 'identity'):
            pack.eligible_map(source, policy)

    def test_check_every_packed_member(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            station_path = root / 'data/history'
            station_path.mkdir(parents=True)
            output = root / 'packed'
            output.mkdir()
            stations = list(map(mapping, ('OPEN', 'ALSO_OPEN')))
            for i, station in enumerate(stations):
                data = {
                    'schema': pack.HISTORY_SCHEMA,
                    'key': station['key'],
                    'rows': [[None, None]],
                }
                (station_path / f'{i}.json.gz').write_bytes(
                    gzip.compress(pack.compact(data), mtime=0)
                )
            part_limit = max(p.stat().st_size for p in station_path.iterdir())
            with (
                patch.object(pack, 'MAX_PART', part_limit),
                patch.object(pack, 'MIN_FREE', 0),
            ):
                index, shards = pack.pack_history(
                    root, output, {'stations': stations}, {0: 0, 1: 1}
                )
            self.assertEqual([row[:2] for row in index], [[0, 0], [1, 0]])
            pack.verify_ranges(
                root, {'stations': stations}, {0: 0, 1: 1}, index, shards
            )
            shards[1].write_bytes(shards[0].read_bytes())
            with self.assertRaisesRegex(ValueError, 'packed byte range differs'):
                pack.verify_ranges(
                    root, {'stations': stations}, {0: 0, 1: 1}, index, shards
                )


if __name__ == '__main__':
    unittest.main()
