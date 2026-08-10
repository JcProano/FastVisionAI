import inspect
import unittest
from types import SimpleNamespace

from src.ui.people.contracts import PeopleManagerState
from src.ui.people.tk_window import PeopleManagerWindow
from src.ui.main import main


class Var:
    def __init__(self, value=""): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


class Window:
    def __init__(self): self.callbacks = {}; self.cancelled = []; self.destroyed = False; self.next = 0
    def after(self, delay, callback):
        self.next += 1; self.callbacks[self.next] = (delay, callback); return self.next
    def after_cancel(self, identifier): self.cancelled.append(identifier); self.callbacks.pop(identifier, None)
    def winfo_exists(self): return not self.destroyed
    def destroy(self): self.destroyed = True


class PeopleSearchWindowTests(unittest.TestCase):
    def app(self):
        value = PeopleManagerWindow.__new__(PeopleManagerWindow)
        value.window = Window(); value._advanced = SimpleNamespace(
            policy=SimpleNamespace(debounce_ms=400, default_page_size=25),
        )
        value._search_after_id = None; value._page = 3; value.refresh_count = 0
        value.refresh = lambda: setattr(value, "refresh_count", value.refresh_count + 1)
        value.query = Var("name"); value.status_filter = Var("ACTIVE")
        value.created_from = Var("2026-01-01"); value.created_to = Var("2026-01-02")
        value.page_size = Var("50")
        return value

    def test_debounce_replaces_pending_callback_and_runs_once(self):
        app = self.app(); app._schedule_search(); first = app._search_after_id
        self.assertEqual(app.window.callbacks[first][0], 400)
        app._schedule_search(); second = app._search_after_id
        self.assertIn(first, app.window.cancelled); self.assertNotEqual(first, second)
        _, callback = app.window.callbacks.pop(second); callback()
        self.assertEqual(app.refresh_count, 1); self.assertEqual(app._page, 1)

    def test_clear_filters_cancels_and_refreshes_once(self):
        app = self.app(); app._schedule_search(); pending = app._search_after_id
        app.clear_filters()
        self.assertIn(pending, app.window.cancelled)
        self.assertEqual((app.query.get(), app.status_filter.get(), app.created_from.get(),
                          app.created_to.get(), app.page_size.get(), app._page),
                         ("", "TODOS", "", "", "25", 1))
        self.assertEqual(app.refresh_count, 1)

    def test_close_cancels_pending_callback(self):
        app = self.app(); app._schedule_search(); pending = app._search_after_id
        app.controller = SimpleNamespace(state=PeopleManagerState.IDLE, close=lambda: None)
        app._on_cancel_additional = lambda: False
        app.close()
        self.assertIn(pending, app.window.cancelled); self.assertTrue(app.window.destroyed)

    def test_advanced_controls_fallback_and_profile_singleton_are_declared(self):
        source = inspect.getsource(PeopleManagerWindow)
        for text in ("TODOS", "PENDING_BIOMETRIC", "Resultados", "Anterior", "Siguiente",
                     "Mostrando", "Deshabilitar/Habilitar", "advanced_controller"):
            self.assertIn(text, source)
        self.assertIn("if self._advanced is not None", source)
        main_source = inspect.getsource(main)
        self.assertIn("profile_windows.get(person_id)", main_source)
        self.assertIn("current.focus()", main_source)


if __name__ == "__main__": unittest.main()
