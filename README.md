# B.Beat → Video

Exporta un MP4 por canción desde un backup M-Live B.Beat. Lee las asignaciones de la base SQLite `conf/bbeatdb` y reconstruye el estéreo desde los WAV mono izquierdo y derecho. No modifica el backup ni usa el audio que pueda traer el video.

## Windows

Descomprimí el ZIP y abrí `INICIAR.cmd`. Elegí la carpeta que contiene `conf`, `media` y `projects`; elegí un destino fuera del backup; seleccioná canciones y pulsá **Exportar seleccionadas**.

Esta entrega es el código listo para ejecutar; requiere Python 3.10+ con Tkinter y FFmpeg/FFprobe en PATH o dentro de `bin/`. Ambos ya estaban instalados en la PC donde se hicieron las pruebas. No incluye un EXE compilado ni el backup.

## Comportamiento

- MP4 H.264, calidad CRF 18, audio AAC estéreo 320 kb/s a 48 kHz.
- Conserva los timestamps/cuadros del video sin imponer 25 o 30 FPS.
- Duración determinada por el WAV, sin cortar la canción porque termine el video.
- Repite los videos cortos desde el principio hasta el final del audio, aunque el backup no tenga `loop_video` activado. La última repetición se corta al finalizar la canción.
- La opción predeterminada es **Repetir video hasta el final**. También permite negro o último cuadro congelado para proyectos sin loop si se eligen manualmente.
- **Abrir carpeta** abre la carpeta de destino en el explorador, incluso mientras se exporta.
- Omite exportaciones terminadas del mismo origen y configuración mediante recibos `.export.json`. No reemplaza MP4 existentes que no coincidan. Se puede cancelar y volver a iniciar: las canciones completas se omiten y la incompleta se vuelve a renderizar.
- Registra los errores de FFmpeg junto a los videos. Los archivos parciales se eliminan al cancelar o fallar.

Al actualizar desde la versión anterior, elegí una carpeta nueva para volver a exportar con loops automáticos: los MP4 existentes no se sobrescriben cuando cambia la configuración.

## Alcance verificado

Formato observado en un backup con 44 proyectos, cada uno con un par L/R enlazado. Comprueba archivos, canales mono, duración igual de L/R y duración/estéreo de salida. Rechaza estructuras o ajustes que no implementa: múltiples stems, volúmenes no estándar, mute/solo, EQ, transposición, offsets o fundidos. Los MIDI no se convierten a audio ni se incorporan al MP4.

El emparejamiento de archivos usa los identificadores internos, no aproximaciones por nombres:

```
conf/bbeatdb
projects/<project.id>/<track.id>.wav
media/<project.id_media>.mp4
```

## Consola

```powershell
python exporter.py "D:\Mi backup"
python exporter.py "D:\Mi backup" --output "D:\Videos" --ids 13 14 18
```

## Compilar portable

Colocá `ffmpeg.exe` y `ffprobe.exe` de una distribución oficial/conocida en `bin/`, instalá `requirements-build.txt` y ejecutá:

```powershell
python -m PyInstaller --noconfirm --clean --windowed --name BBeat-Video --add-binary "bin/ffmpeg.exe;bin" --add-binary "bin/ffprobe.exe;bin" app.py
```

No subir backups, audio ni video al repositorio. La distribución de FFmpeg requiere conservar sus avisos y cumplir la licencia de la compilación utilizada.
