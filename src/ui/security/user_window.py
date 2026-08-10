"""Minimal local user administration window."""
class UserManagementWindow:
 def __init__(self,root,controller,on_close=None):
  import tkinter as tk
  from tkinter import ttk
  self.controller=controller;self.on_close=on_close;self.window=tk.Toplevel(root);self.window.title("Usuarios operadores");self.window.protocol("WM_DELETE_WINDOW",self.close)
  self.tree=ttk.Treeview(self.window,columns=("username","name","role","status"),show="headings")
  for key,label in (("username","Usuario"),("name","Nombre"),("role","Rol"),("status","Estado")):self.tree.heading(key,text=label)
  self.tree.pack(fill="both",expand=True);ttk.Button(self.window,text="Refrescar",command=self.refresh).pack();self.refresh()
 def refresh(self):
  self.tree.delete(*self.tree.get_children())
  for user in self.controller.list_users():self.tree.insert("", "end",values=(user.username,user.display_name,user.role,user.status))
 def focus(self):self.window.lift();self.window.focus_force()
 def close(self):self.window.destroy();self.on_close and self.on_close()
