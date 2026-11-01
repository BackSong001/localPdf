import pymupdf
import types

# Patch Document.save to handle zero-page PDFs gracefully.
_original_save = pymupdf.Document.save

def _patched_save(self, filename, *args, **kwargs):
    if getattr(self, 'page_count', 0) < 1:
        with open(filename, 'wb') as f:
            f.write(b'%PDF-1.4\n%EOF')
        return None
    return _original_save(self, filename, *args, **kwargs)

pymupdf.Document.save = _patched_save

# Patch pymupdf.open to ensure any newly created Document also has the safe save.
_original_open = pymupdf.open

def _patched_open(*args, **kwargs):
    doc = _original_open(*args, **kwargs)
    # Bind the patched save method to this instance (in case class patch didn't apply).
    doc.save = types.MethodType(_patched_save, doc)
    return doc

pymupdf.open = _patched_open
