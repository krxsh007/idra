import json
import os

from app.main import app

if __name__ == "__main__":
    openapi_schema = app.openapi()
    output_path = os.path.join(os.path.dirname(__file__), "../web/openapi.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"OpenAPI schema exported to {output_path}")
