"""Modal Tk login/bootstrap window. No camera is started while it is open."""
from __future__ import annotations
from types import SimpleNamespace
try:
 import tkinter as tk
 from tkinter import ttk
except ModuleNotFoundError: tk=ttk=None

class LoginWindow:
 def __init__(self,root,controller):
  if tk is None:raise RuntimeError("Tkinter is unavailable")
  self.root=root;self.controller=controller;self.authenticated=False;self.window=tk.Toplevel(root);self.window.title("FastVisionAI — Inicio de sesión");self.window.protocol("WM_DELETE_WINDOW",self.cancel)
  bootstrap=controller.needs_bootstrap();self.bootstrap=bootstrap
  ttk.Label(self.window,text="Crear administrador inicial" if bootstrap else "Inicio de sesión").grid(row=0,column=0,columnspan=2,padx=16,pady=12)
  ttk.Label(self.window,text="Usuario").grid(row=1,column=0);self.username=ttk.Entry(self.window);self.username.grid(row=1,column=1)
  self.display_name=None
  row=2
  if bootstrap:
   ttk.Label(self.window,text="Nombre visible").grid(row=row,column=0);self.display_name=ttk.Entry(self.window);self.display_name.grid(row=row,column=1);row+=1
  ttk.Label(self.window,text="Contraseña").grid(row=row,column=0);self.password=ttk.Entry(self.window,show="•");self.password.grid(row=row,column=1);row+=1
  self.confirmation=None
  if bootstrap:
   ttk.Label(self.window,text="Confirmar contraseña").grid(row=row,column=0);self.confirmation=ttk.Entry(self.window,show="•");self.confirmation.grid(row=row,column=1);row+=1
  self.message=ttk.Label(self.window,text="",wraplength=360,justify="center");self.message.grid(row=row,column=0,columnspan=2,sticky="ew",padx=16,pady=(12,8))
  ttk.Button(self.window,text="Crear" if bootstrap else "Ingresar",command=self.submit).grid(row=row+1,column=0);ttk.Button(self.window,text="Salir",command=self.cancel).grid(row=row+1,column=1)
  self.window.bind("<Return>",lambda _e:self.submit());self._prepare_window()
 def _prepare_window(self):
  """Map and center the modal independently from a withdrawn application root."""
  self.window.update_idletasks()
  width=max(420,int(self.window.winfo_reqwidth()));height=max(280,int(self.window.winfo_reqheight()))
  screen_width=int(self.window.winfo_screenwidth());screen_height=int(self.window.winfo_screenheight())
  x=max(0,(screen_width-width)//2);y=max(0,(screen_height-height)//2)
  self.window.minsize(420,280);self.window.geometry(f"{width}x{height}+{x}+{y}")
  try:root_visible=str(self.root.state())!="withdrawn" and bool(self.root.winfo_viewable())
  except Exception:root_visible=False
  if root_visible:self.window.transient(self.root)
  self.window.deiconify();self.window.lift();self.window.focus_force();self.window.grab_set();self.username.focus_set()
 def submit(self):
  self.message.configure(text="")
  username=self.username.get();password=self.password.get()
  if self.bootstrap:
   confirmation=self.confirmation.get();validation=self._validate_bootstrap(username,password,confirmation)
   if validation is not None:
    message,field=validation;self._show_error(message,field);return
   try:result=self.controller.bootstrap(username,self.display_name.get(),password,confirmation)
   except Exception:
    self._show_error("No se pudo crear el administrador inicial.",self.username);return
  else:
   try:result=self.controller.login(username,password)
   except Exception:result=SimpleNamespace(success=False)
  self.password.delete(0,"end")
  if self.confirmation:self.confirmation.delete(0,"end")
  if result.success:self.authenticated=True;self.window.destroy()
  elif self.bootstrap:self._show_error(self._safe_bootstrap_message(getattr(result,"message","")),self.username)
  else:self._show_error("Credenciales inválidas.",self.username)
 def _validate_bootstrap(self,username,password,confirmation):
  import re
  if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}",username.strip()):return "El usuario no es válido.",self.username
  policy=getattr(getattr(getattr(self.controller,"authentication",None),"hasher",None),"policy",None);minimum=int(getattr(policy,"minimum_length",10));maximum=int(getattr(policy,"maximum_length",128))
  if len(password)<minimum:return f"La contraseña debe tener al menos {minimum} caracteres.",self.password
  if len(password)>maximum:return "La contraseña supera la longitud permitida.",self.password
  if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):return "La contraseña debe contener al menos una letra y un número.",self.password
  if password!=confirmation:return "Las contraseñas no coinciden.",self.confirmation
  return None
 @staticmethod
 def _safe_bootstrap_message(message):
  allowed={"Las contraseñas no coinciden.","El bootstrap no está disponible."}
  return message if message in allowed else "No se pudo crear el administrador inicial."
 def _show_error(self,message,field):
  self.message.configure(text=message);self.window.update_idletasks()
  try:field.focus_set()
  except Exception:pass
 def cancel(self):self.authenticated=False;self.window.destroy()
 def run(self):self.root.wait_window(self.window);return self.authenticated
