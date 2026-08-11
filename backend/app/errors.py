"""Domain errors. The API layer maps InputError -> HTTP 400, ModelError -> 500."""


class InputError(ValueError):
    """Bad user input (replaces tkinter messagebox.showerror)."""


class ModelError(RuntimeError):
    """Bellhop failed or produced no usable output."""
