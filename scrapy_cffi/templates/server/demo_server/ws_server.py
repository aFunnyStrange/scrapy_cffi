import asyncio
try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError as e:
    raise ImportError(
        "Missing websockets dependencies. (dev env websockets==15.0.1)"
        "Please install: pip install websockets"
    ) from e
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

ROUTES: dict[str, callable] = {}

def route(path):
    def decorator(func):
        ROUTES[path] = func
        return func
    return decorator

@route("/")
async def root_handler(websocket: "ServerConnection"):
    print(f"[/] new connected: {websocket.remote_address}")
    await websocket.send("welcome to /")
    async for message in websocket:
        print(f"[/] received: {message.decode()}")
        await websocket.send(f"[/] send: {message.decode()}")

@route("/hello")
async def hello_handler(websocket: "ServerConnection"):
    print(f"[/hello] new connected: {websocket.remote_address}")
    await websocket.send("Hi from /hello!")
    async for message in websocket:
        print(f"[/hello] received: {message.decode()}")
        await websocket.send(f"[/hello] send: {message.decode()}")

async def handle_connection(websocket: "ServerConnection"):
    path = websocket.request.path
    handler = ROUTES.get(path)
    if handler:
        try:
            await handler(websocket)
        except ConnectionClosed as e:
            print(f"[{path}] closed: {e}")
        except Exception as e:
            print(f"[{path}] error: {e}")
    else:
        await websocket.send("Unsupported path")
        await websocket.close()

async def main():
    async with websockets.serve(handle_connection, "localhost", 8765):
        print("WebSocket server started on ws://localhost:8765")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())

"""
import asyncio
try:
    import websockets
    from websockets import WebSocketServerProtocol
except ImportError as e:
    raise ImportError(
        "Missing websockets dependencies. (dev env websockets==13.1)"
        "Please install: pip install websockets"
    ) from e

ROUTES: dict[str, callable] = {}

def route(path):
    def decorator(func):
        ROUTES[path] = func
        return func
    return decorator

@route("/")
async def root_handler(websocket: WebSocketServerProtocol, path: str):
    print(f"[/] new connected: {websocket.remote_address}")
    await websocket.send("webcome to /")
    async for message in websocket:
        print(f"[/] received: {message.decode()}")
        await websocket.send(f"[/] send: {message.decode()}")

@route("/hello")
async def hello_handler(websocket: WebSocketServerProtocol, path: str):
    print(f"[/hello] new connected: {websocket.remote_address}")
    await websocket.send("Hi from /hello!")
    async for message in websocket:
        print(f"[/hello] received: {message.decode()}")
        await websocket.send(f"[/hello] send: {message.decode()}")

async def handle_connection(websocket: WebSocketServerProtocol, path: str):
    handler = ROUTES.get(path)
    if handler:
        try:
            await handler(websocket, path)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[{path}] close: {e}")
        except Exception as e:
            print(f"[{path}] error: {e}")
    else:
        await websocket.send("Unsupported path")
        await websocket.close()

async def main():
    server = await websockets.serve(
        handle_connection,
        host="localhost",
        port=8765,
        subprotocols=["chat"]
    )
    print("WebSocket server started on ws://localhost:8765")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
"""