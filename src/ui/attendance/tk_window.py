"""Singleton-capable local-day attendance presentation."""
from __future__ import annotations
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
try:
    import tkinter as tk
    from tkinter import filedialog, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = filedialog = ttk = None
from src.core.attendance import AttendanceDayStatus
from src.ui.thumbnails.presentation import thumbnail_to_ppm

ZONE = ZoneInfo("America/Guayaquil")


def _duration(seconds: int) -> str:
    hours,remainder=divmod(max(0,seconds),3600);minutes=remainder//60
    return f"{hours:02d}:{minutes:02d}"


class AttendanceHistoryWindow:
    def __init__(self, root: Any, controller: Any, *, on_close=None,
                 on_view_person=None) -> None:
        if tk is None or ttk is None: raise RuntimeError("Tkinter no está disponible")
        self.controller=controller;self._on_close=on_close;self._on_view_person=on_view_person
        self._photos={};self.window=tk.Toplevel(root);self.window.title("CONTROL DE ASISTENCIA")
        self.window.protocol("WM_DELETE_WINDOW",self.close)
        self.today=tk.BooleanVar(self.window,value=True);self.day=tk.StringVar(self.window)
        self.name=tk.StringVar(self.window);self.cedula=tk.StringVar(self.window)
        self.state=tk.StringVar(self.window)
        ttk.Checkbutton(self.window,text="Hoy",variable=self.today).grid(row=0,column=0)
        ttk.Label(self.window,text="Fecha YYYY-MM-DD").grid(row=0,column=1)
        ttk.Entry(self.window,textvariable=self.day).grid(row=0,column=2)
        ttk.Label(self.window,text="Nombre").grid(row=0,column=3)
        ttk.Entry(self.window,textvariable=self.name).grid(row=0,column=4)
        ttk.Label(self.window,text="Cédula").grid(row=0,column=5)
        ttk.Entry(self.window,textvariable=self.cedula).grid(row=0,column=6)
        ttk.Label(self.window,text="Estado").grid(row=0,column=7)
        ttk.Combobox(self.window,textvariable=self.state,state="readonly",
            values=("",)+tuple(item.value for item in AttendanceDayStatus)).grid(row=0,column=8)
        columns=("name","cedula","in","out","worked","late","overtime","state")
        self.table=ttk.Treeview(self.window,columns=columns,show="tree headings")
        self.table.heading("#0",text="Foto")
        for key,label in zip(columns,("Nombre","Cédula","Entrada","Salida","Horas","Retraso","Horas extra","Estado")):
            self.table.heading(key,text=label)
        self.table.grid(row=1,column=0,columnspan=9,sticky="nsew")
        self.table.bind("<Double-1>",lambda _event:self.show_detail())
        ttk.Button(self.window,text="Refrescar",command=self.refresh).grid(row=2,column=0)
        ttk.Button(self.window,text="Ver detalle",command=self.show_detail).grid(row=2,column=1)
        ttk.Button(self.window,text="Exportar CSV",command=self.export).grid(row=2,column=2)
        ttk.Button(self.window,text="Cerrar",command=self.close).grid(row=2,column=8)
        self.status=ttk.Label(self.window);self.status.grid(row=3,column=0,columnspan=9)
        self.window.rowconfigure(1,weight=1)
        self.refresh()

    def focus(self)->None:self.window.lift();self.window.focus_force()

    def refresh(self)->None:
        try:
            selected=None if self.today.get() else datetime.strptime(self.day.get(),"%Y-%m-%d").date()
            result=self.controller.day_list(day=selected,name=self.name.get() or None,
                cedula=self.cedula.get() or None,status=self.state.get() or None)
            self.table.delete(*self.table.get_children());self._photos.clear()
            for item in result.days:
                photo=None;text="Sin fotografía"
                if self.controller.identity_provider is not None:
                    payload=thumbnail_to_ppm(self.controller.identity_provider.get_thumbnail(item.person_id))
                    if payload:photo=tk.PhotoImage(data=payload,format="PPM");self._photos[item.person_id]=photo;text=""
                local_in=None if item.check_in is None else item.check_in.astimezone(ZONE).strftime("%H:%M:%S")
                local_out=None if item.check_out is None else item.check_out.astimezone(ZONE).strftime("%H:%M:%S")
                self.table.insert("","end",iid=f"{item.person_id}|{item.local_date.isoformat()}",text=text,image=photo or "",values=(
                    item.display_name or "N/D",item.masked_cedula or "N/D",local_in or "—",local_out or "—",
                    _duration(item.worked_seconds),_duration(item.late_seconds),_duration(item.overtime_seconds),item.status))
            self.status.configure(text=result.message)
        except PermissionError as exc:self.status.configure(text=str(exc))
        except Exception:self.status.configure(text="Filtros inválidos")

    def show_detail(self)->None:
        selected=self.table.selection()
        if not selected:self.status.configure(text="Seleccione una jornada");return
        person_id,day_text=selected[0].split("|",1)
        detail=self.controller.detail(person_id,date.fromisoformat(day_text))
        if detail is None:return
        dialog=tk.Toplevel(self.window);dialog.title("DETALLE DE ASISTENCIA")
        photo=None
        if detail.thumbnail is not None:
            payload=thumbnail_to_ppm(detail.thumbnail)
            if payload:photo=tk.PhotoImage(data=payload,format="PPM")
        image=ttk.Label(dialog,text="Sin fotografía" if photo is None else "",image=photo or "");image.image=photo
        image.grid(row=0,column=0,rowspan=12,padx=10,pady=10)
        person=detail.person;day=detail.day
        values=(("Nombre",None if person is None else person.display_name),("Cédula",None if person is None else person.external_identifier),
            ("Cargo",None if person is None else person.position),("Departamento",None if person is None else person.department),
            ("Entrada",_local(day.check_in)),("Salida",_local(day.check_out)),("Horas trabajadas",_duration(day.worked_seconds)),
            ("Retraso",_duration(day.late_seconds)),("Horas extra",_duration(day.overtime_seconds)),
            ("Origen entrada",day.check_in_source),("Origen salida",day.check_out_source))
        for row,(label,value) in enumerate(values):
            ttk.Label(dialog,text=label+":").grid(row=row,column=1,sticky="e");ttk.Label(dialog,text=value or "N/D").grid(row=row,column=2,sticky="w")
        if self._on_view_person:ttk.Button(dialog,text="Ver persona",command=lambda:self._on_view_person(person_id)).grid(row=12,column=1)
        ttk.Button(dialog,text="Cerrar",command=dialog.destroy).grid(row=12,column=2)

    def export(self)->None:
        selected=filedialog.asksaveasfilename(parent=self.window,defaultextension=".csv")
        if selected:self.status.configure(text=self.controller.export_csv(Path(selected)).message)
    def close(self)->None:
        if self.window.winfo_exists():self.window.destroy()
        if self._on_close:self._on_close()


def _local(value):return None if value is None else value.astimezone(ZONE).strftime("%Y-%m-%d %H:%M:%S")


def _parse_date(value:str,*,end:bool)->datetime|None:
    if not value.strip():return None
    day=datetime.strptime(value.strip(),"%Y-%m-%d").date()
    return datetime.combine(day,time.max if end else time.min,tzinfo=timezone.utc)
