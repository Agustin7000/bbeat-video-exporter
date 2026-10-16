"""Integration tests: actual FFmpeg output, channel ordering, tails and resume."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import exporter as e


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'backup'
        (self.root/'projects/1').mkdir(parents=True)
        (self.root/'media').mkdir()
        ff=e.tool('ffmpeg')
        for ident,freq in [(1,440),(2,880)]:
            e.run([ff,'-v','error','-f','lavfi','-i',f'sine=frequency={freq}:duration=2:sample_rate=48000',str(self.root/f'projects/1/{ident}.wav')])
        e.run([ff,'-v','error','-f','lavfi','-i','color=c=red:s=160x90:r=30:d=0.5','-c:v','libx264','-pix_fmt','yuv420p',str(self.root/'media/1.mp4')])
        self.song=e.Song({'id':1,'name':'CON: prueba','id_media':1,'extension':'mp4','loop_video':0},
            [{'id':2,'stereo_position':'R','id_track_stereo':1,'volume':1000},
             {'id':1,'stereo_position':'L','id_track_stereo':2,'volume':1000}],self.root)
        self.dest=Path(self.tmp.name)/'output'

    def tearDown(self):self.tmp.cleanup()

    def last_pixel(self,path):
        import subprocess
        data=subprocess.check_output([e.tool('ffmpeg'),'-v','error','-ss','1.5','-i',str(path),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
        return tuple(data[:3])

    def test_black_and_stereo_and_resume(self):
        path,status=e.export_song(self.song,self.dest)
        self.assertEqual(status,'exportado')
        self.assertLess(max(self.last_pixel(path)),15)
        self.assertAlmostEqual(float(e.probe(path)['format']['duration']),2,delta=.1)
        # Decode each output channel: zero crossing frequency checks actual L/R mapping.
        import subprocess,array
        for channel,freq in [(0,440),(1,880)]:
            raw=subprocess.check_output([e.tool('ffmpeg'),'-v','error','-i',str(path),'-af',f'pan=mono|c0=c{channel}','-t','1','-f','f32le','-'])
            samples=array.array('f');samples.frombytes(raw)
            crossings=sum(a<=0<b for a,b in zip(samples,samples[1:]))
            self.assertAlmostEqual(crossings,freq,delta=8)
        self.assertIn('omitido',e.export_song(self.song,self.dest)[1])
        with self.assertRaises(e.ExportError):e.export_song(self.song,self.dest,ending='freeze')

    def test_loop_and_freeze(self):
        self.song.project['loop_video']=1
        path,_=e.export_song(self.song,self.dest)
        self.assertGreater(self.last_pixel(path)[0],200)
        self.song.project['loop_video']=0
        path,_=e.export_song(self.song,Path(self.tmp.name)/'freeze',ending='freeze')
        self.assertGreater(self.last_pixel(path)[0],200)

    def test_cancellation_and_readonly_and_missing(self):
        cancel=threading.Event();cancel.set()
        with self.assertRaises(e.Cancelled):e.export_song(self.song,self.dest,cancel=cancel)
        self.assertFalse(list(self.dest.glob('*.mp4')))
        with self.assertRaises(e.ExportError):e.export_song(self.song,self.root/'exports')
        self.song.audio[0].unlink()
        self.assertTrue(self.song.issues())


if __name__=='__main__':unittest.main()
