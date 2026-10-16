# Validación — 16 de octubre de 2026

Se exportaron tres canciones completas desde archivos del backup real:

| Canción | Duración MP4 | Video | Audio |
|---|---:|---|---|
| RENAULT 12 | 151,833 s | H.264, 1536×768, 30 FPS | AAC estéreo |
| CUENTA DNI | 169,667 s | H.264, 1536×768, 30 FPS, loop | AAC estéreo |
| R12 PRESIDENTE | 236,000 s | H.264, 1536×768, 30 FPS | AAC estéreo |

Las tres salidas pasaron una decodificación completa sin errores y la comprobación automática de duración/canales. Al ejecutar de nuevo, se omitieron correctamente sin reemplazarlas. No se hizo una audición ni revisión visual completa: la validación técnica no sustituye esa revisión antes de usar los archivos en vivo.

Cuatro pruebas de integración con material sintético verificaron:

- Orden de canales: fuente de 440 Hz a la izquierda y 880 Hz a la derecha, comprobado después de codificar y decodificar.
- Audio de dos segundos completo aunque el video termine a los 0,5 s: negro, congelado y loop según elección.
- Repetición automática predeterminada aun con el loop del backup desactivado: video de 0,5 s repetido en una salida de 2 s y 60 cuadros a 30 FPS, sin extender la canción.
- Reanudación, rechazo de un MP4 previo con otra configuración, cancelación, archivos faltantes y rechazo del destino dentro del backup.

La interfaz pudo inicializarse correctamente. El formato de este backup no contiene offsets, fundidos, transposición, ecualización ni volúmenes distintos de la unidad; el programa rechaza esos ajustes en otros backups para evitar exportaciones silenciosamente incorrectas.

La compilación a EXE y los workflows de GitHub quedan sin ejecutar. Esta entrega se ejecuta con `INICIAR.cmd`, Python y FFmpeg instalados.
