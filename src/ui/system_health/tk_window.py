try:
 import tkinter as tk
 from tkinter import ttk
except ModuleNotFoundError:tk=ttk=None
class SystemHealthWindow:
 def __init__(self,root,controller,on_close=None):
  self.controller=controller;self.on_close=on_close;self.window=tk.Toplevel(root);self.window.title("Diagnóstico del sistema");self.window.protocol("WM_DELETE_WINDOW",self.close)
  self.tree=ttk.Treeview(self.window,columns=("component","state","message","checked"),show="headings")
  for key,label in (("component","Componente"),("state","Estado"),("message","Mensaje"),("checked","Última comprobación")):self.tree.heading(key,text=label)
  self.tree.pack(fill="both",expand=True);self.performance=ttk.Label(self.window,text="N/D");self.performance.pack(anchor="w");ttk.Button(self.window,text="Actualizar",command=self.refresh).pack(side="left");ttk.Button(self.window,text="Cerrar",command=self.close).pack(side="right");self.refresh()
 def refresh(self):
  dto=self.controller.snapshot();self.tree.delete(*self.tree.get_children())
  for item in dto.components:self.tree.insert("","end",values=item)
  self.performance.configure(text=f"FPS: {dto.fps} | Intervalo: {dto.frame_interval} | Procesamiento: {dto.processing_latency} | Inferencia: {dto.inference_latency}\nCola: {dto.queue_depth} | Descartes: {dto.dropped_frames} | Memoria estimada: {dto.memory} | Uptime: {dto.uptime}")
 def focus(self):self.window.lift();self.window.focus_force()
 def close(self):self.window.destroy();self.on_close and self.on_close()
