from __future__ import annotations
import json
from src.core.configuration.validators import redact
try:
 import tkinter as tk
 from tkinter import filedialog,messagebox,ttk
except ModuleNotFoundError:tk=filedialog=messagebox=ttk=None
class ConfigurationWindow:
 def __init__(self,root,controller,on_close=None):
  self.controller=controller;self.on_close=on_close;self.window=tk.Toplevel(root);self.window.title("Configuración");self.window.protocol("WM_DELETE_WINDOW",self.close);self.loaded=controller.current();self.notice=ttk.Label(self.window,text="Configuración en formato legado; se recomienda actualizar." if self.loaded.legacy_configuration else f"Perfil {self.loaded.profile.value}");self.notice.pack(anchor="w",padx=8,pady=4);self.editor=tk.Text(self.window,width=100,height=32);self.editor.pack(fill="both",expand=True,padx=8);self._restore()
  bar=ttk.Frame(self.window);bar.pack(fill="x",padx=8,pady=8);ttk.Button(bar,text="Validar",command=self.validate).pack(side="left");self.save_button=ttk.Button(bar,text="Guardar",command=self.save,state="normal" if controller.can_edit() else "disabled");self.save_button.pack(side="left");ttk.Button(bar,text="Recargar",command=self.reload).pack(side="left");ttk.Button(bar,text="Restaurar valores cargados",command=self._restore).pack(side="left");self.import_button=ttk.Button(bar,text="Importar",command=self.import_file,state="normal" if controller.can_edit() else "disabled");self.import_button.pack(side="left");ttk.Button(bar,text="Exportar",command=self.export_file).pack(side="left");ttk.Button(bar,text="Cerrar",command=self.close).pack(side="right");self.status=ttk.Label(self.window,text="Snapshot cargado; ningún cambio se aplica automáticamente.");self.status.pack(anchor="w",padx=8,pady=4)
 def _text(self):return self.editor.get("1.0","end-1c")
 def _restore(self):self.editor.delete("1.0","end");self.editor.insert("1.0",json.dumps(redact(self.loaded.as_mapping()),indent=2,sort_keys=True))
 def validate(self):
  try:
   result=self.controller.validate_text(self._text());diff=self.controller.diff_text(self._text());self.status.configure(text=f"Válida: {result.valid}; hot: {len(diff.hot_reloadable)}; reinicio: {len(diff.restart_required)}; inmutables: {len(diff.immutable)}. Solo snapshot, no aplicado.")
  except Exception:self.status.configure(text="La configuración no es válida.")
 def save(self):
  result=self.controller.save_text(self._text());self.status.configure(text=result.message+(f" {result.warning}" if result.warning else ""));self.loaded=self.controller.current() if result.success else self.loaded
 def reload(self):
  result=self.controller.reload();self.loaded=self.controller.current();self._restore();self.status.configure(text=result.message)
 def import_file(self):
  name=filedialog.askopenfilename(parent=self.window,filetypes=(("JSON","*.json"),))
  if not name:return
  try:
   candidate,diff=self.controller.import_file(__import__('pathlib').Path(name));summary=f"Hot: {len(diff.hot_reloadable)}, reinicio: {len(diff.restart_required)}, inmutables: {len(diff.immutable)}. ¿Cargar candidato en editor?"
   if messagebox.askyesno("Importar configuración",summary,parent=self.window):self.editor.delete("1.0","end");self.editor.insert("1.0",json.dumps(redact(candidate),indent=2,sort_keys=True))
  except Exception:self.status.configure(text="La importación fue rechazada.")
 def export_file(self):
  name=filedialog.asksaveasfilename(parent=self.window,defaultextension=".json")
  if name:
   try:self.status.configure(text=self.controller.export_file(__import__('pathlib').Path(name)).message)
   except Exception:self.status.configure(text="No se pudo exportar.")
 def focus(self):self.window.lift();self.window.focus_force()
 def close(self):self.window.destroy();self.on_close and self.on_close()
