"""
Optional check (run by run_pipeline.py when the extension is installed): load the generated TMDL model with Microsoft's
Power BI Modeling MCP server (VS Code extension "analysis-services.powerbi-modeling-mcp") in read-only mode.

    python scripts/validate_powerbi_model.py

Prints whether the model imports, and its tables / relationships / measures counts.
Requires the VS Code extension to be installed; the exe path is found automatically.
"""
import json
import queue
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFINITION = (ROOT / "powerbi" / "Klavis_AI_Quality" / "Klavis_AI_Quality.SemanticModel"
              / "definition")


def find_server() -> Path:
    candidates = sorted((Path.home() / ".vscode" / "extensions").glob("analysis-services.powerbi-modeling-mcp-*"))
    if not candidates:
        raise SystemExit("Power BI Modeling MCP extension not found in ~/.vscode/extensions")
    return candidates[-1] / "server" / "powerbi-modeling-mcp.exe"


class McpClient:
    """Minimal JSON-RPC client over stdio (one JSON message per line)."""

    def __init__(self, exe: Path):
        self.proc = subprocess.Popen([str(exe), "--start", "--readonly"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                     encoding="utf-8", bufsize=1)
        self.messages = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            if line.strip().startswith("{"):
                self.messages.put(json.loads(line))

    def request(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
        if not notify:
            self.next_id += 1
            msg["id"] = self.next_id
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while not notify:
            reply = self.messages.get(timeout=180)
            if reply.get("id") == self.next_id:
                return reply

    def tool(self, name, request):
        reply = self.request("tools/call", {"name": name, "arguments": {"request": request}})
        text = "".join(part.get("text", "") for part in reply["result"].get("content", []))
        return json.loads(text)


def main():
    client = McpClient(find_server())
    client.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "klavis-demo-validate", "version": "1.0"}})
    client.request("notifications/initialized", notify=True)
    result = client.tool("database_operations", {"operation": "ImportFromTmdlFolder",
                                                  "tmdlFolderPath": str(DEFINITION)})
    if not result.get("success"):
        client.proc.kill()
        raise SystemExit(f"FAIL: {result.get('message')}")
    stats = client.tool("model_operations", {"operation": "GetStats"})["data"]
    client.proc.kill()
    print(f"PASS: TMDL model imported by the Power BI engine - {stats['TableCount']} tables, "
          f"{stats['TotalColumnCount']} columns, {stats['RelationshipCount']} relationships, "
          f"{stats['TotalMeasureCount']} measures")


if __name__ == "__main__":
    main()
