import pathlib
import tempfile
import unittest
from replay_render import plan, output_path


class RenderPlanTest(unittest.TestCase):
    def test_block_spans_sources_without_changing_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'run').mkdir()
            catalog = []
            for i in range(5):
                name = f'part-1-20261107-140{i}00.mp4'
                (root/'run'/name).write_bytes(b'video')
                catalog.append({'session':'run','file':name,'duration':300,'bytes':5})
            first = plan(root,catalog,'run',32,0)
            second = plan(root,catalog,'run',32,1)
            self.assertEqual(first['duration'],384)
            self.assertEqual(len(first['clips']),2)
            self.assertEqual(second['start'],384)
            self.assertEqual(second['offset'],84)
            self.assertEqual(second['duration'],384)
            self.assertNotEqual(first['key'],second['key'])
            self.assertEqual(first['key'],plan(root,catalog,'run',32,0)['key'])
            final = plan(root,catalog,'run',32,3)
            self.assertEqual(final['duration'],348)
            for factor,block in [(7,0),(32,-1),(32,100)]:
                with self.assertRaises(ValueError):plan(root,catalog,'run',factor,block)
            with self.assertRaises(ValueError):output_path(root,'../run')


if __name__=='__main__':unittest.main()
