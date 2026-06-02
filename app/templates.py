from fastapi.templating import Jinja2Templates
from fastapi import Request

templates = Jinja2Templates(directory="app/templates")

def get_base_template(request: Request) -> str:
    # Boosted requests (navigation links) need the full page layout (base.html)
    if request.headers.get("HX-Boosted"):
        return "base.html"
    
    # Other HTMX requests (modals, forms, table swaps) only need partials (partial_base.html)
    if request.headers.get("HX-Request"):
        return "partial_base.html"
        
    return "base.html"

# Register helper globally
templates.env.globals["get_base_template"] = get_base_template
