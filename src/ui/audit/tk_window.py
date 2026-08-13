"""Singleton-friendly Tk view for administrative audit records."""
from __future__ import annotations
from pathlib import Path
from tkinter import filedialog,ttk
from src.core.audit import AuditQuery

class AuditLogWindow:
 def __init__(self,master,controller,on_close=None):
  import tkinter as tk
  self.controller=controller;self.on_close=on_close;self.window=tk.Toplevel(master);self.window.title("Auditoría administrativa");self.window.geometry("1050x600");self.window.protocol("WM_DELETE_WINDOW",self.close)
  self.status=ttk.Label(self.window,text="");self.status.pack(fill="x",padx=8,pady=6)
  self.tree=ttk.Treeview(self.window,columns=("time","action","result","actor","entity","message"),show="headings")
  for key,title in (("time","Fecha UTC"),("action","Acción"),("result","Resultado"),("actor","Actor"),("entity","Entidad"),("message","Mensaje")):self.tree.heading(key,text=title)
  self.tree.pack(fill="both",expand=True,padx=8,pady=4)
  actions=ttk.Frame(self.window);actions.pack(fill="x",padx=8,pady=8);ttk.Button(actions,text="Refrescar",command=self.refresh).pack(side="left");ttk.Button(actions,text="Exportar CSV",command=self.export_csv).pack(side="left",padx=5);ttk.Button(actions,text="Cerrar",command=self.close).pack(side="right")
  self.refresh()
 def focus(self):self.window.lift();self.window.focus_force()
 def refresh(self):
  try:
   value=self.controller.query();self.tree.delete(*self.tree.get_children())
   for item in value.records:self.tree.insert("", "end",values=(item.timestamp_utc.isoformat(),item.action,"OK" if item.success else "FALLO",item.actor_user_id or "N/D",f"{item.entity_type}:{item.entity_id or 'N/D'}",item.message))
   self.status.configure(text=value.message)
  except Exception:self.status.configure(text="No se pudo consultar la auditoría")
 def export_csv(self):
  selected=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=(("CSV","*.csv"),))
  if not selected:return
  try:self.status.configure(text=self.controller.export_csv(Path(selected)).message)
  except Exception:self.status.configure(text="No se pudo exportar la auditoría")
 def close(self):
  self.window.destroy()
  if self.on_close:self.on_close()

