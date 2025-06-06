# example from https://gofastmcp.com/servers/openapi#quick-start

import httpx
from fastmcp import FastMCP

# Create an HTTP client for your API
client = httpx.AsyncClient(base_url="http://localhost:5001")

# Load your OpenAPI spec 
openapi_spec = httpx.get("http://localhost:5001/?format=openapi").json()

# Create the MCP server
mcp = FastMCP.from_openapi(
    openapi_spec=openapi_spec,
    client=client,
    name="My API Server"
)

if __name__ == "__main__":
    mcp.run(
        transport="sse",
        host="127.0.0.1",
        port=5002,
        log_level="debug",
    )
