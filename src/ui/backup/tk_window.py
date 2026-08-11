"""Singleton-compatible Tk backup window; work runs outside Tk's thread."""
from __future__ import annotations
import threading
try:
 import tkinter as tk
 from tkinter import filedialog,messagebox,ttk
except ModuleNotFoundError:tk=filedialog=messagebox=ttk=None
class BackupWindow:
 def __init__(self,root,controller,on_close=None,on_restore_success=None):
  self.controller=controller;self.on_close=on_close;self.on_restore_success=on_restore_success;self.window=tk.Toplevel(root);self.window.title("Copias de seguridad");self.window.protocol("WM_DELETE_WINDOW",self.close)
  ttk.Label(self.window,text="El backup contiene información sensible y no está cifrado.").pack(padx=12,pady=8);self.status=ttk.Label(self.window,text="Estado: disponible");self.status.pack();self.history_list=tk.Listbox(self.window,height=6);self.history_list.pack(fill="both",expand=True,padx=12,pady=8)
  bar=ttk.Frame(self.window);bar.pack(padx=12,pady=8)
  self.create_button=ttk.Button(bar,text="Crear backup",command=self._create,state="normal" if controller.can_backup() else "disabled");self.create_button.pack(side="left")
  self.verify_button=ttk.Button(bar,text="Verificar backup",command=self._verify,state="normal" if controller.can_backup() else "disabled");self.verify_button.pack(side="left")
  self.restore_button=ttk.Button(bar,text="Restaurar backup",command=self._restore,state="normal" if controller.can_restore() else "disabled");self.restore_button.pack(side="left")
  ttk.Button(bar,text="Cerrar",command=self.close).pack(side="left")
 def focus(self):self.window.lift();self.window.focus_force()
 def _run(self,work,done=None):
  self.status.configure(text="Estado: procesando");threading.Thread(target=lambda:self._complete(work,done),daemon=True).start()
 def _complete(self,work,done):
  try:result=work();self.window.after(0,self._finish,"Operación completada",done,result)
  except Exception:self.window.after(0,self._finish,"La operación falló de forma segura",None,None)
 def _finish(self,message,done,result):self.status.configure(text=f"Estado: {message}");self._refresh();done and done(result)
 def _create(self):
  name=filedialog.asksaveasfilename(parent=self.window,defaultextension=".fvbackup",filetypes=(("FastVisionAI backup","*.fvbackup"),));name and self._run(lambda:self.controller.create(__import__('pathlib').Path(name)))
 def _verify(self):
  name=filedialog.askopenfilename(parent=self.window,filetypes=(("FastVisionAI backup","*.fvbackup"),));name and self._run(lambda:self.controller.verify(__import__('pathlib').Path(name)))
 def _restore(self):
  name=filedialog.askopenfilename(parent=self.window,filetypes=(("FastVisionAI backup","*.fvbackup"),))
  if name and messagebox.askyesno("Confirmar restauración","La aplicación se cerrará después de restaurar.",parent=self.window):self._run(lambda:self.controller.restore(self.controller.prepare_restore(__import__('pathlib').Path(name)),confirmed=True),self.on_restore_success)
 def _refresh(self):
  self.history_list.delete(0,"end")
  for item in self.controller.history():self.history_list.insert("end",f"{item.timestamp.isoformat()} {item.operation}: {item.message}")
 def close(self):self.window.destroy();self.on_close and self.on_close()
