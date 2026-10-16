"""Read-only B.Beat backup reader and stereo/video exporter. Python 3.10+."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
from dataclasses import dataclass


class ExportError(Exception):
    pass


class Cancelled(ExportError):
    pass


def tool(name):
    suffix = '.exe' if os.name == 'nt' else ''
    bundled = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'bin' / (name + suffix)
    if bundled.is_file():
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    if name == 'ffmpeg':
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass
    raise ExportError(f'No se encontró {name}. Colocá {name}{suffix} en bin o instalá FFmpeg.')


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if p.returncode:
        raise ExportError(p.stderr[-4000:])
    return p.stdout


def probe(path):
    return json.loads(run([tool('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name)).strip(' .')[:140] or 'Canción'


@dataclass
class Song:
    project: dict
    tracks: list[dict]
    root: Path

    @property
    def id(self):
        return self.project['id']

    @property
    def name(self):
        return self.project['name']

    @property
    def video(self):
        return self.root / 'media' / f"{self.project['id_media']}.{self.project['extension']}"

    @property
    def audio(self):
        return [self.root / 'projects' / str(self.id) / f"{t['id']}.wav" for t in self.tracks]

    def issues(self):
        errors = []
        if len(self.tracks) != 2 or {t['stereo_position'] for t in self.tracks} != {'L', 'R'}:
            errors.append('Se requiere exactamente un par L/R; este proyecto tiene otra estructura.')
        if len(self.tracks) == 2 and any(t.get('id_track_stereo') != self.tracks[1-i]['id'] for i,t in enumerate(self.tracks)):
            errors.append('Los canales no están enlazados como par estéreo.')
        if any(t.get('mute') or t.get('solo') or t.get('volume') != 1000 for t in self.tracks):
            errors.append('Volumen, mute o solo no estándar: requiere revisión manual.')
        if any(t.get('equalizer') not in (None, '', 'null', '{}', '[]') for t in self.tracks):
            errors.append('Ecualizador configurado: requiere revisión manual.')
        for key in ('start_offset_millis', 'end_offset_millis', 'delay_video', 'transpose'):
            if self.project.get(key):
                errors.append(f'{key} no es cero: requiere revisión manual.')
        for key in ('fadein_time', 'fadeout_time'):
            if self.project.get(key, -1) not in (-1, 0, None):
                errors.append('Fundido configurado: requiere revisión manual.')
        for path in [self.video, *self.audio]:
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f'Falta {path.relative_to(self.root)}')
        if not self.project.get('extension'):
            errors.append('No hay video asignado.')
        return errors


def load_backup(directory):
    root = Path(directory).resolve()
    db = root / 'conf' / 'bbeatdb'
    if not db.is_file():
        raise ExportError('Elegí la carpeta que contiene conf, media y projects.')
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as c:
        c.row_factory = sqlite3.Row
        projects = [dict(r) for r in c.execute('SELECT p.*, m.extension, m.name video_name FROM projects p LEFT JOIN media m ON m.id=p.id_media ORDER BY p.id')]
        tracks = [dict(r) for r in c.execute('SELECT * FROM tracks ORDER BY ord,id')]
    return [Song(p, [t for t in tracks if t['id_project'] == p['id']], root) for p in projects]


def fingerprint(song, settings):
    fields = {k:v for k,v in song.project.items() if k != 'stems_info'}
    sources = [(str(p.relative_to(song.root)), p.stat().st_size, p.stat().st_mtime_ns) for p in [song.video,*song.audio]]
    payload = json.dumps([fields, song.tracks, sources, settings], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def export_song(song, destination, progress=lambda value: None, cancel=None, ending='loop', crf=18):
    """Repeat short visuals by default, bounded by exact WAV duration."""
    if ending not in ('loop', 'black', 'freeze'):
        raise ExportError('Modo de final de video no válido.')
    errors = song.issues()
    if errors:
        raise ExportError('\n'.join(errors))
    destination = Path(destination).resolve()
    if destination == song.root or song.root in destination.parents:
        raise ExportError('Elegí un destino fuera de la carpeta del backup.')
    destination.mkdir(parents=True, exist_ok=True)
    base = f'{song.id:02d} - {safe_name(song.name)}'
    target = destination / (base + '.mp4')
    receipt = destination / (base + '.export.json')
    settings = {'version':1,'ending':ending,'crf':crf}
    signature = fingerprint(song, settings)
    if target.exists():
        try:
            saved = json.loads(receipt.read_text('utf-8'))
            if saved['signature'] == signature and saved['size'] == target.stat().st_size:
                progress(1)
                return target, 'omitido (ya exportado)'
        except (OSError, ValueError, KeyError):
            pass
        raise ExportError(f'Ya existe {target.name} y no coincide con esta exportación. Elegí otra carpeta o renombrá el archivo existente.')
    audio_info = [probe(p) for p in song.audio]
    for info in audio_info:
        streams = [s for s in info['streams'] if s['codec_type'] == 'audio']
        if len(streams) != 1 or streams[0]['channels'] != 1:
            raise ExportError('Se esperaban WAV mono para los canales L/R.')
    durations = [float(i['streams'][0].get('duration', i['format']['duration'])) for i in audio_info]
    if abs(durations[0] - durations[1]) > .002:
        raise ExportError('Los canales L/R tienen distinta duración.')
    duration = max(durations)
    video_info = probe(song.video)
    if not any(s['codec_type'] == 'video' for s in video_info['streams']):
        raise ExportError('El archivo de visuales no contiene video.')
    temp = destination / (base + '.partial.mp4')
    log = destination / (base + '.ffmpeg.log')
    cmd = [tool('ffmpeg'), '-hide_banner', '-nostdin', '-y']
    loop_video = bool(song.project['loop_video']) or ending == 'loop'
    if loop_video:
        cmd += ['-stream_loop', '-1']
    cmd += ['-i', str(song.video)]
    for audio in song.audio:
        cmd += ['-i', str(audio)]
    left = 1 + next(i for i,t in enumerate(song.tracks) if t['stereo_position'] == 'L')
    right = 1 + next(i for i,t in enumerate(song.tracks) if t['stereo_position'] == 'R')
    vf = 'scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,setpts=PTS-STARTPTS'
    if not loop_video:
        vf += ',tpad=stop_mode=' + ('clone' if ending == 'freeze' else 'add:color=black') + f':stop_duration={duration:.9f}'
    af = f'[{left}:a:0][{right}:a:0]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR,asetpts=PTS-STARTPTS[a]'
    cmd += ['-filter_complex', vf.join(['[0:v:0]', '[v];']) + af,
            '-map', '[v]', '-map', '[a]', '-t', f'{duration:.9f}',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', str(crf), '-pix_fmt', 'yuv420p',
            '-fps_mode', 'passthrough', '-c:a', 'aac', '-b:a', '320k', '-ar', '48000',
            '-movflags', '+faststart', '-metadata', f'title={song.name}',
            '-progress', 'pipe:1', '-nostats', str(temp)]
    try:
        with log.open('w', encoding='utf-8') as err:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            watcher_done = threading.Event()
            def watch():
                while not watcher_done.wait(.2):
                    if cancel is not None and cancel.is_set() and proc.poll() is None:
                        proc.terminate()
                        return
            watcher = threading.Thread(target=watch, daemon=True)
            watcher.start()
            try:
                for line in proc.stdout:
                    if line.startswith('out_time_us='):
                        try:
                            progress(min(.99, float(line.split('=')[1]) / 1_000_000 / duration))
                        except ValueError:
                            pass
                code = proc.wait()
            finally:
                watcher_done.set()
                watcher.join()
                proc.stdout.close()
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait()
        if cancel is not None and cancel.is_set():
            raise Cancelled('Exportación cancelada.')
        if code:
            raise ExportError(log.read_text('utf-8',errors='replace')[-4000:])
        result = probe(temp)
        output_audio = next(s for s in result['streams'] if s['codec_type']=='audio')
        if output_audio['channels'] != 2 or abs(float(result['format']['duration'])-duration) > .2:
            raise ExportError('La verificación de duración o estéreo falló.')
        if target.exists():
            raise ExportError('El destino apareció durante la exportación; no se reemplazó.')
        temp.rename(target)
        receipt.write_text(json.dumps({'signature':signature,'size':target.stat().st_size,'duration':duration,'song':song.name,'settings':settings},ensure_ascii=False,indent=2),encoding='utf-8')
        progress(1)
        return target, 'exportado'
    finally:
        temp.unlink(missing_ok=True)


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Exportar audio y video desde un backup B.Beat')
    parser.add_argument('backup');parser.add_argument('--output');parser.add_argument('--ids',nargs='*',type=int)
    parser.add_argument('--ending',choices=['loop','black','freeze'],default='loop')
    args=parser.parse_args()
    for song in load_backup(args.backup):
        if args.ids is not None and song.id not in args.ids:
            continue
        print(song.id,song.name,'; '.join(song.issues()) or 'OK',flush=True)
        if args.output:
            path,status=export_song(song,args.output,ending=args.ending)
            print(status,path,flush=True)
