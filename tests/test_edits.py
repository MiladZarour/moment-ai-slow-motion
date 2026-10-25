import math
import unittest
from server import sections


class EditTests(unittest.TestCase):
    def test_timing_and_overlap(self):
        result = sections([{'start': .5, 'end': 1.5, 'speed': .25},
                           {'start': 1, 'end': 2, 'speed': .5}], 3)
        self.assertEqual(result, [(0, .5, 1), (.5, 1, .25), (1, 2, .5), (2, 3, 1)])
        self.assertEqual(sum((e - s) / rate for s, e, rate in result), 5.5)

    def test_adjacent_holds_leave_no_subframe_gap(self):
        result = sections([{'start': 0, 'end': .303, 'speed': .25},
                           {'start': .305, 'end': .7, 'speed': .5}], 3)
        self.assertEqual(result[:2], [(0, .3, .25), (.3, .7, .5)])
        self.assertTrue(all(e - s >= 1 / 30 - 1e-8 for s, e, _ in result))

    def test_invalid_speed_and_nonfinite_times(self):
        for hold in ({'start': 0, 'end': 1, 'speed': .1},
                     {'start': math.nan, 'end': 1, 'speed': .25}):
            with self.assertRaises(ValueError):
                sections([hold], 3)

    def test_native_29fps_section_grid(self):
        result = sections([{'start': 15/29, 'end': 45/29, 'speed': .25}], 3, '29')
        self.assertAlmostEqual(result[1][0], 15/29)
        self.assertAlmostEqual(result[1][1], 45/29)

    def test_native_fractional_frame_rate(self):
        import pipeline
        job = {}
        pipeline.ensure_timing(job, {'streams': [{'codec_type': 'video', 'avg_frame_rate': '24000/1001'}], 'format': {}})
        self.assertEqual(job['sourceFps'], '24000/1001')
        self.assertEqual(job['outputFps'], '96000/1001')
        self.assertAlmostEqual(job['chunkSeconds'], 15*1001/24000)


if __name__ == '__main__':
    unittest.main()
