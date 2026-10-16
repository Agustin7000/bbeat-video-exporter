"""Small native Windows interface. All Tk operations stay on the UI thread."""
from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from exporter import load_backup, export_song, Cancelled, tool


class App:
    def __init__(self, root):
        self.root=root
        root.title('B.Beat → Video')
        root.geometry('920x650');root.minsize(760,520)
        self.songs=[];self.events=queue.Queue();self.cancel=threading.Event();self.busy=False
        self.backup=tk.StringVar();self.output=tk.StringVar();self.ending=tk.StringVar(value='Repetir video hasta el final')
        self.status=tk.StringVar(value='Elegí el backup para encontrar sus canciones.')
        frame=ttk.Frame(root,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='B.Beat → Video',font=('Segoe UI',23,'bold')).pack(anchor='w')
        ttk.Label(frame,text='Un MP4 por canción · Audio estéreo · Visuales del backup').pack(anchor='w',pady=(0,18))
        for text,var,callback in [('Carpeta del backup',self.backup,self.choose_backup),('Guardar videos en',self.output,self.choose_output)]:
            row=ttk.Frame(frame);row.pack(fill='x',pady=4)
            ttk.Label(row,text=text,width=22).pack(side='left')
            ttk.Entry(row,textvariable=var,state='readonly').pack(side='left',fill='x',expand=True,padx=8)
            ttk.Button(row,text='Elegir…',command=callback).pack(side='right')
        row=ttk.Frame(frame);row.pack(fill='x',pady=10)
        ttk.Label(row,text='Si el video termina antes que el audio:').pack(side='left')
        self.endbox=ttk.Combobox(row,textvariable=self.ending,state='readonly',width=29,values=['Repetir video hasta el final','Negro al terminar el video','Mantener el último cuadro'])
        self.endbox.pack(side='left',padx=8)
        ttk.Label(frame,text='Seleccioná canciones con Ctrl o Shift. Los loops se repiten hasta el final del audio.').pack(anchor='w',pady=6)
        listing=ttk.Frame(frame);listing.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(listing,columns=('name','video','loop','state'),show='headings',selectmode='extended')
        for key,label,width in [('name','Canción',310),('video','Visual',170),('loop','Loop backup',90),('state','Estado',170)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=width)
        scroll=ttk.Scrollbar(listing,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set);self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        row=ttk.Frame(frame);row.pack(fill='x',pady=12)
        ttk.Button(row,text='Seleccionar todas',command=lambda:self.tree.selection_set(self.tree.get_children())).pack(side='left')
        self.open_button=ttk.Button(row,text='Abrir carpeta',command=self.open_output,state='disabled')
        self.open_button.pack(side='left',padx=8)
        self.go=ttk.Button(row,text='Exportar seleccionadas',command=self.start);self.go.pack(side='right')
        ttk.Button(row,text='Cancelar',command=self.cancel.set).pack(side='right',padx=8)
        self.bar=ttk.Progressbar(frame,maximum=100);self.bar.pack(fill='x')
        ttk.Label(frame,textvariable=self.status,wraplength=850).pack(anchor='w',pady=(8,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def choose_backup(self):
        if self.busy:return
        path=filedialog.askdirectory(title='Elegí la carpeta que contiene conf, media y projects')
        if not path:return
        try:self.songs=load_backup(path)
        except Exception as e:messagebox.showerror('No se pudo leer el backup',str(e));return
        self.backup.set(path);self.tree.delete(*self.tree.get_children())
        valid=[]
        for song in self.songs:
            issues=song.issues()
            self.tree.insert('', 'end',iid=str(song.id),values=(song.name,song.project.get('video_name') or 'Sin video','Sí' if song.project['loop_video'] else 'No','; '.join(issues) if issues else 'Listo'))
            if not issues:valid.append(str(song.id))
        self.tree.selection_set(valid)
        self.status.set(f'{len(self.songs)} canciones · {len(valid)} listas para exportar')

    def choose_output(self):
        if not self.busy:
            path=filedialog.askdirectory(title='Elegí una carpeta fuera del backup')
            if path:
                self.output.set(path)
                self.open_button.configure(state='normal')

    def open_output(self):
        path=Path(self.output.get())
        if not self.output.get() or not path.is_dir():
            messagebox.showinfo('Carpeta no disponible','Elegí una carpeta de destino existente.');return
        try:
            if os.name=='nt':os.startfile(str(path.resolve()))
            else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(path.resolve())])
        except OSError as e:messagebox.showerror('No se pudo abrir la carpeta',str(e))

    def start(self):
        if self.busy:return
        selected=set(self.tree.selection());songs=[s for s in self.songs if str(s.id) in selected]
        if not songs or not self.output.get():messagebox.showinfo('Falta una selección','Elegí canciones y carpeta de destino.');return
        try:tool('ffmpeg');tool('ffprobe')
        except Exception as e:messagebox.showerror('Falta FFmpeg',str(e));return
        self.cancel.clear();self.busy=True;self.go.configure(state='disabled');self.endbox.configure(state='disabled')
        ending={'Repetir video hasta el final':'loop','Mantener el último cuadro':'freeze','Negro al terminar el video':'black'}[self.ending.get()]
        destination=self.output.get()
        def work():
            errors=[];completed=0
            for i,song in enumerate(songs):
                if self.cancel.is_set():break
                self.events.put(('status',f'{i+1}/{len(songs)} · {song.name}'))
                def update(v):self.events.put(('progress',100*(i+v)/len(songs)))
                try:
                    _,state=export_song(song,destination,update,self.cancel,ending)
                    completed+=1;self.events.put(('state',str(song.id),state))
                except Cancelled:break
                except Exception as e:
                    errors.append(f'{song.name}: {e}');self.events.put(('state',str(song.id),'Error: '+str(e).splitlines()[0]))
            self.events.put(('done',completed,len(songs),errors,self.cancel.is_set()))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait()
                if event[0]=='status':self.status.set(event[1])
                elif event[0]=='progress':self.bar['value']=event[1]
                elif event[0]=='state':self.tree.set(event[1],'state',event[2])
                elif event[0]=='done':
                    self.busy=False;self.go.configure(state='normal');self.endbox.configure(state='readonly')
                    self.status.set(f'{"Cancelado" if event[4] else "Finalizado"} · {event[1]}/{event[2]} completadas · {len(event[3])} errores')
                    if event[3]:messagebox.showerror('Algunas canciones no se exportaron','\n\n'.join(event[3])[:7000])
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def close(self):
        if self.busy:
            self.cancel.set();self.status.set('Cancelando… cerrá la ventana cuando termine.');return
        self.root.destroy()


if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
